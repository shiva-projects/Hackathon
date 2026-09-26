"""
Resilience & Graceful Degradation tests (plan.md Section 5, 14.7 & 14.17).
Asserts:
- MCP failure triggers bounded retry, then falls back to UNABLE_TO_COMPLETE
- Gemini timeout triggers graceful degradation to GEMINI_FALLBACK_RATIONALE
- No unhandled exceptions crash the pipeline
"""

import asyncio
import pytest
from src.state import create_initial_state, GEMINI_FALLBACK_RATIONALE
from src.resilience.retry import with_retry
from src.resilience.timeout import with_timeout, ToolTimeoutError, ModelTimeoutError
from src.resilience.fallback import handle_mcp_failure, handle_gemini_failure


@pytest.mark.asyncio
async def test_mcp_unavailable_triggers_retry_then_fallback():
    attempts = 0

    async def faulty_mcp_call():
        nonlocal attempts
        attempts += 1
        raise ConnectionError("Connection refused to MCP stdio transport")

    # 1. Bounded retry must try exactly 2 attempts then raise
    with pytest.raises(ConnectionError):
        await with_retry(
            faulty_mcp_call,
            max_attempts=2,
            initial_backoff=0.01,
            max_backoff=0.02,
            caller_name="test_resilience",
        )
    assert attempts == 2

    # 2. Fallback sets UNABLE_TO_COMPLETE (plan.md Section 14.7)
    state = create_initial_state("APP-RES-01")
    updated_state = handle_mcp_failure(state, "MCP stdio transport offline")

    assert updated_state["decision_status"] == "UNABLE_TO_COMPLETE"
    assert updated_state["unable_reason"] == "MCP_UNAVAILABLE"
    assert updated_state["ai_recommendation"] is None
    assert updated_state["human_review_required"] is True
    assert updated_state["request_status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_model_timeout_triggers_graceful_failure():
    async def slow_gemini_call():
        await asyncio.sleep(0.5)
        return "Adversarial text"

    # Timeout after 0.05s triggers ModelTimeoutError
    with pytest.raises(ModelTimeoutError):
        await with_timeout(
            slow_gemini_call(),
            timeout_seconds=0.05,
            timeout_error_type=ModelTimeoutError,
            error_message="Gemini rationale generation timed out",
        )

    # Fallback preserves deterministic recommendation with exact fallback string (Section 14.17)
    state = create_initial_state("APP-RES-02")
    state["decision_status"] = "DETERMINED"
    state["ai_recommendation"] = "APPROVE"

    fallback_state = handle_gemini_failure(state, "Gemini API timeout")

    # Recommendation survives unaffected
    assert fallback_state["decision_status"] == "DETERMINED"
    assert fallback_state["ai_recommendation"] == "APPROVE"
    assert fallback_state["rationale"] == GEMINI_FALLBACK_RATIONALE


@pytest.mark.asyncio
async def test_no_unhandled_exception_reaches_the_user():
    state = create_initial_state("APP-RES-03")
    try:
        raise RuntimeError("Unexpected socket disconnect")
    except Exception as e:
        safe_state = handle_mcp_failure(state, str(e))

    assert safe_state["decision_status"] == "UNABLE_TO_COMPLETE"
    assert safe_state["unable_reason"] == "MCP_UNAVAILABLE"
    assert safe_state["human_review_required"] is True


def test_mid_run_provider_switch_on_exhausted_retries(monkeypatch):
    """
    v8 Integration test:
    1. Mock Gemini to fail on invoke (raising QuotaExceeded)
    2. Allow Groq to succeed through a mock returning valid content
    3. Trigger retry exhaustion on Gemini
    4. Verify provider switch to Groq
    5. Verify provider_fallback event is written to logs/agent_actions.jsonl
    6. Verify run continues and does NOT immediately become UNABLE_TO_COMPLETE
    7. Verify final deterministic recommendation remains governed by decision engine
    """
    import json
    from pathlib import Path
    from src.llm.client import invoke_with_resilience, reset_run_provider, get_run_provider
    from src.agents.decision_agent import decision_agent_node

    reset_run_provider()
    monkeypatch.setenv("GEMINI_API_KEY", "mock-gemini-key")
    monkeypatch.setenv("GROQ_API_KEY", "mock-groq-key")

    class MockFailingGemini:
        def invoke(self, prompt):
            raise RuntimeError("Gemini 429 Quota Exhausted")

    class MockSuccessfulGroq:
        def invoke(self, prompt):
            class Response:
                content = "Groq generated explanation: Loan satisfies all affordability requirements."
            return Response()

    monkeypatch.setattr("src.llm.client._build_gemini_client", lambda cfg: MockFailingGemini())
    monkeypatch.setattr("src.llm.client._build_groq_client", lambda cfg: MockSuccessfulGroq())

    # 1. Invoke through resilience
    result = invoke_with_resilience("Explain loan approval", run_id="RUN-TEST-FALLBACK")
    assert "Groq generated explanation" in result
    assert get_run_provider() == "groq"

    # 2. Check logs/agent_actions.jsonl for provider_fallback event
    actions_log = Path("logs/agent_actions.jsonl")
    assert actions_log.exists()
    fallback_found = False
    with open(actions_log, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("action") == "provider_fallback":
                det = rec.get("details", {})
                if (
                    det.get("from_provider") == "gemini"
                    and det.get("to_provider") == "groq"
                    and det.get("reason") == "retries_exhausted"
                ):
                    fallback_found = True
                    break
    assert fallback_found, "provider_fallback event was not recorded in logs/agent_actions.jsonl"

    # 3. Test in node: verify deterministic recommendation is preserved and run does not become UNABLE_TO_COMPLETE
    state = create_initial_state("APP-FALLBACK-TEST")
    state["affordability"] = {
        "dti": 0.25,
        "disposable_income": 75000.0,
        "breach": False,
        "threshold": 0.40,
        "monthly_gross_income": 100000.0,
        "monthly_obligations": 25000.0,
    }
    state["rule_evaluations"] = [
        {
            "rule_id": "PL-07",
            "rule_type": "dti_max",
            "passed": True,
            "threshold_value": 0.40,
            "actual_value": 0.25,
            "operator": "<=",
            "message": "DTI 0.25 <= 0.40",
            "is_mandatory_eligibility": True,
        },
        {
            "rule_id": "PL-12",
            "rule_type": "loan_amount_max",
            "passed": True,
            "threshold_value": 1500000.0,
            "actual_value": 300000.0,
            "operator": "<=",
            "message": "Amount 300000 <= 1500000",
            "is_mandatory_eligibility": False,
        },
    ]
    state["policy_selected"] = {"policy_id": "PL-001", "version": "v2.0"}

    final_state = decision_agent_node(state)
    assert final_state["decision_status"] == "DETERMINED"
    assert final_state["ai_recommendation"] == "APPROVE"
    assert final_state["human_review_required"] is False
    assert "Groq generated explanation" in final_state["rationale"]

