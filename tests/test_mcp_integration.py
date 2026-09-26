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
    resource_reads = [l for l in lines if l.get("type") == "resource_read" and l.get("resource") == "policy_corpus://index"]
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
