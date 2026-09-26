"""
Tests for product and jurisdiction applicability matching (plan.md Section 13.9).
Asserts that product/jurisdiction mismatches are correctly rejected.
"""

import pytest
from src.policy.policy_selector import select_applicable_policy


def test_product_jurisdiction_valid_match():
    # personal_loan in IN -> PL-001 v2.0
    result = select_applicable_policy("personal_loan", "IN", "2026-05-01")
    assert result.is_success
    assert result.policy["product"] == "personal_loan"
    assert result.policy["jurisdiction"] == "IN"


def test_uk_mortgage_valid_match():
    # mortgage in UK -> PL-MORT-UK-01
    result = select_applicable_policy("mortgage", "UK", "2026-05-01")
    assert result.is_success
    assert result.policy["product"] == "mortgage"
    assert result.policy["jurisdiction"] == "UK"


def test_product_mismatch_rejected():
    # personal_loan in UK -> no match
    result = select_applicable_policy("personal_loan", "UK", "2026-05-01")
    assert not result.is_success
    assert result.status == "NO_APPLICABLE_POLICY"


def test_jurisdiction_mismatch_rejected():
    # mortgage in IN -> no match
    result = select_applicable_policy("mortgage", "IN", "2026-05-01")
    assert not result.is_success
    assert result.status == "NO_APPLICABLE_POLICY"


def test_unsupported_product_rejected():
    # auto_loan -> no match
    result = select_applicable_policy("auto_loan", "IN", "2026-05-01")
    assert not result.is_success
    assert result.status == "NO_APPLICABLE_POLICY"
