"""
Deterministic Policy Rule Evaluator and Risk Screener.
Per plan.md Section 4.4, 13.8 & 14.11.
NO LLM CALLS HERE.
"""

from decimal import Decimal
from typing import List, Dict, Any, Tuple
from src.domain.models import RuleEvaluationResult, RuleType, AffordabilityResult
from src.domain.calculations import to_decimal, compare_threshold


def evaluate_policy_rules(
    applicant_facts: Dict[str, Any],
    policy_rules: List[Dict[str, Any]],
    affordability: AffordabilityResult,
) -> Tuple[List[RuleEvaluationResult], List[Dict[str, Any]]]:
    """
    Evaluates policy rules against applicant facts and affordability results.
    Returns:
        (rule_results, risk_flags)
    """
    rule_results: List[RuleEvaluationResult] = []
    risk_flags: List[Dict[str, Any]] = []

    monthly_income = affordability.monthly_gross_income
    requested_amount = to_decimal(applicant_facts.get("requested_amount", 0))
    tenure_months = int(applicant_facts.get("tenure_months", 0))
    employment = str(applicant_facts.get("employment", "")).lower()
    provided_docs = set(applicant_facts.get("documents", []))

    # Evaluate each rule from the selected policy
    for rule in policy_rules:
        rule_id = rule.get("rule_id", "UNKNOWN")
        rule_type = rule.get("rule_type")
        raw_val = rule.get("value")
        operator = rule.get("operator", "<=")

        if rule_type == RuleType.DTI_MAX.value:
            threshold = to_decimal(raw_val)
            dti_ratio = affordability.dti
            passed = compare_threshold(dti_ratio, threshold, operator)
            rule_results.append(
                RuleEvaluationResult(
                    rule_id=rule_id,
                    rule_type=rule_type,
                    passed=passed,
                    threshold_value=float(threshold),
                    actual_value=float(dti_ratio),
                    operator=operator,
                    message=f"DTI {float(dti_ratio):.1%} {'satisfies' if passed else 'breaches'} threshold {float(threshold):.1%}",
                    is_mandatory_eligibility=False,
                    requires_human_review=not passed,
                )
            )
            if not passed:
                risk_flags.append({
                    "rule_id": rule_id,
                    "flag": "DTI_BREACH",
                    "severity": "HIGH",
                    "message": f"DTI {float(dti_ratio):.1%} breaches policy maximum {float(threshold):.1%}",
                })

        elif rule_type == RuleType.MINIMUM_INCOME.value:
            threshold = to_decimal(raw_val)
            passed = compare_threshold(monthly_income, threshold, operator)
            rule_results.append(
                RuleEvaluationResult(
                    rule_id=rule_id,
                    rule_type=rule_type,
                    passed=passed,
                    threshold_value=float(threshold),
                    actual_value=float(monthly_income),
                    operator=operator,
                    message=f"Monthly income {monthly_income} {'meets' if passed else 'fails'} minimum {threshold}",
                    is_mandatory_eligibility=True,
                )
            )
            if not passed:
                risk_flags.append({
                    "rule_id": rule_id,
                    "flag": "MINIMUM_INCOME_NOT_MET",
                    "severity": "HIGH",
                    "message": f"Monthly income {monthly_income} below required minimum {threshold}",
                })

        elif rule_type == RuleType.LOAN_AMOUNT_MAX.value:
            threshold = to_decimal(raw_val)
            passed = compare_threshold(requested_amount, threshold, operator)
            rule_results.append(
                RuleEvaluationResult(
                    rule_id=rule_id,
                    rule_type=rule_type,
                    passed=passed,
                    threshold_value=float(threshold),
                    actual_value=float(requested_amount),
                    operator=operator,
                    message=f"Requested amount {requested_amount} {'is within' if passed else 'exceeds'} maximum {threshold}",
                    is_mandatory_eligibility=False,
                    requires_human_review=not passed,
                )
            )
            if not passed:
                risk_flags.append({
                    "rule_id": rule_id,
                    "flag": "LOAN_AMOUNT_EXCEEDED",
                    "severity": "HIGH",
                    "message": f"Requested amount {requested_amount} exceeds maximum allowed {threshold}",
                })

        elif rule_type == RuleType.HIGH_VALUE_REVIEW.value:
            threshold = to_decimal(raw_val)
            # High-value trigger: if requested_amount >= threshold, mandatory human review required
            is_high_value = compare_threshold(requested_amount, threshold, ">=")
            rule_results.append(
                RuleEvaluationResult(
                    rule_id=rule_id,
                    rule_type=rule_type,
                    passed=not is_high_value,
                    threshold_value=float(threshold),
                    actual_value=float(requested_amount),
                    operator=operator,
                    message=f"Loan amount {requested_amount} {'triggers' if is_high_value else 'does not trigger'} high-value review (threshold: {threshold})",
                    requires_human_review=is_high_value,
                )
            )
            if is_high_value:
                risk_flags.append({
                    "rule_id": rule_id,
                    "flag": "HIGH_VALUE_LOAN",
                    "severity": "MEDIUM",
                    "message": f"Loan amount {requested_amount} requires enhanced human review threshold {threshold}",
                })

        elif rule_type == RuleType.REQUIRED_DOCUMENT.value:
            req_doc = str(raw_val)
            has_doc = req_doc in provided_docs
            rule_results.append(
                RuleEvaluationResult(
                    rule_id=rule_id,
                    rule_type=rule_type,
                    passed=has_doc,
                    threshold_value=req_doc,
                    actual_value=list(provided_docs),
                    operator="contains",
                    message=f"Required document '{req_doc}' is {'present' if has_doc else 'MISSING'}",
                    is_mandatory_eligibility=True,
                )
            )
            if not has_doc:
                risk_flags.append({
                    "rule_id": rule_id,
                    "flag": "MISSING_MANDATORY_DOCUMENT",
                    "severity": "CRITICAL",
                    "message": f"Mandatory document missing: {req_doc}",
                })

        elif rule_type == RuleType.MINIMUM_TENURE.value:
            threshold_int = int(raw_val)
            passed = tenure_months >= threshold_int
            rule_results.append(
                RuleEvaluationResult(
                    rule_id=rule_id,
                    rule_type=rule_type,
                    passed=passed,
                    threshold_value=threshold_int,
                    actual_value=tenure_months,
                    operator=operator,
                    message=f"Tenure {tenure_months} months {'meets' if passed else 'fails'} minimum {threshold_int}",
                    is_mandatory_eligibility=True,
                )
            )
            if not passed:
                risk_flags.append({
                    "rule_id": rule_id,
                    "flag": "TENURE_BELOW_MINIMUM",
                    "severity": "HIGH",
                    "message": f"Tenure {tenure_months} months is below minimum {threshold_int}",
                })

        else:
            # Unknown rule_type must fail closed (plan.md Section 4.4 & compliance regulations)
            rule_results.append(
                RuleEvaluationResult(
                    rule_id=rule_id,
                    rule_type=rule_type or "unknown",
                    passed=False,
                    threshold_value=str(raw_val),
                    actual_value=None,
                    operator=operator,
                    message=f"Unknown or unsupported rule_type '{rule_type}' cannot be verified",
                    is_mandatory_eligibility=True,
                    requires_human_review=True,
                )
            )
            risk_flags.append({
                "rule_id": rule_id,
                "flag": "UNKNOWN_RULE_TYPE",
                "severity": "CRITICAL",
                "message": f"Policy rule [{rule_id}] has unknown rule_type '{rule_type}' - failing closed",
            })

    # Additional deterministic risk screening
    if employment in {"unemployed", "jobless", "not_employed", "un-employed", "none"}:
        risk_flags.append({
            "rule_id": "SYS-RISK-01",
            "flag": "UNEMPLOYMENT_FLAG",
            "severity": "CRITICAL",
            "message": "Applicant is currently unemployed",
        })

    # Currency consistency check
    app_currency = str(applicant_facts.get("currency", "INR")).upper()
    jurisdiction = str(applicant_facts.get("jurisdiction", "IN")).upper()
    if jurisdiction == "IN" and app_currency not in {"INR", ""}:
        risk_flags.append({
            "rule_id": "SYS-RISK-CURRENCY",
            "flag": "CURRENCY_MISMATCH",
            "severity": "HIGH",
            "message": f"Currency {app_currency} does not match jurisdiction {jurisdiction} (expected INR)",
        })

    return rule_results, risk_flags
