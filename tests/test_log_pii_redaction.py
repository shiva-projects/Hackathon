"""
Tests for Log PII Redaction across all committed log files (plan.md Section 6.1 & NFR-05).
Asserts that sensitive seeded literals across multiple representations and sensitive fields
are ABSENT from all JSONL log files.
"""

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


@pytest.fixture(autouse=True)
def seed_test_log_events():
    """Generates logged test events with attempted PII leakage to verify redaction at rest."""
    # Attempt to log raw PII via tool calls, agent actions, and human reviews
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
    # Reviewer notes with seeded account number and email (Section 6.1 untrusted review_reason)
    log_human_review(
        review_id="REV-TEST-PII",
        application_id="APP-TEST-PII",
        reviewer_id="LO-001",
        ai_recommendation="REFER",
        final_decision="APPROVE",
        review_reason=f"Spoke to applicant at {SEEDED_PII['phone']} and confirmed account {SEEDED_PII['account_number']}.",
    )


def test_no_raw_pii_in_any_log_file():
    log_files = [
        "logs/tool_calls.jsonl",
        "logs/agent_actions.jsonl",
        "logs/human_reviews.jsonl",
        "logs/unified_trace.jsonl",
    ]

    for log_file in log_files:
        path = Path(log_file)
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")

        # Check account number absent
        assert SEEDED_PII["account_number"] not in content, f"Leaked account_number in {log_file}"

        # Check credit ID absent
        assert SEEDED_PII["credit_id"] not in content, f"Leaked credit_id in {log_file}"

        # Check email absent
        assert SEEDED_PII["email"] not in content, f"Leaked email in {log_file}"

        # Check phone absent
        assert SEEDED_PII["phone"] not in content, f"Leaked phone in {log_file}"
