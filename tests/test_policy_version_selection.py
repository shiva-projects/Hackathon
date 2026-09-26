"""
Tests for deterministic policy version selection (plan.md Section 4.2).
Proves that application date determines policy version (v1 expired vs v2 current vs v3 future).
"""

import pytest
from src.policy.policy_selector import select_applicable_policy


def test_select_current_v2_policy():
    # 2026 application date must select v2.0
    result = select_applicable_policy(
        product="personal_loan",
        jurisdiction="IN",
        application_date="2026-06-15",
    )
    assert result.is_success
    assert result.policy["version"] == "v2.0"
    assert result.policy["policy_id"] == "PL-001"


def test_select_expired_v1_policy_for_2025_date():
    # 2025 application date must select v1.0
    result = select_applicable_policy(
        product="personal_loan",
        jurisdiction="IN",
        application_date="2025-08-20",
    )
    assert result.is_success
    assert result.policy["version"] == "v1.0"
    assert result.policy["policy_id"] == "PL-001"


def test_select_future_v3_policy_for_2027_date():
    # 2027 application date must select v3.0
    result = select_applicable_policy(
        product="personal_loan",
        jurisdiction="IN",
        application_date="2027-02-01",
    )
    assert result.is_success
    assert result.policy["version"] == "v3.0"
    assert result.policy["policy_id"] == "PL-001"


def test_no_applicable_policy_for_out_of_range_date():
    # 2024 date has no policy
    result = select_applicable_policy(
        product="personal_loan",
        jurisdiction="IN",
        application_date="2024-05-10",
    )
    assert not result.is_success
    assert result.status == "NO_APPLICABLE_POLICY"
    assert result.policy is None
