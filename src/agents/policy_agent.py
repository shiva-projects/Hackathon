"""
Policy Agent Worker Node.
Invokes deterministic policy selector and targeted RAG retrieval.
Per plan.md Section 4.2 & 7.1.
"""

from src.state import LoanState
from src.policy.policy_selector import select_applicable_policy
from src.tools.rag_tool import retrieve_policy_chunks
from src.observability.unified_logger import log_agent_action


def policy_agent_node(state: LoanState) -> LoanState:
    """
    LangGraph node: Selects current applicable policy and retrieves relevant chunks.
    """
    facts = state.get("applicant_facts", {})
    product = facts.get("product", "personal_loan")
    jurisdiction = facts.get("jurisdiction", "IN")
    app_date = facts.get("application_date", "2026-01-01")

    # 1. Deterministic policy selection
    selection = select_applicable_policy(product, jurisdiction, app_date)

    if not selection.is_success:
        state["decision_status"] = "UNABLE_TO_COMPLETE"
        state["unable_reason"] = selection.reason or "POLICY_UNAVAILABLE"
        state["human_review_required"] = True
        state["routing_history"].append("policy_agent_error")
        return state

    selected_policy = selection.policy
    state["policy_selected"] = selected_policy

    # 2. Targeted RAG retrieval within selected policy only
    query = f"{product} affordability DTI loan limits documents"
    citations = retrieve_policy_chunks(
        query=query,
        selected_policy=selected_policy,
        top_k=3,
        run_id=state.get("session_id", "default_run"),
    )
    state["policy_citations"] = citations
    state["routing_history"].append("policy_agent")
    state["step_count"] += 1

    log_agent_action(
        actor="policy_agent",
        action="selected_policy_and_citations",
        tool="policy_selector",
        decision=selected_policy["version"],
        application_id=state.get("application_id"),
        details={"policy_id": selected_policy["policy_id"], "version": selected_policy["version"]},
    )
    return state
