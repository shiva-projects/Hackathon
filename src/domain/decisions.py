"""
Deterministic Underwriting Decision Engine.
The SOLE WRITER of ai_recommendation, per plan.md Section 3.2 & 4.4.
NO LLM CALLS HERE.
"""

from typing import List, Dict, Any, Optional
from src.domain.models import (
    AffordabilityResult,
    RuleEvaluationResult,
    UnderwritingDecisionResult,
    RecommendationType,
)


def evaluate_underwriting_decision(
    affordability: AffordabilityResult,
    rule_results: List[RuleEvaluationResult],
    risk_flags: List[Dict[str, Any]],
) -> UnderwritingDecisionResult:
    """
    Combines affordability, rule results, and risk flags into an AI recommendation
    following the strict precedence order locked in plan.md Section 4.4:

    1. IF mandatory eligibility rule fails (missing doc, income, tenure, max loan exceeded)
       -> DECLINE
    2. ELSE IF high-risk flag fires (critical or high severity risk, e.g. unemployment)
       -> REFER
    3. ELSE IF high-value-review policy rule fires
       -> REFER
    4. ELSE IF DTI or affordability threshold breaches
       -> REFER
    5. ELSE
       -> APPROVE
    """
    reasons: List[str] = []

    # Check 1: Mandatory eligibility failures -> DECLINE
    failed_mandatory = [r for r in rule_results if r.is_mandatory_eligibility and not r.passed]
    for f in failed_mandatory:
        reasons.append(f"Failed mandatory eligibility rule [{f.rule_id}]: {f.message}")

    # Check 2: High/critical risk flags -> REFER
    high_risks = [rf for rf in risk_flags if rf.get("severity") in {"CRITICAL", "HIGH"} and rf.get("flag") != "DTI_BREACH"]
    for hr in high_risks:
        reasons.append(f"High risk detected [{hr.get('flag')}]: {hr.get('message')}")

    # Check 3: High value loan review rule -> REFER
    high_value_rule = next((r for r in rule_results if r.rule_type == "high_value_review" and r.requires_human_review), None)
    if high_value_rule:
        reasons.append(f"High value loan requires underwriter review [{high_value_rule.rule_id}]: {high_value_rule.message}")

    # Check 4: DTI or Affordability breach -> REFER
    if affordability.breach:
        threshold_pct = f"{float(affordability.threshold):.1%}" if affordability.threshold else "N/A"
        reasons.append(f"DTI {float(affordability.dti):.1%} exceeds policy threshold {threshold_pct}")

    # Apply strict precedence locked in plan.md Section 4.4:
    # 1. Mandatory eligibility failure -> DECLINE
    # 2. Risk flags / high value / DTI breach -> REFER
    # 3. All rules satisfied -> APPROVE
    if failed_mandatory:
        recommendation = RecommendationType.DECLINE.value
        human_review = True
    elif high_risks or high_value_rule or affordability.breach:
        recommendation = RecommendationType.REFER.value
        human_review = True
    else:
        recommendation = RecommendationType.APPROVE.value
        human_review = False
        reasons.append(f"Application satisfies all eligibility, risk, and affordability criteria (DTI: {float(affordability.dti):.1%}).")

    return UnderwritingDecisionResult(
        ai_recommendation=recommendation,
        decision_status="DETERMINED",
        unable_reason=None,
        human_review_required=human_review,
        affordability=affordability,
        rule_results=rule_results,
        risk_flags=risk_flags,
        reasons=reasons,
    )


def create_unable_to_complete_decision(
    reason: str,
    affordability: Optional[AffordabilityResult] = None,
) -> UnderwritingDecisionResult:
    """
    Constructs an explicit UNABLE_TO_COMPLETE decision state for system/infrastructure failures.
    Per plan.md Section 14.7.
    """
    if affordability is None:
        from decimal import Decimal
        affordability = AffordabilityResult(
            dti=Decimal("0.0"),
            disposable_income=Decimal("0.0"),
            breach=False,
            threshold=None,
            monthly_gross_income=Decimal("0.0"),
            monthly_obligations=Decimal("0.0"),
        )
    return UnderwritingDecisionResult(
        ai_recommendation=None,  # MUST BE NONE on system failures
        decision_status="UNABLE_TO_COMPLETE",
        unable_reason=reason,
        human_review_required=True,
        affordability=affordability,
        rule_results=[],
        risk_flags=[{"flag": "SYSTEM_UNAVAILABLE", "severity": "HIGH", "message": reason}],
        reasons=[f"Underwriting unable to complete: {reason}"],
    )
