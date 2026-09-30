"""
Centralized LLM Client Factory and Resilient Choke Point.
Per v8 Addendum Section 4, 6, 9, 10 & 11.
Single application-level entry point for model calls across the copilot.
Request-scoped provider state using contextvars.
"""

import os
import json
import time
import asyncio
import contextvars
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

from src.llm.provider_resolver import load_model_config, resolve_provider, validate_provider_environment
from src.observability.unified_logger import log_agent_action

# Request-scoped provider state (using ContextVar to prevent concurrency collisions)
_request_provider: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_provider", default=None)
_request_tried_providers: contextvars.ContextVar[Optional[Set[str]]] = contextvars.ContextVar("request_tried_providers", default=None)


def get_run_provider() -> Optional[str]:
    """Returns the current request-scoped active provider."""
    return _request_provider.get()


def set_run_provider(provider: str) -> None:
    """Sets the request-scoped active provider."""
    _request_provider.set(provider)


def reset_run_provider() -> None:
    """Resets the request-scoped active provider and tried set."""
    _request_provider.set(None)
    _request_tried_providers.set(set())


def _get_tried_providers() -> Set[str]:
    tried = _request_tried_providers.get()
    if tried is None:
        tried = set()
        _request_tried_providers.set(tried)
    return tried


class LLMClientHandle:
    """Handle holding resolved provider metadata, client instance, and reasoning."""

    def __init__(
        self,
        provider: str,
        model: str,
        client: Any,
        resolution_reason: str,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.provider = provider
        self.model = model
        self.client = client
        self.resolution_reason = resolution_reason
        self.config = config or {}

    def invoke(self, prompt: str) -> str:
        """Invokes the underlying client synchronously, returning string response content."""
        content, _, _, _ = self.invoke_with_usage(prompt)
        return content

    def invoke_with_usage(self, prompt: str) -> Tuple[str, Optional[int], Optional[int], str]:
        """Invokes client synchronously and returns (content, input_tokens, output_tokens, usage_source)."""
        if hasattr(self.client, "invoke"):
            response = self.client.invoke(prompt)
            content = str(getattr(response, "content", response))
            usage = getattr(response, "usage_metadata", None)
            if not usage:
                resp_meta = getattr(response, "response_metadata", {}) or {}
                usage = resp_meta.get("token_usage", {})
            in_tok = None
            out_tok = None
            source = "unavailable"
            if usage:
                in_val = usage.get("input_tokens") or usage.get("prompt_tokens")
                out_val = usage.get("output_tokens") or usage.get("completion_tokens")
                if in_val is not None:
                    in_tok = int(in_val)
                if out_val is not None:
                    out_tok = int(out_val)
                if in_tok is not None and out_tok is not None:
                    source = "provider_usage_metadata"
            return content, in_tok, out_tok, source
        elif callable(self.client):
            return str(self.client(prompt)), None, None, "unavailable"
        raise AttributeError(f"Client for provider {self.provider} does not support invoke() or __call__")

    async def ainvoke(self, prompt: str) -> str:
        """Asynchronously invokes the underlying client, returning string response content."""
        content, _, _, _ = await self.ainvoke_with_usage(prompt)
        return content

    async def ainvoke_with_usage(self, prompt: str) -> Tuple[str, Optional[int], Optional[int], str]:
        """Asynchronously invokes client and returns (content, input_tokens, output_tokens, usage_source)."""
        if hasattr(self.client, "ainvoke"):
            response = await self.client.ainvoke(prompt)
            content = str(getattr(response, "content", response))
            usage = getattr(response, "usage_metadata", None)
            if not usage:
                resp_meta = getattr(response, "response_metadata", {}) or {}
                usage = resp_meta.get("token_usage", {})
            in_tok = None
            out_tok = None
            source = "unavailable"
            if usage:
                in_val = usage.get("input_tokens") or usage.get("prompt_tokens")
                out_val = usage.get("output_tokens") or usage.get("completion_tokens")
                if in_val is not None:
                    in_tok = int(in_val)
                if out_val is not None:
                    out_tok = int(out_val)
                if in_tok is not None and out_tok is not None:
                    source = "provider_usage_metadata"
            return content, in_tok, out_tok, source
        elif hasattr(self.client, "invoke"):
            return await asyncio.to_thread(self.invoke_with_usage, prompt)
        elif callable(self.client):
            res = await asyncio.to_thread(self.client, prompt)
            return str(res), None, None, "unavailable"
        raise AttributeError(f"Client for provider {self.provider} does not support ainvoke() or invoke()")


def _build_gemini_client(provider_cfg: Dict[str, Any]) -> Any:
    """Constructs LangChain Google Generative AI client."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = os.environ.get(provider_cfg["env_key"], "")
    timeout_val = float(provider_cfg.get("timeout", 15.0))
    model_name = os.getenv("GEMINI_MODEL") or provider_cfg.get("chat_model", "gemini-3.7-flash")
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=provider_cfg.get("temperature", 0.0),
        timeout=timeout_val,
    )


def _build_groq_client(provider_cfg: Dict[str, Any]) -> Any:
    """Constructs OpenAI-compatible client pointed at Groq endpoint."""
    from langchain_openai import ChatOpenAI

    api_key = os.environ.get(provider_cfg["env_key"], "")
    base_url = provider_cfg.get("base_url", "https://api.groq.com/openai/v1")
    timeout_val = float(provider_cfg.get("timeout", 15.0))
    return ChatOpenAI(
        model=provider_cfg.get("chat_model", "openai/gpt-oss-120b"),
        api_key=api_key,
        base_url=base_url,
        temperature=provider_cfg.get("temperature", 0.0),
        timeout=timeout_val,
        max_retries=1,
    )


def get_llm_client(
    force_provider: Optional[str] = None,
    force_model: Optional[str] = None,
    config_path: str = "config/model_config.json",
) -> LLMClientHandle:
    """
    Central LLM factory choke point per v8 specification.
    Resolves provider deterministically, maintains request-scoped provider affinity,
    and returns a ready-to-use LLMClientHandle. Supports force_model for rate-limit fallbacks.
    """
    config = load_model_config(config_path)

    active_provider = get_run_provider()
    if force_provider:
        provider_name = force_provider
        provider_cfg = config.get("providers", {}).get(provider_name)
        if not provider_cfg:
            raise RuntimeError(f"Unknown forced provider '{provider_name}' in model_config.json")
    elif active_provider:
        provider_name = active_provider
        provider_cfg = config.get("providers", {}).get(provider_name)
        if not provider_cfg:
            raise RuntimeError(f"Unknown active run provider '{provider_name}' in model_config.json")
    else:
        provider_name, provider_cfg = resolve_provider(config)
        set_run_provider(provider_name)

    cfg_to_use = dict(provider_cfg)
    if force_model:
        cfg_to_use["chat_model"] = force_model
    model_name = cfg_to_use.get("chat_model", "")

    primary_name = config.get("resolution_order", ["gemini"])[0]
    if provider_name == primary_name:
        reason = f"{provider_name} is primary and its env key is present"
    else:
        reason = f"{primary_name}'s env key absent; fell back to {provider_name}"

    if provider_name == "gemini":
        client = _build_gemini_client(cfg_to_use)
    elif provider_name == "groq":
        client = _build_groq_client(cfg_to_use)
    else:
        raise RuntimeError(f"Unknown provider '{provider_name}' in model_config.json")

    return LLMClientHandle(
        provider=provider_name,
        model=model_name,
        client=client,
        resolution_reason=reason,
        config=config,
    )


def _record_llm_call_metadata(
    current_provider: str,
    model: str,
    prompt: str,
    result: str,
    start_time: float,
    end_time: float,
    run_id: str,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    usage_source: str = "provider_usage_metadata",
) -> None:
    latency_ms = round((end_time - start_time) * 1000.0, 2)
    in_tok = input_tokens if input_tokens is not None else 0
    out_tok = output_tokens if output_tokens is not None else 0

    # Record real thinking span with measured wall-clock latency and real token counts
    from src.observability.tracing import tracer
    tracer.record_span(
        name=f"llm.{current_provider}",
        span_kind="thinking",
        start_time=start_time,
        end_time=end_time,
        inputs={"prompt_preview": prompt[:100], "input_tokens": in_tok},
        outputs={"result_preview": str(result)[:100], "output_tokens": out_tok},
        run_id=run_id,
        step_id=f"step-llm-{current_provider}",
        attributes={
            "llm.token_count.prompt": in_tok,
            "llm.token_count.completion": out_tok,
            "llm.token_count.total": in_tok + out_tok,
            "llm.model_name": model,
            "llm.usage_source": usage_source,
        },
    )

    # Log token usage & exact measured latency to logs/llm_calls.jsonl
    llm_log_path = Path("logs/llm_calls.jsonl")
    llm_log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(llm_log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "provider": current_provider,
            "model": model,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "latency_ms": latency_ms,
            "usage_source": usage_source,
        }) + "\n")


def _calculate_backoff_and_wait(err: Exception, attempt: int) -> float:
    err_str = str(err).lower()
    if "429" in err_str or "rate_limit" in err_str or "quota" in err_str:
        import re
        m_min_sec = re.search(r"try again in (?:(\d+)m)?(\d+(?:\.\d+)?)s", str(err), re.IGNORECASE)
        if m_min_sec:
            mins = float(m_min_sec.group(1)) if m_min_sec.group(1) else 0.0
            secs = float(m_min_sec.group(2)) if m_min_sec.group(2) else 0.0
            total_sec = mins * 60.0 + secs
            return min(total_sec + 0.5, 30.0)
        return min(2.5 * attempt, 15.0)
    if "connection" in err_str or "timeout" in err_str or "network" in err_str or "failed to resolve" in err_str or "getaddrinfo" in err_str:
        return min(2.0 * attempt, 10.0)
    return 0.1


def invoke_with_resilience(
    prompt: str,
    run_id: Optional[str] = None,
    config_path: str = "config/model_config.json",
    force_model: Optional[str] = None,
) -> str:
    """
    Synchronously executes an LLM prompt with bounded retry and request-scoped provider fallback.
    """
    from src.context.execution_context import resolve_run_id
    effective_run_id = resolve_run_id(run_id, required=False)

    config = load_model_config(config_path)
    retry_cfg = config.get("retry_before_provider_switch", {})
    max_attempts = int(retry_cfg.get("max_attempts_per_provider", 2))
    timeout_sec = float(retry_cfg.get("timeout_seconds", 15.0))

    if not get_run_provider():
        handle = get_llm_client(config_path=config_path, force_model=force_model)
        set_run_provider(handle.provider)

    resolution_order = config.get("resolution_order", ["gemini", "groq"])
    providers = config.get("providers", {})
    tried = _get_tried_providers()

    while True:
        current_provider = get_run_provider()
        tried.add(current_provider)
        handle = get_llm_client(force_provider=current_provider, force_model=force_model, config_path=config_path)

        last_error = None
        attempt = 0
        while True:
            attempt += 1
            curr_h = handle

            start_time = time.time()
            try:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(curr_h.invoke_with_usage, prompt)
                    result, in_tok, out_tok, u_source = future.result(timeout=timeout_sec)
                end_time = time.time()
                _record_llm_call_metadata(current_provider, curr_h.model, prompt, result, start_time, end_time, effective_run_id, in_tok, out_tok, u_source)
                return result
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                is_rate_limit = "429" in err_str or "rate_limit" in err_str or "quota" in err_str or "overloaded" in err_str
                fb_model = providers.get(current_provider, {}).get("fallback_chat_model")
                primary_model = providers.get(current_provider, {}).get("chat_model")
                can_fallback = (not force_model) or (force_model == primary_model)
                if is_rate_limit and attempt >= max_attempts and fb_model and curr_h.model != fb_model and can_fallback:
                    try:
                        log_agent_action(
                            actor="llm_client",
                            action="model_fallback",
                            tool="llm_model",
                            decision="FALLBACK_MODEL",
                            run_id=effective_run_id,
                            details={
                                "event": "model_fallback",
                                "from_model": curr_h.model,
                                "to_model": fb_model,
                                "reason": "rate_limit",
                            },
                        )
                        fb_h = get_llm_client(force_provider=current_provider, force_model=fb_model, config_path=config_path)
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                            future = pool.submit(fb_h.invoke_with_usage, prompt)
                            result, in_tok, out_tok, u_source = future.result(timeout=timeout_sec)
                        end_time = time.time()
                        _record_llm_call_metadata(current_provider, fb_h.model, prompt, result, start_time, end_time, effective_run_id, in_tok, out_tok, u_source)
                        return result
                    except Exception as inner_e:
                        last_error = inner_e
                        err_str = str(inner_e).lower()
                        is_rate_limit = "429" in err_str or "rate_limit" in err_str or "quota" in err_str
                
                is_conn_error = "connection" in err_str or "timeout" in err_str or "network" in err_str or "failed to resolve" in err_str or "getaddrinfo" in err_str
                max_allowed = 6 if (is_rate_limit or is_conn_error) else max_attempts
                if attempt >= max_allowed:
                    break
                wait_sec = _calculate_backoff_and_wait(last_error, attempt)
                time.sleep(wait_sec)

        next_provider = None
        for cand in resolution_order:
            if cand not in tried and cand in providers:
                cand_key = providers[cand].get("env_key")
                if cand_key and os.environ.get(cand_key):
                    next_provider = cand
                    break

        if next_provider:
            now_iso = datetime.now(timezone.utc).isoformat()
            log_agent_action(
                actor="llm_client",
                action="provider_fallback",
                tool="llm_provider",
                decision="SWITCHED",
                run_id=effective_run_id,
                details={
                    "event": "provider_fallback",
                    "from_provider": current_provider,
                    "to_provider": next_provider,
                    "reason": "retries_exhausted",
                    "timestamp": now_iso,
                },
            )
            set_run_provider(next_provider)
        else:
            err_msg = str(last_error) if str(last_error) else repr(last_error)
            raise RuntimeError(
                f"All configured LLM providers exhausted retries ({', '.join(tried)}). "
                f"Last error: {err_msg}"
            )


async def ainvoke_with_resilience(
    prompt: str,
    run_id: Optional[str] = None,
    config_path: str = "config/model_config.json",
    force_model: Optional[str] = None,
) -> str:
    """
    Asynchronously executes an LLM prompt with bounded retry and request-scoped provider fallback.
    """
    from src.context.execution_context import resolve_run_id
    effective_run_id = resolve_run_id(run_id, required=False)

    config = load_model_config(config_path)
    retry_cfg = config.get("retry_before_provider_switch", {})
    max_attempts = int(retry_cfg.get("max_attempts_per_provider", 2))
    timeout_sec = float(retry_cfg.get("timeout_seconds", 15.0))

    if not get_run_provider():
        handle = get_llm_client(config_path=config_path, force_model=force_model)
        set_run_provider(handle.provider)

    resolution_order = config.get("resolution_order", ["gemini", "groq"])
    providers = config.get("providers", {})
    tried = _get_tried_providers()

    while True:
        current_provider = get_run_provider()
        tried.add(current_provider)
        handle = get_llm_client(force_provider=current_provider, force_model=force_model, config_path=config_path)

        last_error = None
        attempt = 0
        while True:
            attempt += 1
            curr_h = handle

            start_time = time.time()
            try:
                result, in_tok, out_tok, u_source = await asyncio.wait_for(curr_h.ainvoke_with_usage(prompt), timeout=timeout_sec)
                end_time = time.time()
                _record_llm_call_metadata(current_provider, curr_h.model, prompt, result, start_time, end_time, effective_run_id, in_tok, out_tok, u_source)
                return result
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                is_rate_limit = "429" in err_str or "rate_limit" in err_str or "quota" in err_str or "overloaded" in err_str
                fb_model = providers.get(current_provider, {}).get("fallback_chat_model")
                primary_model = providers.get(current_provider, {}).get("chat_model")
                can_fallback = (not force_model) or (force_model == primary_model)
                if is_rate_limit and attempt >= max_attempts and fb_model and curr_h.model != fb_model and can_fallback:
                    try:
                        log_agent_action(
                            actor="llm_client",
                            action="model_fallback",
                            tool="llm_model",
                            decision="FALLBACK_MODEL",
                            run_id=effective_run_id,
                            details={
                                "event": "model_fallback",
                                "from_model": curr_h.model,
                                "to_model": fb_model,
                                "reason": "rate_limit",
                            },
                        )
                        fb_h = get_llm_client(force_provider=current_provider, force_model=fb_model, config_path=config_path)
                        result, in_tok, out_tok, u_source = await asyncio.wait_for(fb_h.ainvoke_with_usage(prompt), timeout=timeout_sec)
                        end_time = time.time()
                        _record_llm_call_metadata(current_provider, fb_h.model, prompt, result, start_time, end_time, effective_run_id, in_tok, out_tok, u_source)
                        return result
                    except Exception as inner_e:
                        last_error = inner_e
                        err_str = str(inner_e).lower()
                        is_rate_limit = "429" in err_str or "rate_limit" in err_str or "quota" in err_str
                
                is_conn_error = "connection" in err_str or "timeout" in err_str or "network" in err_str or "failed to resolve" in err_str or "getaddrinfo" in err_str
                max_allowed = 6 if (is_rate_limit or is_conn_error) else max_attempts
                if attempt >= max_allowed:
                    break
                wait_sec = _calculate_backoff_and_wait(last_error, attempt)
                await asyncio.sleep(wait_sec)

        next_provider = None
        for cand in resolution_order:
            if cand not in tried and cand in providers:
                cand_key = providers[cand].get("env_key")
                if cand_key and os.environ.get(cand_key):
                    next_provider = cand
                    break

        if next_provider:
            now_iso = datetime.now(timezone.utc).isoformat()
            log_agent_action(
                actor="llm_client",
                action="provider_fallback",
                tool="llm_provider",
                decision="SWITCHED",
                run_id=effective_run_id,
                details={
                    "event": "provider_fallback",
                    "from_provider": current_provider,
                    "to_provider": next_provider,
                    "reason": "retries_exhausted",
                    "timestamp": now_iso,
                },
            )
            set_run_provider(next_provider)
        else:
            err_msg = str(last_error) if str(last_error) else repr(last_error)
            raise RuntimeError(
                f"All configured LLM providers exhausted retries ({', '.join(tried)}). "
                f"Last error: {err_msg}"
            )


