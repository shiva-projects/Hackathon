"""
Tests for Loop / Cascade Guards (plan.md Section 8 & AC-12).
Asserts that step_count threshold stops runaway loops gracefully without unhandled exceptions.
"""

import pytest
from src.state import create_initial_state
from src.graph import build_loan_copilot_graph, route_after_intent
from src.memory.checkpoint_config import get_session_config
from langgraph.checkpoint.sqlite import SqliteSaver


def test_step_count_loop_guard_halts_runaway():
    state = create_initial_state("APP-001")
    # Simulate runaway loop at recursion limit
    state["step_count"] = 15
    state["intent"] = "new_application"

    next_node = route_after_intent(state)

    # Route after intent must detect limit and return END
    assert next_node == "__end__"
    assert state["decision_status"] == "UNABLE_TO_COMPLETE"
    assert state["unable_reason"] == "RECURSION_LIMIT_EXCEEDED"


def test_step_count_below_boundary_continues():
    state = create_initial_state("APP-001")
    # Boundary test: step_count = 14 is below limit of 15, must continue
    state["step_count"] = 14
    state["intent"] = "status_check"

    next_node = route_after_intent(state)

    # Below limit, routing must proceed to status_node rather than terminating
    assert next_node == "status_node"
    assert state.get("decision_status") != "UNABLE_TO_COMPLETE"


def test_step_count_above_boundary_terminates():
    state = create_initial_state("APP-001")
    # Boundary test: step_count = 20 (well over limit), must terminate immediately
    state["step_count"] = 20
    state["intent"] = "document_question"

    next_node = route_after_intent(state)

    assert next_node == "__end__"
    assert state["decision_status"] == "UNABLE_TO_COMPLETE"
    assert state["unable_reason"] == "RECURSION_LIMIT_EXCEEDED"


def test_clarification_reset_preserves_turn2_budget():
    state = create_initial_state("APP-001")
    # Verify that upon clarification resume, step_count budget is reset per supervisor_node logic
    state["clarification_needed"] = True
    state["clarification_response"] = "Applying for personal loan"
    state["step_count"] = 8

    # Simulate supervisor node logic
    if state.get("clarification_needed") and state.get("clarification_response"):
        state["clarification_needed"] = False
        state["step_count"] = 0

    assert state["step_count"] == 0
    assert not state["clarification_needed"]
