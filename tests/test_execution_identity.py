"""
Automated tests for Canonical Run/Evidence Identity (Phase 3).
Verifies:
1. Correlation of MCP, tool, audit, and trace records with matching run_id and session_id.
2. Loud failure (ValueError) when run_id is missing for consequential operations.
3. Stable tool_call_id across retries with incrementing attempt (1 -> 2).
4. Total elimination of prohibited defaults: "default_run", "RUN-MCP", "RUN-UNKNOWN", "default-session".
5. Semantic distinction between session_id and run_id.
"""

import json
import uuid
import pytest
from pathlib import Path

from src.context.execution_context import (
    ExecutionContext,
    get_current_context,
    set_current_context,
    reset_current_context,
    resolve_run_id,
    resolve_identity,
)
from src.observability.unified_logger import (
    log_agent_action,
    log_tool_call,
    log_human_review,
)
from src.observability.tracing import ExecutionTracer
from src.state import assert_state_invariants, create_initial_state
from mcp_server.client import MCPClient


def test_correlated_run_and_session_id():
    """Verifies that a single run produces correlated MCP, tool, audit, and trace records with matching IDs."""
    test_run_id = "RUN-PHASE3-CORRELATION-001"
    test_session_id = "SESS-PHASE3-CORRELATION-001"
    test_app_id = "APP-TEST-CORRELATION"

    ctx = ExecutionContext(
        run_id=test_run_id,
        session_id=test_session_id,
        application_id=test_app_id,
        step_id="step-correlation-check",
    )
    token = set_current_context(ctx)

    try:
        # 1. Audit log
        action_rec = log_agent_action(
            actor="test_correlation_actor",
            action="evaluate_identity",
            tool="identity_verifier",
            decision="VALIDATED",
            details={"check": "correlation"},
        )
        assert action_rec["run_id"] == test_run_id
        assert action_rec["session_id"] == test_session_id
        assert action_rec["application_id"] == test_app_id

        # 2. Tool call log
        tool_rec = log_tool_call(
            agent="test_agent",
            tool_name="test_tool",
            args={"query": "test"},
            result={"status": "ok"},
            latency_ms=12.5,
            attempt=1,
        )
        assert tool_rec["run_id"] == test_run_id
        assert tool_rec["session_id"] == test_session_id
        assert tool_rec["application_id"] == test_app_id

        # 3. Trace span
        tracer = ExecutionTracer(project_name="phase3-test")
        span = tracer.record_span(
            name="test_span",
            span_kind="acting",
            start_time=100.0,
            end_time=100.05,
            inputs={"input": 1},
            outputs={"output": 2},
        )
        assert span["run_id"] == test_run_id
        assert span["session_id"] == test_session_id

        # 4. MCP tool execution
        mcp_res = MCPClient.call_compute_affordability(
            income_amount=5000.0,
            income_period="monthly",
            existing_obligations=[{"amount": 1500.0, "period": "monthly"}],
            dti_max_threshold=0.40,
        )
        assert mcp_res.get("dti") == 0.3

        # Verify mcp_transcript.jsonl contains matching run_id and session_id
        mcp_log = Path("logs/mcp_transcript.jsonl")
        assert mcp_log.exists()
        last_mcp_record = json.loads(mcp_log.read_text(encoding="utf-8").strip().splitlines()[-1])
        assert last_mcp_record["run_id"] == test_run_id
        assert last_mcp_record["session_id"] == test_session_id
        assert last_mcp_record["application_id"] == test_app_id

    finally:
        reset_current_context(token)


def test_missing_run_id_fails_loudly():
    """Verifies that consequential operations fail loudly when run_id is missing or prohibited."""
    # Ensure no ambient context is active
    assert get_current_context() is None

    # resolve_run_id fails if required
    with pytest.raises(ValueError, match="Missing mandatory canonical run_id"):
        resolve_run_id(None, required=True)

    with pytest.raises(ValueError, match="Missing mandatory canonical run_id"):
        resolve_run_id("default_run", required=True)

    with pytest.raises(ValueError, match="Missing mandatory canonical run_id"):
        resolve_run_id("RUN-MCP", required=True)

    with pytest.raises(ValueError, match="Missing mandatory canonical run_id"):
        resolve_run_id("RUN-UNKNOWN", required=True)

    # resolve_identity fails if required
    with pytest.raises(ValueError, match="Missing mandatory canonical run_id"):
        resolve_identity(required=True)

    # ExecutionContext constructor rejects prohibited values
    with pytest.raises(ValueError, match="Invalid or prohibited run_id"):
        ExecutionContext(run_id="default_run", session_id="SESS-1", application_id="APP-1")

    with pytest.raises(ValueError, match="Invalid or prohibited run_id"):
        ExecutionContext(run_id="RUN-MCP", session_id="SESS-1", application_id="APP-1")

    with pytest.raises(ValueError, match="Invalid or prohibited run_id"):
        ExecutionContext(run_id="RUN-UNKNOWN", session_id="SESS-1", application_id="APP-1")

    with pytest.raises(ValueError, match="Invalid or prohibited session_id"):
        ExecutionContext(run_id="RUN-VALID-1", session_id="default-session", application_id="APP-1")

    # State invariant checks reject missing/prohibited run_id
    with pytest.raises(AssertionError, match="Invalid or missing canonical run_id"):
        assert_state_invariants({"run_id": "default_run"})

    with pytest.raises(AssertionError, match="Invalid or missing canonical run_id"):
        assert_state_invariants({"run_id": ""})

    with pytest.raises(AssertionError, match="Invalid or missing canonical run_id"):
        assert_state_invariants({"run_id": "RUN-UNKNOWN"})

    with pytest.raises(AssertionError, match="Invalid or missing canonical run_id"):
        assert_state_invariants({"run_id": "RUN-MCP"})

    # Consequential agent node functions fail loudly if run_id is missing
    from src.agents.eligibility_agent import eligibility_agent_node
    from src.agents.decision_agent import decision_agent_node
    from src.agents.policy_agent import policy_agent_node
    from src.agents.risk_agent import risk_agent_node

    with pytest.raises(ValueError, match="requires.*canonical run_id"):
        eligibility_agent_node({"run_id": ""})

    with pytest.raises(ValueError, match="requires.*canonical run_id"):
        decision_agent_node({"run_id": "default_run"})

    with pytest.raises(ValueError, match="requires.*canonical run_id"):
        policy_agent_node({"run_id": "RUN-UNKNOWN"})

    with pytest.raises(ValueError, match="requires.*canonical run_id"):
        risk_agent_node({"run_id": None})


def test_tool_call_id_stable_across_retries():
    """Verifies that tool_call_id remains stable across retries while attempt increments (1 -> 2)."""
    test_run_id = f"RUN-PHASE3-RETRY-{uuid.uuid4().hex[:8].upper()}"
    test_session_id = f"SESS-PHASE3-RETRY-{uuid.uuid4().hex[:8].upper()}"
    fixed_tool_call_id = f"tc-calculate_dti-stable-{uuid.uuid4().hex[:8]}"

    # Attempt 1
    rec1 = log_tool_call(
        agent="mcp_client",
        tool_name="calculate_dti",
        args={"monthly_debt": 1000, "income": 4000},
        result={"error": "temporary timeout"},
        latency_ms=25.0,
        run_id=test_run_id,
        session_id=test_session_id,
        application_id="APP-RETRY-TEST",
        tool_call_id=fixed_tool_call_id,
        attempt=1,
    )

    # Attempt 2 (retry)
    rec2 = log_tool_call(
        agent="mcp_client",
        tool_name="calculate_dti",
        args={"monthly_debt": 1000, "income": 4000},
        result={"dti": 0.25},
        latency_ms=20.0,
        run_id=test_run_id,
        session_id=test_session_id,
        application_id="APP-RETRY-TEST",
        tool_call_id=fixed_tool_call_id,
        attempt=2,
    )

    assert rec1["tool_call_id"] == fixed_tool_call_id
    assert rec2["tool_call_id"] == fixed_tool_call_id
    assert rec1["attempt"] == 1
    assert rec2["attempt"] == 2
    assert rec1["run_id"] == rec2["run_id"] == test_run_id


def test_no_prohibited_identity_defaults_in_logged_records():
    """Verifies that newly generated logs contain zero prohibited identity defaults."""
    prohibited = {"default_run", "RUN-MCP", "RUN-UNKNOWN", "default-session"}

    run_id = "RUN-PHASE3-CLEAN-001"
    session_id = "SESS-PHASE3-CLEAN-001"
    app_id = "APP-PHASE3-CLEAN-001"

    ctx = ExecutionContext(run_id=run_id, session_id=session_id, application_id=app_id)
    token = set_current_context(ctx)

    try:
        r1 = log_agent_action(actor="clean_actor", action="clean_action", tool=None, decision="OK")
        r2 = log_tool_call(agent="clean_agent", tool_name="clean_tool", args={}, result={}, latency_ms=5.0)
        r3 = log_human_review(
            review_id=f"REV-CLEAN-{uuid.uuid4().hex[:8].upper()}",
            application_id=app_id,
            reviewer_id="USR-01",
            ai_recommendation="REFER",
            final_decision="APPROVE",
            review_reason="Clean verified",
        )

        for rec in [r1, r2, r3]:
            for field in ["run_id", "session_id"]:
                val = rec.get(field)
                assert val not in prohibited, f"Found prohibited {field}='{val}' in {rec}"
                assert val is not None

        # Verify create_initial_state produces canonical non-default IDs
        init_st = create_initial_state(app_id)
        assert init_st["run_id"] not in prohibited
        assert init_st["session_id"] not in prohibited
        assert init_st["run_id"].startswith("RUN-")
        assert init_st["session_id"].startswith("SESS-")
    finally:
        reset_current_context(token)


def test_session_vs_run_semantic_distinction():
    """Demonstrates that a multi-turn session maintains one session_id across distinct continuous run_ids."""
    session_id = "SESS-MULTITURN-APPLICANT-777"
    app_id = "APP-777"

    # Turn 1: Initial submission yielding clarification
    run_1 = "RUN-TURN-1-SUBMISSION"
    ctx_1 = ExecutionContext(run_id=run_1, session_id=session_id, application_id=app_id)
    assert ctx_1.session_id == session_id
    assert ctx_1.run_id == run_1

    # Turn 2: Applicant resumes session after clarification
    run_2 = "RUN-TURN-2-RESUME"
    ctx_2 = ExecutionContext(run_id=run_2, session_id=session_id, application_id=app_id)
    assert ctx_2.session_id == session_id
    assert ctx_2.run_id == run_2

    # Session ID persists; run ID is unique per continuous execution attempt
    assert ctx_1.session_id == ctx_2.session_id
    assert ctx_1.run_id != ctx_2.run_id
