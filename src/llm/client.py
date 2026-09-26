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
        if hasattr(self.client, "invoke"):
            response = self.client.invoke(prompt)
            if hasattr(response, "content"):
                return str(response.content)
            return str(response)
        elif callable(self.client):
            return str(self.client(prompt))
        raise AttributeError(f"Client for provider {self.provider} does not support invoke() or __call__")

    async def ainvoke(self, prompt: str) -> str:
        """Asynchronously invokes the underlying client, returning string response content."""
        if hasattr(self.client, "ainvoke"):
            response = await self.client.ainvoke(prompt)
            if hasattr(response, "content"):
                return str(response.content)
            return str(response)
        elif hasattr(self.client, "invoke"):
            return await asyncio.to_thread(self.invoke, prompt)
        elif callable(self.client):
            return await asyncio.to_thread(self.client, prompt)
        raise AttributeError(f"Client for provider {self.provider} does not support ainvoke() or invoke()")


def _build_gemini_client(provider_cfg: Dict[str, Any]) -> Any:
    """Constructs LangChain Google Generative AI client."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = os.environ.get(provider_cfg["env_key"], "")
    return ChatGoogleGenerativeAI(
        model=provider_cfg.get("chat_model", "gemini-2.0-flash"),
        google_api_key=api_key,
        temperature=provider_cfg.get("temperature", 0.0),
    )


def _build_groq_client(provider_cfg: Dict[str, Any]) -> Any:
    """Constructs OpenAI-compatible client pointed at Groq endpoint."""
    from langchain_openai import ChatOpenAI

    api_key = os.environ.get(provider_cfg["env_key"], "")
    base_url = provider_cfg.get("base_url", "https://api.groq.com/openai/v1")
    return ChatOpenAI(
        model=provider_cfg.get("chat_model", "qwen/qwen3-32b"),
        api_key=api_key,
        base_url=base_url,
        temperature=provider_cfg.get("temperature", 0.0),
    )


def get_llm_client(
    force_provider: Optional[str] = None,
    config_path: str = "config/model_config.json",
) -> LLMClientHandle:
    """
    Central LLM factory choke point per v8 specification.
    Resolves provider deterministically, maintains request-scoped provider affinity,
    and returns a ready-to-use LLMClientHandle.
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

    primary_name = config.get("resolution_order", ["gemini"])[0]
    if provider_name == primary_name:
        reason = f"{provider_name} is primary and its env key is present"
    else:
        reason = f"{primary_name}'s env key absent; fell back to {provider_name}"

    if provider_name == "gemini":
        client = _build_gemini_client(provider_cfg)
    elif provider_name == "groq":
        client = _build_groq_client(provider_cfg)
    else:
        raise RuntimeError(f"Unknown provider '{provider_name}' in model_config.json")

    return LLMClientHandle(
        provider=provider_name,
        model=provider_cfg.get("chat_model", ""),
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
) -> None:
    latency_ms = round((end_time - start_time) * 1000.0, 2)
    in_tok = max(1, len(prompt) // 4)
    out_tok = max(1, len(str(result)) // 4)

    # Record real thinking span with measured wall-clock latency
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
        }) + "\n")


def invoke_with_resilience(
    prompt: str,
    run_id: str = "default_run",
    config_path: str = "config/model_config.json",
) -> str:
    """
    Synchronously executes an LLM prompt with bounded retry and request-scoped provider fallback.
    """
    config = load_model_config(config_path)
    retry_cfg = config.get("retry_before_provider_switch", {})
    max_attempts = int(retry_cfg.get("max_attempts_per_provider", 2))

    if not get_run_provider():
        handle = get_llm_client(config_path=config_path)
        set_run_provider(handle.provider)

    resolution_order = config.get("resolution_order", ["gemini", "groq"])
    providers = config.get("providers", {})
    tried = _get_tried_providers()

    while True:
        current_provider = get_run_provider()
        tried.add(current_provider)
        handle = get_llm_client(force_provider=current_provider, config_path=config_path)

        last_error = None
        for attempt in range(1, max_attempts + 1):
            start_time = time.time()
            try:
                result = handle.invoke(prompt)
                end_time = time.time()
                _record_llm_call_metadata(current_provider, handle.model, prompt, result, start_time, end_time, run_id)
                return result
            except Exception as e:
                last_error = e
                time.sleep(0.05)

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
                run_id=run_id,
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
            raise RuntimeError(
                f"All configured LLM providers exhausted retries ({', '.join(tried)}). "
                f"Last error: {last_error}"
            )


async def ainvoke_with_resilience(
    prompt: str,
    run_id: str = "default_run",
    config_path: str = "config/model_config.json",
) -> str:
    """
    Asynchronously executes an LLM prompt with bounded retry and request-scoped provider fallback.
    """
    config = load_model_config(config_path)
    retry_cfg = config.get("retry_before_provider_switch", {})
    max_attempts = int(retry_cfg.get("max_attempts_per_provider", 2))

    if not get_run_provider():
        handle = get_llm_client(config_path=config_path)
        set_run_provider(handle.provider)

    resolution_order = config.get("resolution_order", ["gemini", "groq"])
    providers = config.get("providers", {})
    tried = _get_tried_providers()

    while True:
        current_provider = get_run_provider()
        tried.add(current_provider)
        handle = get_llm_client(force_provider=current_provider, config_path=config_path)

        last_error = None
        for attempt in range(1, max_attempts + 1):
            start_time = time.time()
            try:
                result = await handle.ainvoke(prompt)
                end_time = time.time()
                _record_llm_call_metadata(current_provider, handle.model, prompt, result, start_time, end_time, run_id)
                return result
            except Exception as e:
                last_error = e
                await asyncio.sleep(0.05)

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
                run_id=run_id,
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
            raise RuntimeError(
                f"All configured LLM providers exhausted retries ({', '.join(tried)}). "
                f"Last error: {last_error}"
            )
