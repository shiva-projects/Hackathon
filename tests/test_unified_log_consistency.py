"""
Consistency tests between per-concern logs and logs/unified_trace.jsonl (plan.md Section 7.5).
Proves that the unified trace contains every single record from per-concern logs with no orphan or missing records.
"""

import json
from pathlib import Path
import pytest


def test_every_source_record_appears_in_unified_log():
    unified_path = Path("logs/unified_trace.jsonl")
    if not unified_path.exists():
        pytest.skip("logs/unified_trace.jsonl does not exist yet")

    unified_lines = [json.loads(l) for l in unified_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    source_files = [
        "logs/tool_calls.jsonl",
        "logs/agent_actions.jsonl",
        "logs/mcp_transcript.jsonl",
        "logs/human_reviews.jsonl",
    ]

    for source_file in source_files:
        src_p = Path(source_file)
        if not src_p.exists():
            continue

        source_records = [json.loads(l) for l in src_p.read_text(encoding="utf-8").splitlines() if l.strip()]
        matching_unified = [u for u in unified_lines if u.get("source_log") == source_file]

        assert len(source_records) == len(matching_unified), (
            f"Record count mismatch for {source_file}: {len(source_records)} vs {len(matching_unified)} in unified trace"
        )

        # Assert all fields in source record match in unified record
        for s, u in zip(source_records, matching_unified):
            for k, v in s.items():
                assert u.get(k) == v, f"Field '{k}' mismatch between {source_file} and unified trace"


def test_unified_log_has_no_orphan_records():
    unified_path = Path("logs/unified_trace.jsonl")
    if not unified_path.exists():
        pytest.skip("logs/unified_trace.jsonl does not exist yet")

    valid_sources = {
        "logs/tool_calls.jsonl",
        "logs/agent_actions.jsonl",
        "logs/mcp_transcript.jsonl",
        "logs/human_reviews.jsonl",
    }

    for line in unified_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        assert record.get("source_log") in valid_sources, f"Orphan record with unknown source_log: {record.get('source_log')}"
