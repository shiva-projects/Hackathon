"""
Checkpoint and Session Resume integration tests (plan.md Section 14.4).
Proves that SQLite checkpoints survive process restarts and can be resumed.
"""

from pathlib import Path
import pytest
from src.state import create_initial_state
from src.memory.checkpoint_config import get_checkpointer, get_session_config


def test_checkpoint_state_persists_and_resumes(tmp_path):
    db_file = tmp_path / "test_checkpoints.sqlite"
    checkpointer = get_checkpointer(str(db_file))

    session_id = "SESSION-TEST-RESUME-01"
    config = get_session_config(session_id)

    # 1. First run / process phase: populate state
    state = create_initial_state("APP-001", session_id=session_id)
    state["policy_selected"] = {"policy_id": "PL-001", "version": "v2.0"}
    state["routing_history"] = ["supervisor", "policy_agent", "eligibility_agent"]
    state["step_count"] = 3
    state["request_status"] = "IN_PROGRESS"

    from langgraph.checkpoint.base import empty_checkpoint
    chk = empty_checkpoint()
    chk["channel_values"] = {"state": state}

    # Save checkpoint
    saved_cfg = checkpointer.put(config, checkpoint=chk, metadata={"source": "test_phase1"}, new_versions={})

    # 2. Simulate process exit & restart: new checkpointer instance reading the same SQLite file
    new_checkpointer = get_checkpointer(str(db_file))
    checkpoint_tuple = new_checkpointer.get_tuple(saved_cfg)

    assert checkpoint_tuple is not None
    resumed_state = checkpoint_tuple.checkpoint["channel_values"]["state"]

    # 3. Assert preserved state across restart per Section 14.4
    assert resumed_state["application_id"] == "APP-001"
    assert resumed_state["policy_selected"]["version"] == "v2.0"
    assert resumed_state["routing_history"] == ["supervisor", "policy_agent", "eligibility_agent"]
    assert resumed_state["step_count"] == 3
    assert resumed_state["request_status"] == "IN_PROGRESS"
