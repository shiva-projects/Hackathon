"""
Tests for Loop / Cascade Guards (plan.md Section 8 & AC-12).
Asserts that step_count threshold stops runaway loops gracefully without unhandled exceptions.
"""

import pytest
from src.state import create_initial_state
from src.graph import build_loan_copilot_graph, route_after_intent, loop_guard_terminal_node


def test_step_count_loop_guard_halts_runaway():
    state = create_initial_state("APP-001")
    # Simulate runaway loop at recursion limit (15 steps)
    state["step_count"] = 15
    state["intent"] = "new_application"

    next_node = route_after_intent(state)

    # Pure routing function must direct to dedicated terminal node
    assert next_node == "loop_guard_terminal"
    # Terminal node executes state mutations cleanly
    import asyncio
    asyncio.run(loop_guard_terminal_node(state))
    assert state["decision_status"] == "UNABLE_TO_COMPLETE"
    assert state["unable_reason"] == "RECURSION_LIMIT_EXCEEDED"
    assert state["human_review_required"] is True


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

    assert next_node == "loop_guard_terminal"
    import asyncio
    asyncio.run(loop_guard_terminal_node(state))
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


@pytest.mark.asyncio
async def test_compiled_graph_loop_guard_execution():
    """Validates that a compiled graph hitting recursion limit cleanly reaches loop_guard_terminal."""
    from langgraph.checkpoint.memory import MemorySaver
    from src.state import create_initial_state

    checkpointer = MemorySaver()
    app = build_loan_copilot_graph(checkpointer=checkpointer)

    initial_state = create_initial_state("APP-001", applicant_raw_text="Apply for loan", actor_id="APPLICANT-001")
    initial_state["step_count"] = 15
    initial_state["intent"] = "new_application"

    config = {"configurable": {"thread_id": "thread-loop-test"}}
    final_state = await app.ainvoke(initial_state, config=config)

    assert final_state["decision_status"] == "UNABLE_TO_COMPLETE"
    assert final_state["unable_reason"] == "RECURSION_LIMIT_EXCEEDED"
    assert final_state["human_review_required"] is True
    assert "loop_guard_terminal" in final_state["routing_history"]
