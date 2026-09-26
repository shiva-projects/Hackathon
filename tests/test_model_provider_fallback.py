"""
Unit tests for deterministic multi-provider LLM resolution and fallback.
Per v8 Addendum Section 7.
Tests require NO network access.
"""

import pytest
from src.llm.provider_resolver import load_model_config, resolve_provider


def test_prefers_gemini_when_both_keys_present(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_dummy")
    provider_name, _ = resolve_provider(load_model_config())
    assert provider_name == "gemini"


def test_falls_back_to_groq_when_gemini_key_absent(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_dummy")
    provider_name, _ = resolve_provider(load_model_config())
    assert provider_name == "groq"


def test_raises_when_no_provider_key_present(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        resolve_provider(load_model_config())
    assert "No configured LLM provider has a live API key" in str(exc_info.value)


def test_resolution_order_is_config_driven(monkeypatch):
    # Flipping resolution_order in config, not code, changes the outcome
    cfg = load_model_config()
    cfg["resolution_order"] = ["groq", "gemini"]
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_dummy")
    provider_name, _ = resolve_provider(cfg)
    assert provider_name == "groq"
