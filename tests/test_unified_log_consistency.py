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


def test_verifier_check_unified_log_consistency_passes_on_current_logs():
    from scripts.verify_evidence import check_unified_log_consistency
    passed, msg = check_unified_log_consistency()
    assert passed is True
    assert "verified at record level" in msg


def test_same_count_mismatched_event_id_fails(tmp_path):
    """
    Acceptance: component X event_id=E1 vs unified event_id=E2 must fail
    even if both files contain the exact same number of records.
    """
    from scripts.verify_evidence import check_unified_log_consistency
    comp_file = tmp_path / "tool_calls.jsonl"
    unif_file = tmp_path / "unified_trace.jsonl"

    rec_comp = {
        "event_id": "E1",
        "timestamp": "2026-09-30T10:00:00+00:00",
        "run_id": "RUN-001",
        "tool_call_id": "TC-001",
        "attempt": 1,
        "tool_name": "compute_affordability",
    }
    rec_unif = {
        "event_id": "E2",  # Mismatched identity
        "timestamp": "2026-09-30T10:00:00+00:00",
        "run_id": "RUN-001",
        "tool_call_id": "TC-001",
        "attempt": 1,
        "tool_name": "compute_affordability",
        "source_log": "logs/tool_calls.jsonl",
    }

    comp_file.write_text(json.dumps(rec_comp) + "\n", encoding="utf-8")
    unif_file.write_text(json.dumps(rec_unif) + "\n", encoding="utf-8")

    passed, msg = check_unified_log_consistency(logs_dir=tmp_path)
    assert passed is False
    assert "Record identity reconciliation failure" in msg
    assert "E1" in msg


def test_same_count_mismatched_run_id_fails(tmp_path):
    from scripts.verify_evidence import check_unified_log_consistency
    comp_file = tmp_path / "tool_calls.jsonl"
    unif_file = tmp_path / "unified_trace.jsonl"

    rec_comp = {
        "event_id": "E1",
        "timestamp": "2026-09-30T10:00:00+00:00",
        "run_id": "RUN-ACTUAL",
        "tool_call_id": "TC-001",
        "attempt": 1,
    }
    rec_unif = {
        "event_id": "E1",
        "timestamp": "2026-09-30T10:00:00+00:00",
        "run_id": "RUN-MISMATCHED",
        "tool_call_id": "TC-001",
        "attempt": 1,
        "source_log": "logs/tool_calls.jsonl",
    }

    comp_file.write_text(json.dumps(rec_comp) + "\n", encoding="utf-8")
    unif_file.write_text(json.dumps(rec_unif) + "\n", encoding="utf-8")

    passed, msg = check_unified_log_consistency(logs_dir=tmp_path)
    assert passed is False
    assert "run_id mismatch" in msg


def test_same_count_mismatched_tool_call_id_or_attempt_fails(tmp_path):
    from scripts.verify_evidence import check_unified_log_consistency
    comp_file = tmp_path / "tool_calls.jsonl"
    unif_file = tmp_path / "unified_trace.jsonl"

    rec_comp = {
        "event_id": "E1",
        "timestamp": "2026-09-30T10:00:00+00:00",
        "run_id": "RUN-001",
        "tool_call_id": "TC-001",
        "attempt": 1,
    }
    rec_unif = {
        "event_id": "E1",
        "timestamp": "2026-09-30T10:00:00+00:00",
        "run_id": "RUN-001",
        "tool_call_id": "TC-002",  # Mismatch
        "attempt": 2,  # Mismatch
        "source_log": "logs/tool_calls.jsonl",
    }

    comp_file.write_text(json.dumps(rec_comp) + "\n", encoding="utf-8")
    unif_file.write_text(json.dumps(rec_unif) + "\n", encoding="utf-8")

    passed, msg = check_unified_log_consistency(logs_dir=tmp_path)
    assert passed is False
    assert "tool_call_id mismatch" in msg


def test_same_count_mismatched_review_id_fails(tmp_path):
    from scripts.verify_evidence import check_unified_log_consistency
    comp_file = tmp_path / "human_reviews.jsonl"
    unif_file = tmp_path / "unified_trace.jsonl"

    rec_comp = {
        "event_id": "E-REV",
        "timestamp": "2026-09-30T10:00:00+00:00",
        "run_id": "RUN-001",
        "review_id": "REV-REAL",
    }
    rec_unif = {
        "event_id": "E-REV",
        "timestamp": "2026-09-30T10:00:00+00:00",
        "run_id": "RUN-001",
        "review_id": "REV-TAMPERED",
        "source_log": "logs/human_reviews.jsonl",
    }

    comp_file.write_text(json.dumps(rec_comp) + "\n", encoding="utf-8")
    unif_file.write_text(json.dumps(rec_unif) + "\n", encoding="utf-8")

    passed, msg = check_unified_log_consistency(logs_dir=tmp_path)
    assert passed is False
    assert "review_id mismatch" in msg


def test_unparseable_timestamp_fails(tmp_path):
    from scripts.verify_evidence import check_unified_log_consistency
    comp_file = tmp_path / "tool_calls.jsonl"
    unif_file = tmp_path / "unified_trace.jsonl"

    rec_comp = {
        "event_id": "E1",
        "timestamp": "NOT-A-VALID-ISO-TIMESTAMP",
        "run_id": "RUN-001",
        "tool_call_id": "TC-001",
    }
    rec_unif = {
        "event_id": "E1",
        "timestamp": "NOT-A-VALID-ISO-TIMESTAMP",
        "run_id": "RUN-001",
        "tool_call_id": "TC-001",
        "source_log": "logs/tool_calls.jsonl",
    }

    comp_file.write_text(json.dumps(rec_comp) + "\n", encoding="utf-8")
    unif_file.write_text(json.dumps(rec_unif) + "\n", encoding="utf-8")

    passed, msg = check_unified_log_consistency(logs_dir=tmp_path)
    assert passed is False
    assert "Unparseable timestamp" in msg

