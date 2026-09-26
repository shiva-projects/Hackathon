"""
Tool Contract tests (plan.md Section 8 & AC-12).
Asserts each tool's input and output schema plus one error path.
"""

import pytest
from mcp_server.client import MCPClient
from src.tools.rag_tool import retrieve_policy_chunks


def test_compute_affordability_contract_success():
    # Success path
    res = MCPClient.call_compute_affordability(
        income_amount=100000.0,
        income_period="monthly",
        existing_obligations=[{"amount": 30000.0, "period": "monthly"}],
        dti_max_threshold=0.40,
    )
    assert isinstance(res, dict)
    assert "dti" in res
    assert "disposable_income" in res
    assert "breach" in res
    assert res["dti"] == 0.3
    assert res["breach"] is False


def test_compute_affordability_contract_error_path():
    # Error path: zero income triggers ValueError
    with pytest.raises(ValueError, match="greater than zero"):
        MCPClient.call_compute_affordability(
            income_amount=0.0,
            income_period="monthly",
            existing_obligations=[],
        )


def test_get_policy_document_contract_success():
    res = MCPClient.call_get_policy_document("PL-001", "v2.0")
    assert isinstance(res, dict)
    assert res["policy_id"] == "PL-001"
    assert res["version"] == "v2.0"
    assert "metadata" in res
    assert "content" in res


def test_get_policy_document_contract_error_path():
    # Error path: non-existent policy version returns structured error
    res = MCPClient.call_get_policy_document("PL-UNKNOWN", "v99.0")
    assert "error" in res
    assert "not found" in res["error"].lower()


def test_rag_tool_contract():
    policy = {"policy_id": "PL-001", "version": "v2.0"}
    chunks = retrieve_policy_chunks("DTI maximum", selected_policy=policy, top_k=2)
    assert isinstance(chunks, list)
    assert len(chunks) > 0
    chunk = chunks[0]
    required_keys = {"policy_id", "version", "rule_id", "source_file", "chunk_id", "text_hash", "text"}
    assert required_keys.issubset(chunk.keys())
    assert chunk["policy_id"] == "PL-001"
    assert chunk["version"] == "v2.0"
