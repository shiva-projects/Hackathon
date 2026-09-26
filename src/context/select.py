"""
Context Selection module.
Selects strictly necessary state fields per agent, pruning irrelevant or dangerous fields.
Per plan.md Section 13.10.
"""

from typing import Dict, Any, List, Set
from src.state import LoanState

AGENT_ALLOWED_CONTEXT: Dict[str, Set[str]] = {
    "policy_agent": {"product", "jurisdiction", "application_date", "policy_selected", "policy_citations"},
    "eligibility_agent": {"income_amount", "income_period", "monthly_gross_income", "existing_obligations", "policy_selected"},
    "risk_agent": {"affordability", "risk_flags", "policy_citations", "employment", "tenure_months", "documents"},
    "rationale_agent": {"ai_recommendation", "affordability", "risk_flags", "policy_citations", "policy_selected", "reasons"},
}


def select_agent_context(agent_name: str, state: LoanState) -> Dict[str, Any]:
    """
    Extracts a filtered, scoped context dictionary for the target agent.
    Applicant raw text and other agents' private scratch data are strictly excluded.
    """
    allowed_keys = AGENT_ALLOWED_CONTEXT.get(agent_name, set())

    # Build context from applicant_facts and state fields
    combined = {**state.get("applicant_facts", {}), **state}

    selected = {}
    excluded = []

    for k, v in combined.items():
        if k in allowed_keys:
            selected[k] = v
        else:
            excluded.append(k)

    # Ensure applicant_raw_text is NEVER included in selected context
    assert "applicant_raw_text" not in selected, f"Raw applicant text leaked into {agent_name} context!"

    return {
        "node": agent_name,
        "selected_context": selected,
        "context_selected": list(selected.keys()),
        "context_excluded": excluded,
    }
