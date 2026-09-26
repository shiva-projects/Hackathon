"""
Configurable Multi-Provider LLM Layer (v8 Addendum).
Gemini Primary -> Groq Secondary Fallback.
"""

from src.llm.provider_resolver import load_model_config, resolve_provider
from src.llm.client import get_llm_client, LLMClientHandle, reset_run_provider, set_run_provider, get_run_provider

__all__ = [
    "load_model_config",
    "resolve_provider",
    "get_llm_client",
    "LLMClientHandle",
    "reset_run_provider",
    "set_run_provider",
    "get_run_provider",
]
