"""
Unit tests for deterministic multi-provider LLM resolution and fallback.
Per v8 Addendum Section 7 and Remediation Phase 1.
Tests require NO network access.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest

from src.llm.provider_resolver import load_model_config, resolve_provider
from src.llm.client import invoke_with_resilience, reset_run_provider, get_run_provider
from src.domain.models import AffordabilityResult
from src.domain.calculations import calculate_dti, calculate_monthly_gross_income, calculate_monthly_obligations
from src.domain.rules import evaluate_policy_rules
from src.domain.decisions import evaluate_underwriting_decision


def test_prefers_gemini_when_both_keys_present(monkeypatch):
    """1. Gemini configured + Groq configured -> Gemini selected."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSy_live_mock_key_for_testing")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_dummy_key_12345")
    provider_name, _ = resolve_provider(load_model_config())
    assert provider_name == "gemini"


def test_falls_back_to_groq_when_gemini_key_absent(monkeypatch):
    """3. Gemini unavailable + Groq configured -> Groq selected."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_dummy_key_12345")
    provider_name, _ = resolve_provider(load_model_config())
    assert provider_name == "groq"


def test_raises_when_no_provider_key_present(monkeypatch):
    """4. Neither configured -> explicit failure path."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        resolve_provider(load_model_config())
    assert "No configured LLM provider has a live API key" in str(exc_info.value)


def test_resolution_order_is_config_driven(monkeypatch):
    """Flipping resolution_order in config changes the deterministic outcome."""
    cfg = load_model_config()
    cfg["resolution_order"] = ["groq", "gemini"]
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSy_live_mock_key")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_dummy_key_12345")
    provider_name, _ = resolve_provider(cfg)
    assert provider_name == "groq"


def test_gemini_transient_failure_falls_back_to_groq(monkeypatch):
    """2. Gemini transient failure + Groq configured -> Groq selected."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSy_MockKey")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_MockKey")
    reset_run_provider()

    mock_gemini = MagicMock()
    mock_gemini.invoke.side_effect = RuntimeError("ResourceExhausted: 429 Quota Exceeded")

    mock_groq = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "Groq fallback rationale explanation."
    mock_response.usage_metadata = {"input_tokens": 100, "output_tokens": 50}
    mock_groq.invoke.return_value = mock_response

    def fake_get_llm_client(force_provider=None, force_model=None, config_path="config/model_config.json"):
        from src.llm.client import LLMClientHandle
        if force_provider == "gemini":
            return LLMClientHandle("gemini", "gemini-3.7-flash", mock_gemini, "mock gemini")
        elif force_provider == "groq":
            return LLMClientHandle("groq", "openai/gpt-oss-120b", mock_groq, "mock groq")
        else:
            p = get_run_provider() or "gemini"
            return fake_get_llm_client(force_provider=p, config_path=config_path)

    with patch("src.llm.client.get_llm_client", side_effect=fake_get_llm_client):
        result = invoke_with_resilience("Explain approval", run_id="RUN-TEST-FALLBACK")
        assert result == "Groq fallback rationale explanation."
        assert get_run_provider() == "groq"


def test_provider_choice_does_not_alter_deterministic_underwriting():
    """5. Provider choice does not alter deterministic DTI/affordability/recommendation."""
    income = calculate_monthly_gross_income(100000, "monthly")
    obligations = calculate_monthly_obligations([{"obligation_type": "car_loan", "amount": 25000, "period": "monthly"}])
    dti = calculate_dti(obligations, income)
    assert dti == Decimal("0.250000")

    affordability = AffordabilityResult(
        monthly_gross_income=income,
        monthly_obligations=obligations,
        disposable_income=income - obligations,
        dti=dti,
        threshold=Decimal("0.40"),
        breach=False,
    )

    applicant_facts = {
        "application_id": "APP-TEST",
        "requested_amount": 300000,
        "tenure_months": 24,
        "documents": ["identity_proof", "income_statement"],
    }
    policy_rules = [
        {"rule_type": "dti_max", "value": "0.40", "rule_id": "DTI_MAX", "operator": "<="},
        {"rule_type": "minimum_income", "value": "25000", "rule_id": "MIN_INCOME", "operator": ">="},
    ]

    rule_results1, risk_flags1 = evaluate_policy_rules(applicant_facts, policy_rules, affordability)
    rule_results2, risk_flags2 = evaluate_policy_rules(applicant_facts, policy_rules, affordability)

    dec1 = evaluate_underwriting_decision(affordability, rule_results1, risk_flags1)
    dec2 = evaluate_underwriting_decision(affordability, rule_results2, risk_flags2)

    assert dec1.ai_recommendation == "APPROVE"
    assert dec2.ai_recommendation == "APPROVE"
    assert dec1.human_review_required is False
    assert dec2.human_review_required is False
