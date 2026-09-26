"""
Tests for Output PII Redaction across multiple representations (plan.md Section 6.1 & NFR-05).
"""

import pytest
from src.guardrails.output_guard import screen_output


def test_output_redacts_email_and_phone():
    text = "Contact applicant at test.borrower@example.com or mobile +91-9876543210 regarding the review."
    sanitized = screen_output(text, ai_recommendation="REFER")
    assert "test.borrower@example.com" not in sanitized
    assert "9876543210" not in sanitized
    assert "[REDACTED_EMAIL]" in sanitized
    assert "[REDACTED_PHONE]" in sanitized


def test_output_redacts_bank_accounts():
    text = "Funds will be disbursed to account ACC-987654321 upon final approval."
    sanitized = screen_output(text, ai_recommendation="APPROVE")
    assert "ACC-987654321" not in sanitized
    assert "[REDACTED_ACCOUNT]" in sanitized


def test_output_redacts_multiple_income_representations():
    # Tested multiple representations of income per plan.md Section 6.1
    representations = ["742,300", "742300", "₹742,300", "742300.00"]
    for rep in representations:
        text = f"The borrower reports an annual salary of {rep} with monthly debt obligations."
        sanitized = screen_output(text, ai_recommendation="REFER", seeded_pii_literals=representations)
        assert rep not in sanitized
        assert "[REDACTED_PII]" in sanitized
