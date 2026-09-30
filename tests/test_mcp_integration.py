"""
Tests for MCP Server integration & causal load-bearing proof (plan.md Section 13.4).
Asserts:
- Tool 1 (get_policy_document) invoked and logged
- Tool 2 (compute_affordability) invoked and logged
- Resource (policy_corpus://index) read and logged
- Selector candidates match the resource manifest keys (causal chain)
"""

import json
from pathlib import Path
import pytest
from mcp_server.client import MCPClient
from src.policy.policy_selector import select_applicable_policy


def test_mcp_resource_read_and_causal_selector_chain():
    # 1. Read resource via MCP
    manifest = MCPClient.read_resource_manifest()
    assert "policies" in manifest
    assert len(manifest["policies"]) > 0

    # 2. Selector consumes manifest directly
    selection = select_applicable_policy(
        product="personal_loan",
        jurisdiction="IN",
        application_date="2026-05-15",
        resource_manifest=manifest,
    )
    assert selection.is_success
    assert selection.policy["policy_id"] == "PL-001"

    # Causal chain proof per Section 13.4
    assert selection.policy["policy_id"] in [p["policy_id"] for p in manifest["policies"].values()]
    assert set(selection.candidate_ids) == set(manifest["policies"].keys())

    # 3. Verify logs/mcp_transcript.jsonl contains resource_read
    transcript_path = Path("logs/mcp_transcript.jsonl")
    assert transcript_path.exists()
    lines = [json.loads(line) for line in transcript_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    resource_reads = [l for l in lines if l.get("type") == "resource_read" and l.get("resource") in ("policy-corpus://index", "policy_corpus://index")]
    assert len(resource_reads) > 0


def test_mcp_tool_get_policy_document():
    doc_res = MCPClient.call_get_policy_document("PL-001", "v2.0")
    assert "policy_id" in doc_res
    assert doc_res["policy_id"] == "PL-001"
    assert "content" in doc_res
    assert len(doc_res["content"]) > 0

    # Verify tool call logged
    lines = [json.loads(line) for line in Path("logs/mcp_transcript.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    tool_calls = [l for l in lines if l.get("tool_name") == "get_policy_document"]
    assert len(tool_calls) > 0


def test_mcp_tool_compute_affordability():
    aff_res = MCPClient.call_compute_affordability(
        income_amount=100000,
        income_period="monthly",
        existing_obligations=[{"amount": 35000, "period": "monthly"}],
        dti_max_threshold=0.40,
    )
    assert aff_res["dti"] == 0.35
    assert aff_res["breach"] is False
    assert aff_res["disposable_income"] == 65000.0

    # Verify tool call logged
    lines = [json.loads(line) for line in Path("logs/mcp_transcript.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    tool_calls = [l for l in lines if l.get("tool_name") == "compute_affordability"]
    assert len(tool_calls) > 0


@pytest.mark.asyncio
async def test_mcp_success_normal_workflow_continues():
    from src.state import create_initial_state
    from src.agents.policy_agent import apolicy_agent_node
    from src.agents.eligibility_agent import aeligibility_agent_node
    from src.agents.supervisor import supervisor_router

    state = create_initial_state(
        application_id="APP-MCP-OK-01",
        run_id="RUN-MCP-OK",
        applicant_facts={
            "product": "personal_loan",
            "jurisdiction": "IN",
            "application_date": "2026-05-15",
            "income_amount": 100000.0,
            "income_period": "monthly",
            "existing_obligations": [{"amount": 25000.0, "period": "monthly"}],
            "requested_amount": 200000.0,
            "credit_score": 750,
        },
    )

    state = await apolicy_agent_node(state)
    assert state.get("decision_status") != "UNABLE_TO_COMPLETE"
    assert state["policy_selected"]["policy_id"] == "PL-001"

    next_node = supervisor_router(state)
    assert next_node == "eligibility_agent"

    state = await aeligibility_agent_node(state)
    assert state.get("decision_status") != "UNABLE_TO_COMPLETE"
    assert state["affordability"]["dti"] == 0.25
    assert state["affordability"]["breach"] is False

    next_node = supervisor_router(state)
    assert next_node == "risk_agent"


@pytest.mark.asyncio
async def test_mcp_timeout_retry_unable_to_complete(monkeypatch):
    from src.state import create_initial_state
    from src.agents.eligibility_agent import aeligibility_agent_node
    from src.agents.supervisor import supervisor_router
    from mcp_server.client import MCPSessionPool
    import asyncio

    attempts = 0

    async def mock_execute_tool(tool_name, args, session_id=None):
        nonlocal attempts
        attempts += 1
        raise asyncio.TimeoutError("MCP tool execution timed out after 10.0s")

    monkeypatch.setattr(MCPSessionPool.get_instance(), "execute_tool", mock_execute_tool)

    state = create_initial_state(
        application_id="APP-MCP-TIMEOUT",
        run_id="RUN-MCP-TIMEOUT",
        applicant_facts={
            "income_amount": 100000.0,
            "income_period": "monthly",
            "existing_obligations": [],
        },
    )
    state["routing_history"].append("policy_agent")

    state = await aeligibility_agent_node(state)

    assert state["decision_status"] == "UNABLE_TO_COMPLETE"
    assert state["unable_reason"] == "MCP_UNAVAILABLE"
    assert state["human_review_required"] is True
    assert state["ai_recommendation"] is None
    assert supervisor_router(state) == "__end__"


@pytest.mark.asyncio
async def test_mcp_connection_failure_retry_unable_to_complete(monkeypatch):
    from src.state import create_initial_state
    from src.agents.eligibility_agent import aeligibility_agent_node
    from src.agents.supervisor import supervisor_router
    from mcp_server.client import MCPSessionPool

    attempts = 0

    async def mock_execute_tool(tool_name, args, session_id=None):
        nonlocal attempts
        attempts += 1
        raise ConnectionResetError("MCP transport connection reset by peer")

    monkeypatch.setattr(MCPSessionPool.get_instance(), "execute_tool", mock_execute_tool)

    state = create_initial_state(
        application_id="APP-MCP-CONN-ERR",
        run_id="RUN-MCP-CONN-ERR",
        applicant_facts={
            "income_amount": 80000.0,
            "income_period": "monthly",
            "existing_obligations": [],
        },
    )
    state["routing_history"].append("policy_agent")

    state = await aeligibility_agent_node(state)

    assert state["decision_status"] == "UNABLE_TO_COMPLETE"
    assert state["unable_reason"] == "MCP_UNAVAILABLE"
    assert state["human_review_required"] is True
    assert state["ai_recommendation"] is None
    assert supervisor_router(state) == "__end__"


@pytest.mark.asyncio
async def test_mcp_resource_unavailable_unable_to_complete(monkeypatch):
    from src.state import create_initial_state
    from src.agents.policy_agent import apolicy_agent_node
    from src.agents.supervisor import supervisor_router
    from mcp_server.client import MCPClient, MCPUnavailableError

    def mock_read_resource_manifest():
        raise MCPUnavailableError("MCP policy resource stream unavailable")

    monkeypatch.setattr(MCPClient, "read_resource_manifest", mock_read_resource_manifest)

    state = create_initial_state(
        application_id="APP-MCP-RES-UNAVAIL",
        run_id="RUN-MCP-RES-UNAVAIL",
        applicant_facts={
            "product": "personal_loan",
            "jurisdiction": "IN",
            "application_date": "2026-05-15",
        },
    )

    state = await apolicy_agent_node(state)

    assert state["decision_status"] == "UNABLE_TO_COMPLETE"
    assert "MCP" in state.get("unable_reason", "")
    assert state["human_review_required"] is True
    assert supervisor_router(state) == "__end__"


def test_no_direct_server_function_invoked_when_transport_fails(monkeypatch):
    from unittest.mock import MagicMock
    import mcp_server.server as server_mod
    from mcp_server.client import MCPSessionPool, MCPUnavailableError

    spy_compute = MagicMock()
    spy_get_doc = MagicMock()
    spy_get_index = MagicMock()

    monkeypatch.setattr(server_mod, "compute_affordability", spy_compute)
    monkeypatch.setattr(server_mod, "get_policy_document", spy_get_doc)
    monkeypatch.setattr(server_mod, "get_policy_corpus_index", spy_get_index)

    async def failing_execute(tool_name, args, session_id=None):
        raise ConnectionRefusedError("Transport down")

    async def failing_read(uri, session_id=None):
        raise ConnectionRefusedError("Transport down")

    pool = MCPSessionPool.get_instance()
    monkeypatch.setattr(pool, "execute_tool", failing_execute)
    monkeypatch.setattr(pool, "read_resource", failing_read)

    with pytest.raises(MCPUnavailableError):
        MCPClient.call_compute_affordability(100000.0, "monthly", [])

    with pytest.raises(MCPUnavailableError):
        MCPClient.call_get_policy_document("PL-001", "v2.0")

    with pytest.raises(MCPUnavailableError):
        MCPClient.read_resource_manifest()

    spy_compute.assert_not_called()
    spy_get_doc.assert_not_called()
    spy_get_index.assert_not_called()

