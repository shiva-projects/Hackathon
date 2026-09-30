"""
tests/test_async_behavior.py — Async correctness and resource hygiene tests (Phase 10).
Conforms strictly to Phase 10 acceptance criteria:
1. No process-wide stdlib monkeypatch remains for tracing cleanup.
2. Cleanup failures are visible and diagnosable.
3. No obvious blocking I/O/tool invocation remains inside async graph nodes.
4. Unnecessary ThreadPoolExecutor bridges are eliminated.
"""

import asyncio
import logging
import tempfile
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest

from src.state import create_initial_state
from src.domain.models import RuleEvaluationResult
from src.observability.tracing import safe_cleanup_temp_dir, shutdown_tracing
from src.agents.policy_agent import apolicy_agent_node, policy_agent_node
from src.agents.eligibility_agent import aeligibility_agent_node, eligibility_agent_node
from src.agents.risk_agent import arisk_agent_node, risk_agent_node
from src.agents.decision_agent import adecision_agent_node, decision_agent_node
from src.agents.intent_classifier import intent_classifier_node


def test_no_global_tempfile_cleanup_monkeypatch():
    """Verify that tempfile.TemporaryDirectory._cleanup is the standard library implementation."""
    import inspect
    cleanup_func = getattr(tempfile.TemporaryDirectory, "_cleanup", None)
    assert cleanup_func is not None
    # Inspect source or docstring — ensure it does not contain the suppressed exception patch
    source = inspect.getsource(cleanup_func)
    assert "_safe_cleanup" not in source
    assert "except Exception:\n            pass" not in source


def test_safe_cleanup_temp_dir_reports_diagnostics(caplog):
    """Verify that safe_cleanup_temp_dir makes cleanup failures visible and diagnosable."""
    mock_temp_dir = MagicMock()
    mock_temp_dir.cleanup.side_effect = PermissionError("Simulated locked file on Windows")

    with caplog.at_level(logging.WARNING):
        safe_cleanup_temp_dir(mock_temp_dir)

    assert "Failed to clean up temporary directory" in caplog.text
    assert "Simulated locked file on Windows" in caplog.text


def test_shutdown_tracing_runs_cleanly():
    """Verify shutdown_tracing executes without raising or requiring monkeypatches."""
    shutdown_tracing()


@pytest.mark.asyncio
async def test_async_nodes_run_as_native_coroutines():
    """Verify worker nodes are true coroutines that execute in an active event loop."""
    # 1. Eligibility agent
    state_elig = create_initial_state("APP-ASYNC-01", run_id="RUN-ASYNC-TEST-01")
    state_elig["applicant_facts"] = {
        "income_amount": 50000,
        "income_period": "monthly",
        "existing_obligations": [{"amount": 10000}],
        "requested_amount": 200000,
        "tenor_months": 24,
    }
    state_elig["policy_selected"] = {"policy_id": "PL-001", "version": "v2.0"}

    res_elig = await aeligibility_agent_node(state_elig)
    assert "affordability" in res_elig
    assert res_elig["affordability"]["dti"] > 0

    # 2. Risk agent
    state_risk = create_initial_state("APP-ASYNC-02", run_id="RUN-ASYNC-TEST-02")
    state_risk["affordability"] = {
        "dti": 0.20,
        "disposable_income": 40000.0,
        "breach": False,
        "threshold": 0.40,
    }
    state_risk["policy_selected"] = {"policy_id": "PL-001", "version": "v2.0"}

    res_risk = await arisk_agent_node(state_risk)
    assert "risk_flags" in res_risk

    # 3. Decision agent
    state_dec = create_initial_state("APP-ASYNC-03", run_id="RUN-ASYNC-TEST-03")
    state_dec["affordability"] = {
        "dti": 0.20,
        "disposable_income": 40000.0,
        "breach": False,
        "threshold": 0.40,
    }
    state_dec["_rule_results"] = [
        RuleEvaluationResult(
            rule_id="PL-07",
            rule_type="dti_max",
            passed=True,
            threshold_value=0.40,
            actual_value=0.20,
            operator="<=",
            message="DTI within limits",
            requires_human_review=False,
        ).model_dump()
    ]
    state_dec["risk_flags"] = []
    state_dec["policy_selected"] = {"policy_id": "PL-001", "version": "v2.0"}

    res_dec = await adecision_agent_node(state_dec)
    assert res_dec["decision_status"] == "DETERMINED"
    assert res_dec["request_status"] == "COMPLETED"
    assert res_dec["ai_recommendation"] == "APPROVE"


@pytest.mark.asyncio
async def test_intent_classifier_async_mem_tool_invocation(monkeypatch):
    """Verify intent_classifier_node uses async invocation for long_term memory tool."""
    state = create_initial_state("APP-ASYNC-INTENT", run_id="RUN-ASYNC-INTENT-01")
    state["applicant_raw_text"] = "What documents are required to apply for personal loan?"

    # Mock long-term memory tool with async ainvoke
    mock_tool = AsyncMock()
    mock_tool.name = "manage_memory"
    mock_tool.ainvoke = AsyncMock(return_value={"status": "async_invoked"})

    from src.memory.long_term import long_term_memory
    monkeypatch.setattr(long_term_memory, "get_langmem_tool", lambda app_id, ns: mock_tool)

    res = await intent_classifier_node(state)
    assert res["intent"] == "document_question"
    assert mock_tool.ainvoke.await_count == 1
