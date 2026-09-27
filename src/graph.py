"""
LangGraph Multi-Agent Architecture for Transaction Dispute & Fraud Triage Copilot.
Per AAIE_AGT_001_BFS Specification §5.1 (AC-01..AC-05, AC-12, NFR-02, NFR-04).
Implements Supervisor routing across specialized workers:
intake_agent -> fraud_signal_agent -> chargeback_eligibility_agent -> resolution_draft_agent.
Full Phoenix tracing instrumentation & load-bearing checkpointing (AC-05).
"""

import time
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END
from src.state import DisputeState, LoanState, assert_state_invariants
from src.guardrails.input_guard import screen_input
from src.security.authorization import authorize
from src.agents.intent_classifier import intent_classifier_node
from src.agents.supervisor import supervisor_router
from src.agents.clarification import clarification_node

# Specialized Dispute & Fraud Workers (AC-02)
from src.agents.intake_agent import intake_agent_node, aintake_agent_node
from src.agents.fraud_signal_agent import fraud_signal_agent_node, afraud_signal_agent_node
from src.agents.chargeback_eligibility_agent import chargeback_eligibility_agent_node, achargeback_eligibility_agent_node
from src.agents.resolution_draft_agent import resolution_draft_agent_node, aresolution_draft_agent_node

# Legacy imports for backward-compatible test calls
from src.agents.policy_agent import policy_agent_node, apolicy_agent_node
from src.agents.eligibility_agent import eligibility_agent_node, aeligibility_agent_node
from src.agents.risk_agent import risk_agent_node, arisk_agent_node
from src.agents.decision_agent import decision_agent_node, adecision_agent_node

from src.memory.checkpoint_config import get_checkpointer
from src.observability.tracing import tracer, traced_node
from src.observability.unified_logger import log_agent_action


async def input_guard_node(state: DisputeState) -> DisputeState:
    """Entry node: Screens input for prompt injection and isolates untrusted customer text (NFR-03)."""
    raw_text = state.get("dispute_raw_text") or state.get("applicant_raw_text", "")
    dispute_id = state.get("dispute_id") or state.get("application_id", "DSP-UNKNOWN")
    guard_result = screen_input(raw_text, current_application_id=dispute_id)

    state["routing_history"] = list(state.get("routing_history", [])) + ["input_guard"]
    state["step_count"] = state.get("step_count", 0) + 1

    if not guard_result.is_safe:
        state["request_status"] = "REFUSED"
        state["refusal_reason"] = guard_result.rejection_reason or "SECURITY_SENSITIVE_REQUEST"
        state["rationale"] = f"Request refused: {state['refusal_reason']}."
    return state


async def authorization_node(state: DisputeState) -> DisputeState:
    """Security node: Enforces access control boundaries."""
    state["routing_history"] = list(state.get("routing_history", [])) + ["authorization_node"]
    state["step_count"] = state.get("step_count", 0) + 1

    if state.get("request_status") == "REFUSED":
        return state

    requester_id = state.get("customer_id") or state.get("application_id", "")
    dispute_id = state.get("dispute_id") or state.get("application_id", "")

    auth_status = authorize(requester_id, dispute_id, run_id=state.get("session_id", "default_run"))
    if auth_status != "AUTHORIZED":
        state["request_status"] = "REFUSED"
        state["refusal_reason"] = "AUTHORIZATION_DENIED"
        state["rationale"] = f"Access denied: Requester '{requester_id}' is unauthorized for dispute '{dispute_id}'."
    return state


async def supervisor_node(state: DisputeState) -> DisputeState:
    """Supervisor coordinator node: central dispatch point for multi-agent execution (AC-02)."""
    start_t = time.time()

    # On clarification resume: clear the flag so routing continues to the worker pipeline
    if state.get("clarification_needed") and state.get("clarification_response"):
        state["clarification_needed"] = False
        state["step_count"] = 0

    state["routing_history"] = list(state.get("routing_history", [])) + ["supervisor"]
    state["step_count"] = state.get("step_count", 0) + 1

    latency_ms = round((time.time() - start_t) * 1000.0, 2)

    log_agent_action(
        actor="supervisor",
        action="supervisor_dispatch",
        tool="supervisor_router",
        decision=state.get("intent", "new_dispute"),
        latency_ms=latency_ms,
        details={"step_count": state.get("step_count"), "intent": state.get("intent")},
    )
    return state


async def status_node(state: DisputeState) -> DisputeState:
    """Handles status_check intent without modifying decision fields."""
    state["routing_history"] = list(state.get("routing_history", [])) + ["status_node"]
    state["step_count"] = state.get("step_count", 0) + 1
    state["request_status"] = "COMPLETED"
    disp_id = state.get("dispute_id") or state.get("application_id")
    state["rationale"] = (
        f"Dispute {disp_id} is currently {state.get('request_status')} with "
        f"action {state.get('resolution_action', 'PENDING_REVIEW')}."
    )
    return state


async def document_node(state: DisputeState) -> DisputeState:
    """Handles document_question intent explaining evidence requirements."""
    state["routing_history"] = list(state.get("routing_history", [])) + ["document_node"]
    state["step_count"] = state.get("step_count", 0) + 1
    state["request_status"] = "COMPLETED"
    state["rationale"] = (
        "Standard dispute evidence under card network rules includes itemized merchant receipts, "
        "cancellation notice emails, delivery tracking numbers, and police reports for stolen cards."
    )
    return state


async def refusal_node(state: DisputeState) -> DisputeState:
    """Terminal node for out_of_scope or security refusals."""
    state["routing_history"] = list(state.get("routing_history", [])) + ["refusal_node"]
    state["step_count"] = state.get("step_count", 0) + 1
    state["request_status"] = "REFUSED"
    if not state.get("refusal_reason"):
        state["refusal_reason"] = "OUT_OF_SCOPE"
    state["rationale"] = f"Request refused: {state.get('refusal_reason', 'OUT_OF_SCOPE')}."
    return state


# Routing conditionals
def route_after_input_guard(state: DisputeState) -> str:
    if state.get("request_status") == "REFUSED":
        return "refusal_node"
    return "authorization_node"


def route_after_authorization(state: DisputeState) -> str:
    if state.get("request_status") == "REFUSED":
        return "refusal_node"
    return "intent_classifier"


def route_from_supervisor(state: DisputeState) -> str:
    """Routes execution from supervisor to worker or termination."""
    # Loop/cascade guard (AC-01 / recursion limit)
    if state.get("step_count", 0) >= 20:
        state["request_status"] = "COMPLETED"
        state["rationale"] = "Process completed: execution reached recursion ceiling."
        return END

    target = supervisor_router(state)
    if target == "__end__":
        return END
    return target


def route_after_intent(state: DisputeState) -> str:
    return route_from_supervisor(state)


def build_dispute_copilot_graph(checkpointer: Any = None) -> StateGraph:
    """
    Assembles and compiles the full LangGraph Dispute & Fraud Triage Copilot state graph.
    Satisfies AC-01 (Typed state), AC-02 (Supervisor + Workers), AC-03 (Conditional edges), AC-05 (Checkpointing).
    """
    tracer.initialize()
    workflow = StateGraph(DisputeState)

    # Core Pipeline Nodes (AC-02)
    workflow.add_node("input_guard", traced_node("input_guard", "acting", input_guard_node))
    workflow.add_node("authorization_node", traced_node("authorization_node", "acting", authorization_node))
    workflow.add_node("intent_classifier", traced_node("intent_classifier", "thinking", intent_classifier_node))
    workflow.add_node("supervisor", traced_node("supervisor", "acting", supervisor_node))
    workflow.add_node("clarification_node", traced_node("clarification_node", "acting", clarification_node))
    workflow.add_node("status_node", traced_node("status_node", "acting", status_node))
    workflow.add_node("document_node", traced_node("document_node", "acting", document_node))
    workflow.add_node("refusal_node", traced_node("refusal_node", "acting", refusal_node))

    # Specialized Worker Agents (AC-02)
    workflow.add_node("intake_agent", traced_node("intake_agent", "acting", aintake_agent_node))
    workflow.add_node("fraud_signal_agent", traced_node("fraud_signal_agent", "acting", afraud_signal_agent_node))
    workflow.add_node("chargeback_eligibility_agent", traced_node("chargeback_eligibility_agent", "acting", achargeback_eligibility_agent_node))
    workflow.add_node("resolution_draft_agent", traced_node("resolution_draft_agent", "acting", aresolution_draft_agent_node))

    # Backward compatibility nodes for legacy tests
    workflow.add_node("policy_agent", traced_node("policy_agent", "acting", apolicy_agent_node))
    workflow.add_node("eligibility_agent", traced_node("eligibility_agent", "acting", aeligibility_agent_node))
    workflow.add_node("risk_agent", traced_node("risk_agent", "acting", arisk_agent_node))
    workflow.add_node("decision_node", traced_node("decision_node", "acting", adecision_agent_node))

    # Entry point
    workflow.set_entry_point("input_guard")

    # Edges
    workflow.add_conditional_edges("input_guard", route_after_input_guard, ["authorization_node", "refusal_node"])
    workflow.add_conditional_edges("authorization_node", route_after_authorization, ["intent_classifier", "refusal_node"])
    workflow.add_edge("intent_classifier", "supervisor")

    workflow.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        [
            "clarification_node",
            "refusal_node",
            "status_node",
            "document_node",
            "intake_agent",
            "fraud_signal_agent",
            "chargeback_eligibility_agent",
            "resolution_draft_agent",
            "policy_agent",
            "eligibility_agent",
            "risk_agent",
            "decision_node",
            END,
        ],
    )

    workflow.add_edge("clarification_node", END)
    workflow.add_edge("status_node", END)
    workflow.add_edge("document_node", END)
    workflow.add_edge("refusal_node", END)

    # Worker dispatch loops back to supervisor (AC-02)
    workflow.add_edge("intake_agent", "supervisor")
    workflow.add_edge("fraud_signal_agent", "supervisor")
    workflow.add_edge("chargeback_eligibility_agent", "supervisor")
    workflow.add_edge("resolution_draft_agent", "supervisor")

    # Legacy node loops
    workflow.add_edge("policy_agent", "supervisor")
    workflow.add_edge("eligibility_agent", "supervisor")
    workflow.add_edge("risk_agent", "supervisor")
    workflow.add_edge("decision_node", "supervisor")

    if checkpointer is None:
        checkpointer = get_checkpointer()

    return workflow.compile(checkpointer=checkpointer)


# Legacy alias
build_loan_copilot_graph = build_dispute_copilot_graph
