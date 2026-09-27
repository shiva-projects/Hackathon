"""
Regression test suite for P0.1 Centralized Financial & PII Sanitization.
Ensures income, obligations, account numbers, and credit identifiers are never logged in plaintext.
Per plan.md Section 6.1, 6.2, NFR-05 & AC-06.
"""

import pytest
from src.observability.span_sanitizer import sanitize_data, sanitize_text, is_presidio_active, SENSITIVE_KEYS


def test_sensitive_financial_dict_redaction():
    payload = {
        "application_id": "APP-100",
        "actor": "underwriter",
        "income": 150000,
        "income_amount": 150000,
        "monthly_gross_income": 12500,
        "monthly_obligations": 3000,
        "disposable_income": 9500,
        "credit_identifier": "CR-9988776655",
        "nested": {
            "account_number": "ACC-12345678",
            "pan_number": "ABCDE1234F",
            "salary": 100000,
            "public_metric": "0.35_dti",
        },
        "obligations_list": [
            {"existing_obligations": 1200, "note": "car loan"},
            {"amount": 500, "description": "credit card payment to ACC-88889999"},
        ],
    }

    clean = sanitize_data(payload)

    # Identifiers and operational keys preserved
    assert clean["application_id"] == "APP-100"
    assert clean["actor"] == "underwriter"
    assert clean["nested"]["public_metric"] == "0.35_dti"

    # Sensitive financial fields masked
    assert clean["income"] == "[REDACTED_SENSITIVE]"
    assert clean["income_amount"] == "[REDACTED_SENSITIVE]"
    assert clean["monthly_gross_income"] == "[REDACTED_SENSITIVE]"
    assert clean["monthly_obligations"] == "[REDACTED_SENSITIVE]"
    assert clean["disposable_income"] == "[REDACTED_SENSITIVE]"
    assert clean["credit_identifier"] == "[REDACTED_SENSITIVE]"
    assert clean["nested"]["account_number"] == "[REDACTED_SENSITIVE]"
    assert clean["nested"]["pan_number"] == "[REDACTED_SENSITIVE]"
    assert clean["nested"]["salary"] == "[REDACTED_SENSITIVE]"

    # List items sanitized
    assert clean["obligations_list"][0]["existing_obligations"] == "[REDACTED_SENSITIVE]"
    assert "[REDACTED_ACCOUNT]" in clean["obligations_list"][1]["description"]


def test_sanitize_text_patterns():
    raw_text = "Applicant email test@example.com, phone +1-555-123-4567, account ACC-987654321, credit CR-12345678."
    clean = sanitize_text(raw_text)

    assert "test@example.com" not in clean
    assert "[REDACTED_EMAIL]" in clean
    assert "+1-555-123-4567" not in clean
    assert "[REDACTED_PHONE]" in clean
    assert "ACC-987654321" not in clean
    assert "[REDACTED_ACCOUNT]" in clean
    assert "CR-12345678" not in clean
    assert "[REDACTED_CREDIT_ID]" in clean


def test_presidio_status_function():
    # Calling is_presidio_active() must return a boolean without throwing an error
    active = is_presidio_active()
    assert isinstance(active, bool)
