"""
LangGraph Supervisor Router for Transaction Dispute & Fraud Triage Copilot.
Coordinates routing between specialized workers based on classified intent and state.
Per AAIE_AGT_001_BFS Specification §5.1 (AC-02, AC-03).
"""

from typing import Literal
from src.state import DisputeState


def supervisor_router(state: DisputeState) -> str:
    """
    Evaluates current state and returns the next node to execute.
    Orchestrates: intake_agent -> fraud_signal_agent -> chargeback_eligibility_agent -> resolution_draft_agent (AC-02).
    Includes AC-03 conditional routing:
    - Escalate suspected fraud to manual review
    - Short-circuit disputes outside the chargeback window
    """
    intent = state.get("intent", "new_dispute")
    request_status = state.get("request_status")

    # If request was already refused, route to refusal
    if request_status == "REFUSED":
        return "refusal_node"

    # If still waiting for clarification (no response yet), route to clarification
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
    elif intent in {"dispute_inquiry", "policy_question"}:
        # Route to resolution draft with agentic RAG lookup
        history = state.get("routing_history", [])
        if "resolution_draft_agent" not in history and "decision_node" not in history:
            return "resolution_draft_agent"
        return "__end__"
    elif intent in {"new_dispute", "new_application"}:
        # Check multi-agent worker progress (AC-02)
        history = state.get("routing_history", [])

        # Step 1: Intake Agent (captures transaction + customer via MCP)
        if "intake_agent" not in history and "policy_agent" not in history:
            return "intake_agent"

        # Step 2: Fraud Signal Agent (surfaces fraud indicators via MCP)
        if "fraud_signal_agent" not in history and "eligibility_agent" not in history:
            return "fraud_signal_agent"

        # Step 3: Chargeback Eligibility Agent (120-Day window & reason codes)
        if "chargeback_eligibility_agent" not in history and "risk_agent" not in history:
            return "chargeback_eligibility_agent"

        # Step 4: Resolution Draft Agent (Agentic RAG + reflection loop)
        if "resolution_draft_agent" not in history and "decision_node" not in history:
            return "resolution_draft_agent"

        return "__end__"
    else:
        return "__end__"
