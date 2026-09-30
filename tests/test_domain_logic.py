"""
Unit tests for deterministic domain calculations, rules, and decision precedence.
Plan.md Section 4.4, 14.14.
"""

from decimal import Decimal
import pytest
from src.domain.calculations import (
    calculate_monthly_gross_income,
    calculate_monthly_obligations,
    calculate_dti,
    calculate_disposable_income,
    compute_affordability,
)
from src.domain.rules import evaluate_policy_rules
from src.domain.decisions import evaluate_underwriting_decision, create_unable_to_complete_decision


def test_calculations_decimal_precision():
    # Annual income 1,200,000 -> 100,000 monthly
    monthly_inc = calculate_monthly_gross_income(Decimal("1200000"), "annual")
    assert monthly_inc == Decimal("100000.00")

    # Obligations: 25,000 monthly + 120,000 annual (10,000/mo) = 35,000
    obs = [
        {"amount": Decimal("25000"), "period": "monthly"},
        {"amount": Decimal("120000"), "period": "annual"},
    ]
    monthly_debts = calculate_monthly_obligations(obs)
    assert monthly_debts == Decimal("35000.00")

    # DTI = 35,000 / 100,000 = 0.35
    dti = calculate_dti(monthly_debts, monthly_inc)
    assert dti == Decimal("0.350000")

    # Disposable = 65,000
    disp = calculate_disposable_income(monthly_inc, monthly_debts)
    assert disp == Decimal("65000.00")


def test_affordability_breach_detection():
    # DTI 45% breaches 40% threshold
    affordability = compute_affordability(
        income_amount=Decimal("100000"),
        income_period="monthly",
        existing_obligations=[{"amount": Decimal("45000"), "period": "monthly"}],
        dti_max_threshold=Decimal("0.40"),
    )
    assert affordability.breach is True
    assert affordability.dti == Decimal("0.450000")

    # DTI 38% satisfies 40% threshold
    affordability_ok = compute_affordability(
        income_amount=Decimal("100000"),
        income_period="monthly",
        existing_obligations=[{"amount": Decimal("38000"), "period": "monthly"}],
        dti_max_threshold=Decimal("0.40"),
    )
    assert affordability_ok.breach is False


def test_decision_precedence_mandatory_failure_declines():
    # Even if DTI is great, missing required doc -> DECLINE
    affordability = compute_affordability(100000, "monthly", [], Decimal("0.40"))
    policy_rules = [
        {"rule_id": "PL-DOC", "rule_type": "required_document", "value": "income_statement"},
        {"rule_id": "PL-07", "rule_type": "dti_max", "value": 0.40, "operator": "<="},
    ]
    facts = {
        "requested_amount": 200000,
        "tenure_months": 24,
        "employment": "salaried",
        "documents": ["identity_proof"],  # missing income_statement
    }
    rule_results, risk_flags = evaluate_policy_rules(facts, policy_rules, affordability)
    decision = evaluate_underwriting_decision(affordability, rule_results, risk_flags)
    assert decision.ai_recommendation == "DECLINE"
    assert decision.human_review_required is True
    assert decision.decision_status == "DETERMINED"


def test_decision_precedence_dti_breach_refers():
    # Affordability breach -> REFER
    affordability = compute_affordability(100000, "monthly", [{"amount": 52000}], Decimal("0.40"))
    policy_rules = [
        {"rule_id": "PL-07", "rule_type": "dti_max", "value": 0.40, "operator": "<="},
        {"rule_id": "PL-DOC", "rule_type": "required_document", "value": "identity_proof"},
    ]
    facts = {
        "requested_amount": 200000,
        "tenure_months": 24,
        "employment": "salaried",
        "documents": ["identity_proof"],
    }
    rule_results, risk_flags = evaluate_policy_rules(facts, policy_rules, affordability)
    decision = evaluate_underwriting_decision(affordability, rule_results, risk_flags)
    assert decision.ai_recommendation == "REFER"
    assert decision.human_review_required is True


def test_decision_clean_approval():
    affordability = compute_affordability(100000, "monthly", [{"amount": 20000}], Decimal("0.40"))
    policy_rules = [
        {"rule_id": "PL-07", "rule_type": "dti_max", "value": 0.40, "operator": "<="},
        {"rule_id": "PL-DOC", "rule_type": "required_document", "value": "identity_proof"},
        {"rule_id": "PL-INC", "rule_type": "minimum_income", "value": 25000, "operator": ">="},
    ]
    facts = {
        "requested_amount": 300000,
        "tenure_months": 24,
        "employment": "salaried",
        "documents": ["identity_proof"],
    }
    rule_results, risk_flags = evaluate_policy_rules(facts, policy_rules, affordability)
    decision = evaluate_underwriting_decision(affordability, rule_results, risk_flags)
    assert decision.ai_recommendation == "APPROVE"
    assert decision.human_review_required is False


def test_unable_to_complete_decision_structure():
    decision = create_unable_to_complete_decision("MCP service unreachable")
    assert decision.ai_recommendation is None
    assert decision.decision_status == "UNABLE_TO_COMPLETE"
    assert decision.unable_reason == "MCP service unreachable"
    assert decision.human_review_required is True


def test_loan_amount_max_mandatory_failure_declines():
    """Phase 6: LOAN_AMOUNT_MAX is mandatory eligibility; breach must yield DECLINE."""
    affordability = compute_affordability(100000, "monthly", [], Decimal("0.40"))
    policy_rules = [
        {"rule_id": "PL-MAX", "rule_type": "loan_amount_max", "value": 1500000, "operator": "<="},
        {"rule_id": "PL-07", "rule_type": "dti_max", "value": 0.40, "operator": "<="},
        {"rule_id": "PL-DOC", "rule_type": "required_document", "value": "identity_proof"},
    ]
    # Requested 2,000,000 exceeds maximum allowed 1,500,000
    facts = {
        "requested_amount": 2000000,
        "tenure_months": 24,
        "employment": "salaried",
        "documents": ["identity_proof"],
    }
    rule_results, risk_flags = evaluate_policy_rules(facts, policy_rules, affordability)
    
    # Assert rule evaluation result has is_mandatory_eligibility=True and passed=False
    max_loan_eval = next(r for r in rule_results if r.rule_type == "loan_amount_max")
    assert max_loan_eval.passed is False
    assert max_loan_eval.is_mandatory_eligibility is True
    assert max_loan_eval.requires_human_review is True

    decision = evaluate_underwriting_decision(affordability, rule_results, risk_flags)
    assert decision.ai_recommendation == "DECLINE"
    assert decision.human_review_required is True
    assert any("loan_amount_max" in r.lower() or "exceeds maximum" in r.lower() for r in decision.reasons)


def test_high_risk_flag_alone_refers():
    """Phase 6: Critical/high risk flag (e.g. unemployment) alone must yield REFER."""
    affordability = compute_affordability(100000, "monthly", [], Decimal("0.40"))
    policy_rules = [
        {"rule_id": "PL-07", "rule_type": "dti_max", "value": 0.40, "operator": "<="},
        {"rule_id": "PL-DOC", "rule_type": "required_document", "value": "identity_proof"},
    ]
    facts = {
        "requested_amount": 200000,
        "tenure_months": 24,
        "employment": "unemployed",  # triggers UNEMPLOYMENT_FLAG
        "documents": ["identity_proof"],
    }
    rule_results, risk_flags = evaluate_policy_rules(facts, policy_rules, affordability)
    decision = evaluate_underwriting_decision(affordability, rule_results, risk_flags)
    assert decision.ai_recommendation == "REFER"
    assert decision.human_review_required is True
    assert any("UNEMPLOYMENT_FLAG" in r for r in decision.reasons)


def test_high_value_review_alone_refers():
    """Phase 6: High-value review policy trigger alone must yield REFER."""
    affordability = compute_affordability(100000, "monthly", [], Decimal("0.40"))
    policy_rules = [
        {"rule_id": "PL-MAX", "rule_type": "loan_amount_max", "value": 5000000, "operator": "<="},
        {"rule_id": "PL-HIGH", "rule_type": "high_value_review", "value": 1000000, "operator": "<"},
        {"rule_id": "PL-07", "rule_type": "dti_max", "value": 0.40, "operator": "<="},
        {"rule_id": "PL-DOC", "rule_type": "required_document", "value": "identity_proof"},
    ]
    facts = {
        "requested_amount": 1500000,  # >= 1,000,000 triggers high value review, within 5,000,000 max
        "tenure_months": 36,
        "employment": "salaried",
        "documents": ["identity_proof"],
    }
    rule_results, risk_flags = evaluate_policy_rules(facts, policy_rules, affordability)
    decision = evaluate_underwriting_decision(affordability, rule_results, risk_flags)
    assert decision.ai_recommendation == "REFER"
    assert decision.human_review_required is True
    assert any("High value loan" in r for r in decision.reasons)


def test_combinations_mandatory_failure_takes_precedence_over_dti_breach():
    """Phase 6: Multiple violations: Mandatory eligibility failure (max loan) + DTI breach -> DECLINE."""
    # DTI = 55% > 40% (affordability breach)
    affordability = compute_affordability(100000, "monthly", [{"amount": 55000}], Decimal("0.40"))
    assert affordability.breach is True

    policy_rules = [
        {"rule_id": "PL-MAX", "rule_type": "loan_amount_max", "value": 1500000, "operator": "<="},
        {"rule_id": "PL-07", "rule_type": "dti_max", "value": 0.40, "operator": "<="},
        {"rule_id": "PL-DOC", "rule_type": "required_document", "value": "identity_proof"},
    ]
    facts = {
        "requested_amount": 2500000,  # exceeds 1,500,000 max loan
        "tenure_months": 24,
        "employment": "salaried",
        "documents": ["identity_proof"],
    }
    rule_results, risk_flags = evaluate_policy_rules(facts, policy_rules, affordability)
    decision = evaluate_underwriting_decision(affordability, rule_results, risk_flags)
    
    # Precedence: mandatory failure MUST result in DECLINE, not REFER
    assert decision.ai_recommendation == "DECLINE"
    assert decision.human_review_required is True


def test_combinations_mandatory_failure_takes_precedence_over_high_risk():
    """Phase 6: Multiple violations: Missing document + Unemployed -> DECLINE."""
    affordability = compute_affordability(100000, "monthly", [], Decimal("0.40"))
    policy_rules = [
        {"rule_id": "PL-DOC", "rule_type": "required_document", "value": "income_statement"},
        {"rule_id": "PL-07", "rule_type": "dti_max", "value": 0.40, "operator": "<="},
    ]
    facts = {
        "requested_amount": 200000,
        "tenure_months": 24,
        "employment": "unemployed",  # high risk
        "documents": ["identity_proof"],  # missing income_statement
    }
    rule_results, risk_flags = evaluate_policy_rules(facts, policy_rules, affordability)
    decision = evaluate_underwriting_decision(affordability, rule_results, risk_flags)
    assert decision.ai_recommendation == "DECLINE"
    assert decision.human_review_required is True


def test_combinations_dti_breach_and_high_risk_refers():
    """Phase 6: DTI breach + High risk -> REFER."""
    affordability = compute_affordability(100000, "monthly", [{"amount": 50000}], Decimal("0.40"))
    assert affordability.breach is True

    policy_rules = [
        {"rule_id": "PL-07", "rule_type": "dti_max", "value": 0.40, "operator": "<="},
        {"rule_id": "PL-DOC", "rule_type": "required_document", "value": "identity_proof"},
    ]
    facts = {
        "requested_amount": 200000,
        "tenure_months": 24,
        "employment": "unemployed",
        "documents": ["identity_proof"],
    }
    rule_results, risk_flags = evaluate_policy_rules(facts, policy_rules, affordability)
    decision = evaluate_underwriting_decision(affordability, rule_results, risk_flags)
    assert decision.ai_recommendation == "REFER"
    assert decision.human_review_required is True
