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
    # Simulate runaway loop approaching recursion limit
    state["step_count"] = 15
    state["intent"] = "new_application"

    next_node = route_after_intent(state)

    # Route after intent must detect limit and return END
    assert next_node == "__end__"
    assert state["decision_status"] == "UNABLE_TO_COMPLETE"
    assert state["unable_reason"] == "RECURSION_LIMIT_EXCEEDED"
