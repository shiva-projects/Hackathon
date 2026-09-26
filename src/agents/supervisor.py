"""
LangGraph Supervisor Router.
Coordinates routing between specialized workers based on classified intent.
Per plan.md Section 4.1 & 4.3.
"""

from typing import Literal
from src.state import LoanState


def supervisor_router(state: LoanState) -> str:
    """
    Evaluates current state and returns the next node to execute.
    """
    intent = state.get("intent", "new_application")
    request_status = state.get("request_status")

    # If request was already refused or needs clarification, stop
    if request_status == "REFUSED":
        return "refusal_node"
    if state.get("clarification_needed"):
        return "clarification_node"

    # Route based on classified intent
    if intent == "ambiguous":
        return "clarification_node"
    elif intent in {"out_of_scope", "security_sensitive"}:
        return "refusal_node"
    elif intent == "status_check":
        return "status_node"
    elif intent == "document_question":
        return "document_node"
    elif intent == "policy_question":
        return "policy_agent"
    elif intent == "new_application":
        # Check underwriting worker progress
        history = state.get("routing_history", [])
        if "policy_agent" not in history:
            return "policy_agent"
        elif "eligibility_agent" not in history:
            return "eligibility_agent"
        elif "risk_agent" not in history:
            return "risk_agent"
        elif "decision_node" not in history:
            return "decision_node"
        else:
            return "__end__"
    else:
        return "__end__"
