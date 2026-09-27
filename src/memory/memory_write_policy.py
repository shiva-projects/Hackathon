"""
Memory Write Policy Gate.
The single gate that long-term writes must pass through.
Ensures arbitrary applicant free-text or malicious 'SYSTEM: remember X' commands NEVER reach Tier 3 memory.
Per plan.md Section 6.3 & 13.11.
"""

from typing import Any, Dict, Optional, Tuple

# Approved structured schema keys allowed to persist in long-term semantic memory
APPROVED_LONG_TERM_KEYS = {
    "employment",
    "employment_type",
    "employer_name",
    "preferred_currency",
    "verified_identity",
    "previous_tenure_months",
    "account_tenure_years",
    # Dispute & Customer Profile memory attributes (AC-06, AC-08)
    "dispute_history_count",
    "preferred_channel",
    "customer_tier",
    "home_city",
    "primary_bank",
    "card_last4_primary",
}


def validate_long_term_fact(key: str, value: Any) -> Tuple[bool, Optional[str]]:
    """
    Validates whether a candidate fact is safe and permitted for long-term Tier 3 persistence:
    1. Key must belong to APPROVED_LONG_TERM_KEYS.
    2. Value must be primitive (str, int, float, bool) and not contain prompt injection markers.
    """
    clean_key = str(key).strip().lower()
    if clean_key not in APPROVED_LONG_TERM_KEYS:
        return False, f"Key '{key}' is not an approved long-term memory attribute"

    val_str = str(value)
    # Check for adversarial injection attempts
    forbidden_markers = ["system:", "ignore", "instructions", "override", "bypass", "remember forever"]
    for marker in forbidden_markers:
        if marker in val_str.lower():
            return False, f"Value contains suspicious adversarial marker: '{marker}'"

    if len(val_str) > 200:
        return False, "Value exceeds maximum allowed attribute length (200 chars)"

    return True, None
