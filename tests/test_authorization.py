"""
Tests for Authorization boundaries (plan.md Section 14.1).
Uses the concrete fixture table:
- LO-001 -> APP-001, APP-004
- LO-002 -> APP-002
- APPLICANT-001 -> APP-001 only
- APPLICANT-002 -> APP-002 only
"""

import pytest
from src.security.authorization import authorize


def test_authorized_loan_officer_allowed():
    assert authorize("LO-001", "APP-001") == "AUTHORIZED"
    assert authorize("LO-001", "APP-004") == "AUTHORIZED"
    assert authorize("LO-002", "APP-002") == "AUTHORIZED"


def test_unauthorized_loan_officer_denied():
    # LO-002 is not assigned to APP-001
    assert authorize("LO-002", "APP-001") == "DENIED"


def test_applicant_self_access_allowed():
    assert authorize("APPLICANT-001", "APP-001") == "AUTHORIZED"
    assert authorize("APPLICANT-002", "APP-002") == "AUTHORIZED"


def test_cross_applicant_access_denied():
    # APPLICANT-001 requesting APP-002 must be strictly denied
    assert authorize("APPLICANT-001", "APP-002") == "DENIED"


def test_spoofed_or_unknown_id_denied():
    assert authorize("UNKNOWN_ATTACKER", "APP-001") == "DENIED"
    assert authorize("LO-001", "NON_EXISTENT_APP") == "DENIED"
