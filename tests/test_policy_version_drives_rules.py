"""
Integration test proving policy version selection directly drives deterministic rule results.
Plan.md Section 14.13.
Applicant has DTI = 42% (monthly income 100k, debt 42k).
Under Policy v2.0 (2026, DTI max 40%) -> REFER.
Under Policy v3.0 (2027, DTI max 45%) -> APPROVE.
"""

from decimal import Decimal
import pytest
from src.policy.policy_selector import select_applicable_policy
from src.domain.calculations import compute_affordability
from src.domain.rules import evaluate_policy_rules
from src.domain.decisions import evaluate_underwriting_decision


def test_policy_version_drives_rule_outcomes():
    applicant_facts = {
        "application_id": "APP-VERSION-DIFF",
        "product": "personal_loan",
        "jurisdiction": "IN",
        "income_amount": 100000,
        "income_period": "monthly",
        "requested_amount": 400000,
        "tenure_months": 24,
        "employment": "salaried",
        "existing_obligations": [{"amount": 42000, "period": "monthly"}],  # DTI = 0.42
        "documents": ["identity_proof", "income_statement"],
    }

    # 1. Run against 2026 date (selects v2.0, max DTI 0.40)
    policy_2026 = select_applicable_policy("personal_loan", "IN", "2026-06-01").policy
    dti_rule_2026 = next(r for r in policy_2026["rules"] if r["rule_type"] == "dti_max")
    affordability_2026 = compute_affordability(
        applicant_facts["income_amount"],
        applicant_facts["income_period"],
        applicant_facts["existing_obligations"],
        dti_max_threshold=dti_rule_2026["value"],
    )
    rule_results_2026, risk_2026 = evaluate_policy_rules(applicant_facts, policy_2026["rules"], affordability_2026)
    decision_2026 = evaluate_underwriting_decision(affordability_2026, rule_results_2026, risk_2026)

    # DTI 42% > 40% -> must REFER
    assert affordability_2026.breach is True
    assert decision_2026.ai_recommendation == "REFER"
    assert decision_2026.human_review_required is True

    # 2. Run against 2027 date (selects v3.0, max DTI 0.45)
    policy_2027 = select_applicable_policy("personal_loan", "IN", "2027-06-01").policy
    dti_rule_2027 = next(r for r in policy_2027["rules"] if r["rule_type"] == "dti_max")
    affordability_2027 = compute_affordability(
        applicant_facts["income_amount"],
        applicant_facts["income_period"],
        applicant_facts["existing_obligations"],
        dti_max_threshold=dti_rule_2027["value"],
    )
    rule_results_2027, risk_2027 = evaluate_policy_rules(applicant_facts, policy_2027["rules"], affordability_2027)
    decision_2027 = evaluate_underwriting_decision(affordability_2027, rule_results_2027, risk_2027)

    # DTI 42% <= 45% -> must APPROVE
    assert affordability_2027.breach is False
    assert decision_2027.ai_recommendation == "APPROVE"
    assert decision_2027.human_review_required is False
