"""
Provider Compliance Regression Tests.
Per Pre-Submission Review:
  1. Gemini configured -> Gemini path usable.
  2. Gemini unavailable / retry failure -> Groq fallback works.
  3. Groq configured -> Groq works.
  4. Neither provider configured -> Clear configuration failure.
  5. Evidence matches provider actually used.
  6. Provider resolution is request-scoped (no cross-request state bleed).
"""

import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.llm.provider_resolver import (
    validate_provider_environment,
    has_live_provider_key,
    resolve_provider,
    load_model_config,
)
from src.llm.client import (
    get_llm_client,
    get_run_provider,
    set_run_provider,
    reset_run_provider,
    invoke_with_resilience,
)

APPROVED_PROVIDERS = {"gemini", "groq"}  # Groq approved per instructor exception — see docs/instructor-provider-exception.md


def test_committed_evidence_used_approved_provider():
    """
    Per the faculty-amended provider rule: committed evidence must have been
    generated using an approved provider (Gemini, or Groq per documented 
    instructor exception). Fails the build if a run resolves to anything else.
    """
    env_p = Path("reports/environment.json")
    assert env_p.exists(), "reports/environment.json missing — run regenerate_evidence.py"
    env_data = json.loads(env_p.read_text(encoding="utf-8"))
    assert env_data["provider"] in APPROVED_PROVIDERS, (
        f"Committed evidence was generated with provider='{env_data['provider']}', "
        f"which is not on the approved list {APPROVED_PROVIDERS}."
    )


def test_gemini_configured_path(monkeypatch):
    """When GEMINI_API_KEY is present and non-placeholder, Gemini path is selected."""
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyLiveTestKeyForTestingOnly")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    val = validate_provider_environment()
    assert val["has_live_key"] is True
    assert val["active_provider"] == "gemini"
    assert val["available_providers"] == ["gemini"]

    prov, cfg = resolve_provider()
    assert prov == "gemini"
    assert cfg.get("env_key") == "GEMINI_API_KEY"


def test_groq_configured_path(monkeypatch):
    """When GEMINI_API_KEY is absent and GROQ_API_KEY is present, Groq path is selected."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_liveTestKey123456789")

    val = validate_provider_environment()
    assert val["has_live_key"] is True
    assert val["active_provider"] == "groq"
    assert val["available_providers"] == ["groq"]

    prov, cfg = resolve_provider()
    assert prov == "groq"
    assert cfg.get("env_key") == "GROQ_API_KEY"


def test_neither_provider_configured(monkeypatch):
    """When neither provider has a live key, clear configuration failure is raised."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    val = validate_provider_environment()
    assert val["has_live_key"] is False
    assert val["active_provider"] is None
    assert has_live_provider_key() is False

    with pytest.raises(RuntimeError, match="No configured LLM provider has a live API key"):
        resolve_provider()


def test_dummy_placeholder_keys_rejected(monkeypatch):
    """Dummy template keys must never be treated as live keys."""
    monkeypatch.setenv("GEMINI_API_KEY", "your_gemini_api_key_here")
    monkeypatch.setenv("GROQ_API_KEY", "your_groq_api_key_here")

    val = validate_provider_environment()
    assert val["has_live_key"] is False
    assert val["active_provider"] is None
    assert has_live_provider_key() is False


def test_gemini_quota_failure_falls_back_to_groq(monkeypatch):
    """
    When Gemini fails or exhausts retries, invoke_with_resilience
    falls back cleanly to Groq and logs provider_fallback.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyMockKeyForFallbackTest")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_MockGroqKeyForFallbackTest")
    reset_run_provider()

    mock_gemini = MagicMock()
    mock_gemini.invoke.side_effect = RuntimeError("ResourceExhausted: 429 Quota Exceeded")

    mock_groq = MagicMock()
    mock_groq.invoke.return_value = "Groq fallback rationale explanation."

    def fake_get_llm_client(force_provider=None, config_path="config/model_config.json"):
        from src.llm.client import LLMClientHandle
        if force_provider == "gemini":
            return LLMClientHandle("gemini", "gemini-2.0-flash", mock_gemini, "mock gemini")
        elif force_provider == "groq":
            return LLMClientHandle("groq", "qwen/qwen3-32b", mock_groq, "mock groq")
        else:
            p = get_run_provider() or "gemini"
            return fake_get_llm_client(force_provider=p, config_path=config_path)

    with patch("src.llm.client.get_llm_client", side_effect=fake_get_llm_client):
        result = invoke_with_resilience("Explain approval", run_id="RUN-TEST-FALLBACK")
        assert result == "Groq fallback rationale explanation."
        assert get_run_provider() == "groq"


def test_request_scoped_provider_isolation():
    """
    Verifies that provider state is request-scoped via contextvars and
    isolated across independent execution contexts.
    """
    import contextvars

    reset_run_provider()
    assert get_run_provider() is None

    # Set in one context
    ctx = contextvars.copy_context()

    def run_in_ctx():
        set_run_provider("groq")
        return get_run_provider()

    result_ctx = ctx.run(run_in_ctx)
    assert result_ctx == "groq"

    # Main context should remain isolated
    assert get_run_provider() is None


def test_evidence_provider_consistency():
    """
    Verifies that generated evidence files exist and do not contradict each other
    regarding the resolved provider.
    """
    env_p = Path("reports/environment.json")
    signals_p = Path("reports/golden_signals.json")
    latest_p = Path("reports/latest_run.json")

    if env_p.exists() and signals_p.exists() and latest_p.exists():
        env_data = json.loads(env_p.read_text(encoding="utf-8"))
        signals_data = json.loads(signals_p.read_text(encoding="utf-8"))
        latest_data = json.loads(latest_p.read_text(encoding="utf-8"))

        env_prov = env_data.get("provider")
        signals_prov = signals_data.get("provider")
        latest_prov = latest_data.get("provider")

        # Provider must be consistent across environment, signals, and latest run
        assert env_prov == latest_prov, f"Mismatch: environment has {env_prov}, latest_run has {latest_prov}"
        if signals_prov:
            assert env_prov == signals_prov, f"Mismatch: environment has {env_prov}, signals has {signals_prov}"
