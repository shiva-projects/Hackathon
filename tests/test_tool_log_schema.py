"""
Schema enforcement tests for generated JSONL logs (plan.md Section 13.3).
Asserts that every record in logs/*.jsonl satisfies the required field schemas.
"""

import json
from pathlib import Path
import pytest


def test_tool_calls_log_schema():
    path = Path("logs/tool_calls.jsonl")
    if not path.exists():
        pytest.skip("logs/tool_calls.jsonl not yet generated")

    required_fields = {
        "timestamp",
        "agent",
        "tool_name",
        "args",
        "result",
        "latency_ms",
        "status",
        "run_id",
        "step_id",
        "tool_call_id",
        "attempt",
    }
    lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) > 0, "logs/tool_calls.jsonl is empty"

    for idx, line in enumerate(lines):
        record = json.loads(line)
        assert required_fields.issubset(record.keys()), (
            f"Line {idx+1} in logs/tool_calls.jsonl missing fields: {required_fields - set(record.keys())}"
        )


def test_mcp_transcript_log_schema():
    path = Path("logs/mcp_transcript.jsonl")
    if not path.exists():
        pytest.skip("logs/mcp_transcript.jsonl not yet generated")

    required_fields = {"timestamp", "run_id", "type", "caller"}
    lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) > 0, "logs/mcp_transcript.jsonl is empty"

    for idx, line in enumerate(lines):
        record = json.loads(line)
        assert required_fields.issubset(record.keys()), (
            f"Line {idx+1} in logs/mcp_transcript.jsonl missing fields: {required_fields - set(record.keys())}"
        )
