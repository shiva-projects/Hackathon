"""
Risk Screening Agent Worker Node.
Evaluates deterministic credit risk rules and policy compliance.
Per plan.md Section 4.4 & AC-02.
"""

from decimal import Decimal
from src.state import LoanState
from src.domain.models import AffordabilityResult
from src.domain.rules import evaluate_policy_rules
from src.observability.unified_logger import log_agent_action


def risk_agent_node(state: LoanState) -> LoanState:
    """
    LangGraph node: Evaluates risk rules against applicant facts and affordability results.
    """
    facts = state.get("applicant_facts", {})
    policy_selected = state.get("policy_selected", {})
    rules = policy_selected.get("rules", [])
    aff_dict = state.get("affordability", {})

    affordability = AffordabilityResult(
        dti=Decimal(str(aff_dict.get("dti", "0.0"))),
        disposable_income=Decimal(str(aff_dict.get("disposable_income", "0.0"))),
        breach=bool(aff_dict.get("breach", False)),
        threshold=Decimal(str(aff_dict.get("threshold", "0.40"))) if aff_dict.get("threshold") is not None else None,
        monthly_gross_income=Decimal(str(aff_dict.get("monthly_gross_income", "0.0"))),
        monthly_obligations=Decimal(str(aff_dict.get("monthly_obligations", "0.0"))),
    )

    rule_results, risk_flags = evaluate_policy_rules(facts, rules, affordability)

    state["risk_flags"] = risk_flags
    # Save serializable rule evaluations in state for decision node
    state["rule_evaluations"] = [r.model_dump() for r in rule_results]
    state["routing_history"].append("risk_agent")
    state["step_count"] += 1

    log_agent_action(
        actor="risk_agent",
        action="screened_risk_rules",
        tool="domain.rules.evaluate_policy_rules",
        decision=f"{len(risk_flags)} flags raised",
        application_id=state.get("application_id"),
        details={"risk_count": len(risk_flags), "flags": risk_flags},
    )
    return state
