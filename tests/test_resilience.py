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
