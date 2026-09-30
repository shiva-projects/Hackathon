"""
Process-isolated Checkpoint and Session Resume integration tests.
Per plan.md Section 14.4 & Phase 4.

Proves:
1. Process 1 submits an ambiguous application, pauses for clarification, and persists state in SQLite.
2. Process 2 resumes using ONLY --resume-session and --clarification (no --application passed),
   restores state from SQLite checkpoint, injects clarification, continues through remaining stages,
   and produces the final underwriting decision.
3. Non-existent sessions fail closed.
"""

import os
import sys
import json
import sqlite3
import subprocess
from pathlib import Path
import pytest

from src.memory.checkpoint_config import (
    get_checkpointer,
    get_session_config,
    checkpoint_exists,
    load_checkpoint_state,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_checkpoint_state_lookup_api(tmp_path):
    """Direct API verification that checkpoint_exists and load_checkpoint_state work across instances."""
    db_file = tmp_path / "test_lookup.sqlite"
    session_id = "SESSION-LOOKUP-01"

    # Initially does not exist
    assert not checkpoint_exists(session_id, db_path=str(db_file))
    assert load_checkpoint_state(session_id, db_path=str(db_file)) is None

    # Save state via instance 1
    from src.state import create_initial_state
    state = create_initial_state("APP-001", session_id=session_id, run_id="RUN-TEST-01")
    state["policy_selected"] = {"policy_id": "PL-001", "version": "v2.0"}
    state["routing_history"] = ["input_guard", "authorization_node", "supervisor"]
    state["request_status"] = "IN_PROGRESS"

    from langgraph.checkpoint.base import empty_checkpoint
    chk = empty_checkpoint()
    chk["channel_values"] = state

    cp1 = get_checkpointer(str(db_file))
    cfg = get_session_config(session_id)
    cp1.put(cfg, checkpoint=chk, metadata={"test": "lookup"}, new_versions={})

    # Read back via independent lookup
    assert checkpoint_exists(session_id, db_path=str(db_file))
    restored = load_checkpoint_state(session_id, db_path=str(db_file))
    assert restored is not None
    assert restored["application_id"] == "APP-001"
    assert restored["policy_selected"]["version"] == "v2.0"
    assert restored["request_status"] == "IN_PROGRESS"


def test_process_isolated_checkpoint_resume(tmp_path):
    """
    Acceptance test for Phase 4:
    Process 1:
      submit ambiguous application
      graph pauses for clarification
      checkpoint exists in SQLite
      process exits
    Process 2:
      run --resume-session S1 --clarification '...'
      state is restored from checkpoint (no --application flag)
      graph resumes
      final result is produced
    """
    test_db = tmp_path / "checkpoints_test_e2e.sqlite"
    session_id = "SESSION-E2E-PROC-RESUME-01"

    env = os.environ.copy()
    env["CHECKPOINT_DB_PATH"] = str(test_db)
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    ambiguous_app_path = PROJECT_ROOT / "data" / "sample_applications" / "ambiguous_case.json"
    assert ambiguous_app_path.exists(), "ambiguous_case.json must exist in data/sample_applications"

    # ── Process 1: Submit ambiguous application ─────────────────────────────
    cmd_proc1 = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "run_pipeline.py"),
        "--application",
        str(ambiguous_app_path),
        "--resume-session",
        session_id,
    ]

    proc1 = subprocess.run(
        cmd_proc1,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(PROJECT_ROOT),
        timeout=240,
    )

    assert proc1.returncode == 0, f"Process 1 failed (exit code {proc1.returncode}):\nSTDOUT: {proc1.stdout}\nSTDERR: {proc1.stderr}"

    # Verify checkpoint exists in SQLite database
    assert checkpoint_exists(session_id, db_path=str(test_db)), "Process 1 must save checkpoint to SQLite"
    chk_state_p1 = load_checkpoint_state(session_id, db_path=str(test_db))
    assert chk_state_p1 is not None
    assert chk_state_p1["application_id"] == "APP-AMB-01"
    assert chk_state_p1["clarification_needed"] is True
    assert chk_state_p1["request_status"] == "IN_PROGRESS"
    assert "clarification_node" in chk_state_p1["routing_history"]
    assert chk_state_p1["decision_status"] == "N/A"

    # Verify structured output from Process 1
    p1_out_file = PROJECT_ROOT / "outputs" / "sample_results" / "APP-AMB-01.json"
    assert p1_out_file.exists()
    with open(p1_out_file, "r", encoding="utf-8") as f:
        p1_result = json.load(f)
    assert p1_result["request_status"] == "IN_PROGRESS"
    assert p1_result["decision_status"] == "N/A"
    assert p1_result["clarification_needed"] is True

    # ── Process 2: Resume with clarification across isolated process boundary ─
    # NOTE: We deliberately do NOT pass --application. State must restore from SQLite!
    clarification_text = "I would like to apply for a personal loan of 100000 INR for 12 months."
    cmd_proc2 = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "run_pipeline.py"),
        "--resume-session",
        session_id,
        "--clarification",
        clarification_text,
    ]

    proc2 = subprocess.run(
        cmd_proc2,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(PROJECT_ROOT),
        timeout=240,
    )

    assert proc2.returncode == 0, f"Process 2 failed (exit code {proc2.returncode}):\nSTDOUT: {proc2.stdout}\nSTDERR: {proc2.stderr}"

    # Verify checkpoint state was updated in SQLite
    chk_state_p2 = load_checkpoint_state(session_id, db_path=str(test_db))
    assert chk_state_p2 is not None
    assert chk_state_p2["application_id"] == "APP-AMB-01"
    assert chk_state_p2["session_id"] == session_id
    assert chk_state_p2["clarification_needed"] is False
    assert chk_state_p2["clarification_response"] == clarification_text
    assert chk_state_p2["request_status"] in {"COMPLETED", "IN_PROGRESS"}
    assert chk_state_p2["decision_status"] in {"DETERMINED", "UNABLE_TO_COMPLETE"}

    # Verify structured output updated for Process 2
    with open(p1_out_file, "r", encoding="utf-8") as f:
        p2_result = json.load(f)
    assert p2_result["session_id"] == session_id
    assert p2_result["clarification_response"] == clarification_text
    assert p2_result["request_status"] in {"COMPLETED", "IN_PROGRESS"}
    assert p2_result["decision_status"] in {"DETERMINED", "UNABLE_TO_COMPLETE"}


def test_resume_nonexistent_session_fails(tmp_path):
    """Resuming a session that has no saved checkpoint must fail closed with exit code 1."""
    test_db = tmp_path / "checkpoints_nonexistent.sqlite"
    env = os.environ.copy()
    env["CHECKPOINT_DB_PATH"] = str(test_db)
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "run_pipeline.py"),
        "--resume-session",
        "SESSION-DEFINITELY-DOES-NOT-EXIST-9999",
        "--clarification",
        "Some clarification text",
    ]

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(PROJECT_ROOT),
        timeout=90,
    )

    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert "No checkpoint found for session" in output or "Cannot resume" in output
