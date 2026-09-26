"""
Span and data sanitizer for PII scrubbing.
Redacts income figures, account numbers, credit identifiers, emails, and phone numbers.
Per plan.md Section 6.1 & 6.2.
"""

import re
from typing import Any, Dict, List, Union


# Common PII regex patterns
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
PHONE_PATTERN = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
ACCOUNT_PATTERN = re.compile(r"\b(?:ACC-?|AC-?|acc-?|\d{4}-)\d{4,12}\b")
CREDIT_ID_PATTERN = re.compile(r"\b(?:CR-?|cr-?|PAN-?|pan-?)[A-Z0-9]{8,12}\b")

# Sensitive key names to redact or mask
SENSITIVE_KEYS = {
    "income_amount",
    "raw_income",
    "account_number",
    "account_no",
    "credit_id",
    "pan_number",
    "ssn",
    "phone",
    "email",
    "bank_account",
}


def sanitize_text(text: str) -> str:
    """Redacts PII patterns from raw string text."""
    if not isinstance(text, str):
        return str(text)

    sanitized = text
    sanitized = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", sanitized)
    sanitized = PHONE_PATTERN.sub("[REDACTED_PHONE]", sanitized)
    sanitized = ACCOUNT_PATTERN.sub("[REDACTED_ACCOUNT]", sanitized)
    sanitized = CREDIT_ID_PATTERN.sub("[REDACTED_CREDIT_ID]", sanitized)

    return sanitized


SYSTEM_ID_KEYS = {
    "review_id",
    "run_id",
    "session_id",
    "application_id",
    "chunk_id",
    "rule_id",
    "source_file",
    "type",
    "status",
    "actor",
    "action",
    "tool_name",
    "timestamp",
    "step_id",
    "tool_call_id",
    "final_decision",
    "ai_recommendation",
    "decision",
}


def sanitize_data(data: Any) -> Any:
    """Recursively traverses dictionaries, lists, and primitives to mask sensitive fields."""
    if isinstance(data, dict):
        sanitized_dict = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if k_lower in SENSITIVE_KEYS:
                # Mask value
                sanitized_dict[k] = "[REDACTED_SENSITIVE]"
            elif k_lower in SYSTEM_ID_KEYS:
                sanitized_dict[k] = v
            else:
                sanitized_dict[k] = sanitize_data(v)
        return sanitized_dict
    elif isinstance(data, list):
        return [sanitize_data(item) for item in data]
    elif isinstance(data, str):
        return sanitize_text(data)
    else:
        return data
