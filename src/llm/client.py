"""
Centralized LLM Client Factory and Resilient Choke Point.
Per v8 Addendum Section 4, 6, 9, 10 & 11.
Single application-level entry point for model calls across the copilot.
"""

import os
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set, Tuple

from src.llm.provider_resolver import load_model_config, resolve_provider
from src.observability.unified_logger import log_agent_action

# Module-level run provider state (run-level switching per Section 10)
_current_run_provider: Optional[str] = None
_tried_providers_this_run: Set[str] = set()


def get_run_provider() -> Optional[str]:
    """Returns the current run-level active provider."""
    global _current_run_provider
    return _current_run_provider


def set_run_provider(provider: str) -> None:
    """Sets the active run-level provider."""
    global _current_run_provider
    _current_run_provider = provider


def reset_run_provider() -> None:
    """Resets the active run-level provider and tried set (for new runs/tests)."""
    global _current_run_provider, _tried_providers_this_run
    _current_run_provider = None
    _tried_providers_this_run = set()


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
        """Invokes the underlying client, returning string response content."""
        if hasattr(self.client, "invoke"):
            response = self.client.invoke(prompt)
            if hasattr(response, "content"):
                return str(response.content)
            return str(response)
        elif callable(self.client):
            return str(self.client(prompt))
        raise AttributeError(f"Client for provider {self.provider} does not support invoke() or __call__")


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
    Resolves provider deterministically, maintains run-level provider affinity,
    and returns a ready-to-use LLMClientHandle.
    """
    global _current_run_provider
    config = load_model_config(config_path)

    if force_provider:
        provider_name = force_provider
        provider_cfg = config.get("providers", {}).get(provider_name)
        if not provider_cfg:
            raise RuntimeError(f"Unknown forced provider '{provider_name}' in model_config.json")
    elif _current_run_provider:
        provider_name = _current_run_provider
        provider_cfg = config.get("providers", {}).get(provider_name)
        if not provider_cfg:
            raise RuntimeError(f"Unknown active run provider '{provider_name}' in model_config.json")
    else:
        provider_name, provider_cfg = resolve_provider(config)
        _current_run_provider = provider_name

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


def invoke_with_resilience(
    prompt: str,
    run_id: str = "default_run",
    config_path: str = "config/model_config.json",
) -> str:
    """
    Executes an LLM prompt with bounded retry and automatic provider fallback.
    Per v8 Section 9 & 10:
      1. Tries current provider up to max_attempts_per_provider
      2. On retry exhaustion, looks for the next configured provider with a live key
      3. If found, logs 'provider_fallback' to logs/agent_actions.jsonl, locks new provider for the run, and retries
      4. If all providers exhausted, raises RuntimeError for upstream fallback handling
    """
    global _current_run_provider, _tried_providers_this_run
    config = load_model_config(config_path)
    retry_cfg = config.get("retry_before_provider_switch", {})
    max_attempts = int(retry_cfg.get("max_attempts_per_provider", 2))

    # Ensure initial provider is resolved
    if not _current_run_provider:
        handle = get_llm_client(config_path=config_path)
        _current_run_provider = handle.provider

    resolution_order = config.get("resolution_order", ["gemini", "groq"])
    providers = config.get("providers", {})

    while True:
        current_provider = _current_run_provider
        _tried_providers_this_run.add(current_provider)
        handle = get_llm_client(force_provider=current_provider, config_path=config_path)

        # Attempt calls with bounded retries
        success = False
        last_error = None

        for attempt in range(1, max_attempts + 1):
            try:
                result = handle.invoke(prompt)
                return result
            except Exception as e:
                last_error = e
                # Backoff slightly before next attempt
                time.sleep(0.05)

        # Retries exhausted for current_provider
        # Look for the next configured provider not yet tried this run with an available key
        next_provider = None
        for cand in resolution_order:
            if cand not in _tried_providers_this_run and cand in providers:
                cand_key = providers[cand].get("env_key")
                if cand_key and os.environ.get(cand_key):
                    next_provider = cand
                    break

        if next_provider:
            # Switch provider at run-level
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
            _current_run_provider = next_provider
            # Loop continues with next_provider
        else:
            # All providers exhausted
            raise RuntimeError(
                f"All configured LLM providers exhausted retries ({', '.join(_tried_providers_this_run)}). "
                f"Last error: {last_error}"
            )
