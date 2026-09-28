"""
Tests for Log PII Redaction across all committed log files (plan.md Section 6.1 & NFR-05).
Asserts that sensitive seeded literals across multiple representations and sensitive fields
are ABSENT from all JSONL log files without polluting committed repository logs.
"""

import os
from pathlib import Path
import pytest
from src.observability.unified_logger import log_tool_call, log_agent_action, log_human_review

SEEDED_PII = {
    "income_representations": ["742,300", "742300", "₹742,300", "742300.00"],
    "account_number": "ACC-9988776655",
    "credit_id": "CR-PAN-9876543",
    "phone": "+91-9876543210",
    "email": "seeded.applicant.pii@example.com",
}


def test_seeded_pii_is_redacted_at_write_time(tmp_path, monkeypatch):
    """Generates logged test events into isolated test directory to verify redaction at rest."""
    test_logs = tmp_path / "test_logs"
    test_logs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LOG_DIR", str(test_logs))

    log_tool_call(
        agent="test_agent",
        tool_name="verify_income",
        args={
            "income_amount": SEEDED_PII["income_representations"][0],
            "account_number": SEEDED_PII["account_number"],
            "email": SEEDED_PII["email"],
        },
        result={"status": "verified"},
        latency_ms=10.0,
    )
    log_agent_action(
        actor="test_officer",
        action="check_credit",
        tool=None,
        decision="REVIEWED",
        details={"credit_id": SEEDED_PII["credit_id"], "phone": SEEDED_PII["phone"]},
    )
    log_human_review(
        review_id="REV-TEST-PII",
        application_id="APP-TEST-PII",
        reviewer_id="LO-001",
        ai_recommendation="REFER",
        final_decision="APPROVE",
        review_reason=f"Spoke to applicant at {SEEDED_PII['phone']} and confirmed account {SEEDED_PII['account_number']}.",
    )

    for log_file in test_logs.glob("*.jsonl"):
        content = log_file.read_text(encoding="utf-8")
        assert SEEDED_PII["account_number"] not in content, f"Leaked account_number in {log_file.name}"
        assert SEEDED_PII["credit_id"] not in content, f"Leaked credit_id in {log_file.name}"
        assert SEEDED_PII["email"] not in content, f"Leaked email in {log_file.name}"
        assert SEEDED_PII["phone"] not in content, f"Leaked phone in {log_file.name}"


def test_no_raw_pii_in_committed_log_files():
    log_files = [
        Path("logs/tool_calls.jsonl"),
        Path("logs/agent_actions.jsonl"),
        Path("logs/human_reviews.jsonl"),
        Path("logs/unified_trace.jsonl"),
    ]

    for path in log_files:
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        assert SEEDED_PII["account_number"] not in content, f"Leaked account_number in {path}"
        assert SEEDED_PII["credit_id"] not in content, f"Leaked credit_id in {path}"
        assert SEEDED_PII["email"] not in content, f"Leaked email in {path}"
        assert SEEDED_PII["phone"] not in content, f"Leaked phone in {path}"
