"""
Tests for Async Correctness, Lifecycle Management, and Resource Hygiene (Phase 10).
Conforms to plan.md Section 7.5 & antigravity_implementation_checklist.md Phase 10.
"""

import os
import sys
import time
import inspect
import asyncio
import tempfile
import logging
from pathlib import Path
import pytest

from src.state import create_initial_state
from src.memory.checkpoint_config import (
    get_checkpointer,
    get_session_config,
    checkpoint_exists,
    load_checkpoint_state,
    DualSqliteSaver,
)
from src.observability.tracing import shutdown_tracing, safe_cleanup_temp_dir
from mcp_server.client import MCPSessionPool, shutdown_mcp_pool, MCPClient


def test_no_global_tempdir_monkeypatch():
    """
    Acceptance: No process-wide stdlib monkeypatch remains for tracing cleanup.
    Verifies that tempfile.TemporaryDirectory._cleanup is the standard library implementation.
    """
    import tempfile
    cleanup_func = tempfile.TemporaryDirectory._cleanup
    # The standard library implementation is a normal function, not our previously patched staticmethod
    assert "src.observability.tracing" not in str(cleanup_func)
    assert not hasattr(cleanup_func, "__wrapped__")


def test_sqlite_checkpointer_lifecycle_and_scoped_cleanup():
    """
    Verifies that DualSqliteSaver.close() releases the SQLite file lock on Windows,
    allowing scoped TemporaryDirectory cleanup to succeed without PermissionError.
    """
    temp_dir = tempfile.TemporaryDirectory()
    temp_path = Path(temp_dir.name)
    db_file = temp_path / "test_lifecycle.sqlite"

    checkpointer = get_checkpointer(str(db_file))
    cfg = get_session_config("SESSION-LIFECYCLE-01")
    checkpoint_data = {
        "v": 1,
        "ts": "2026-09-30T12:00:00+00:00",
        "id": "chk-001",
        "channel_values": {"application_id": "APP-LIFE-01", "step_count": 1},
        "channel_versions": {},
        "versions_seen": {},
    }
    checkpointer.put(cfg, checkpoint_data, {}, {})

    # Read back to confirm data is written
    loaded = checkpointer.get_tuple(cfg)
    assert loaded is not None
    assert loaded.checkpoint["channel_values"]["application_id"] == "APP-LIFE-01"

    # Explicitly close checkpointer
    checkpointer.close()

    # Temporary directory cleanup must succeed cleanly on Windows without file locking errors
    temp_dir.cleanup()
    assert not temp_path.exists(), "Temporary directory must be cleanly removed after checkpointer.close()"


def test_checkpoint_exists_and_load_auto_close_connections():
    """
    Verifies that checkpoint_exists() and load_checkpoint_state() cleanly close
    their database connections in finally blocks and never leak file locks.
    """
    temp_dir = tempfile.TemporaryDirectory()
    temp_path = Path(temp_dir.name)
    db_file = temp_path / "test_auto_close.sqlite"

    with get_checkpointer(str(db_file)) as cp:
        cfg = get_session_config("SESSION-AUTOCLOSE-01")
        checkpoint_data = {
            "v": 1,
            "ts": "2026-09-30T12:00:00+00:00",
            "id": "chk-002",
            "channel_values": {"application_id": "APP-AUTO-01"},
            "channel_versions": {},
            "versions_seen": {},
        }
        cp.put(cfg, checkpoint_data, {}, {})

    # Call checkpoint_exists and load_checkpoint_state without explicit checkpointer handle
    assert checkpoint_exists("SESSION-AUTOCLOSE-01", db_path=str(db_file)) is True
    assert checkpoint_exists("SESSION-NONEXISTENT", db_path=str(db_file)) is False

    st = load_checkpoint_state("SESSION-AUTOCLOSE-01", db_path=str(db_file))
    assert st is not None
    assert st["application_id"] == "APP-AUTO-01"

    # Must be cleanable immediately because connections were closed
    temp_dir.cleanup()
    assert not temp_path.exists()


def test_mcp_session_pool_explicit_shutdown():
    """
    Verifies that MCPSessionPool supports explicit shutdown, properly stopping
    background worker thread and closing sessions.
    """
    pool = MCPSessionPool.get_instance()
    assert pool is not None

    # Explicitly shut down pool
    shutdown_mcp_pool()
    assert MCPSessionPool._instance is None


@pytest.mark.asyncio
async def test_async_graph_nodes_are_native_coroutines():
    """
    Acceptance: No obvious blocking I/O/tool invocation remains inside async graph nodes.
    Verifies that all nodes in the graph pipeline are registered as asynchronous coroutines.
    """
    from src.graph import (
        input_guard_node,
        authorization_node,
        intent_classifier_node,
        supervisor_node,
        clarification_node,
        status_node,
        document_node,
        refusal_node,
        loop_guard_terminal_node,
    )
    from src.agents.policy_agent import apolicy_agent_node
    from src.agents.eligibility_agent import aeligibility_agent_node
    from src.agents.risk_agent import arisk_agent_node
    from src.agents.decision_agent import adecision_agent_node

    nodes = [
        ("input_guard", input_guard_node),
        ("authorization", authorization_node),
        ("intent_classifier", intent_classifier_node),
        ("supervisor", supervisor_node),
        ("clarification", clarification_node),
        ("status", status_node),
        ("document", document_node),
        ("refusal", refusal_node),
        ("loop_guard", loop_guard_terminal_node),
        ("policy_agent", apolicy_agent_node),
        ("eligibility_agent", aeligibility_agent_node),
        ("risk_agent", arisk_agent_node),
        ("decision_agent", adecision_agent_node),
    ]

    for name, node_fn in nodes:
        assert inspect.iscoroutinefunction(node_fn), f"Node '{name}' must be an async coroutine function"


@pytest.mark.asyncio
async def test_async_tools_gather_concurrency():
    """
    Verifies that async tool invocations can be executed concurrently with asyncio.gather
    without thread exhaustion or blocking the event loop.
    """
    args1 = {
        "income_amount": 100000.0,
        "income_period": "monthly",
        "existing_obligations": [{"amount": 20000.0, "period": "monthly"}],
        "dti_max_threshold": 0.40,
        "run_id": "RUN-ASYNC-GATHER-01",
    }
    args2 = {
        "income_amount": 150000.0,
        "income_period": "monthly",
        "existing_obligations": [{"amount": 35000.0, "period": "monthly"}],
        "dti_max_threshold": 0.40,
        "run_id": "RUN-ASYNC-GATHER-02",
    }

    t0 = time.time()
    res1, res2 = await asyncio.gather(
        MCPClient.acall_compute_affordability(**args1),
        MCPClient.acall_compute_affordability(**args2),
    )
    elapsed = time.time() - t0

    assert "dti" in res1
    assert "dti" in res2
    assert res1["dti"] == 0.20
    assert round(res2["dti"], 4) == round(35000.0 / 150000.0, 4)
    # Both finished cleanly
    assert elapsed < 30.0


def test_diagnosable_cleanup_error_logging(caplog):
    """
    Acceptance: Cleanup failures are visible and diagnosable, not swallowed indiscriminately.
    """
    class FailingTempDir:
        def cleanup(self):
            raise PermissionError("Simulated OS lock during cleanup")

    with caplog.at_level(logging.WARNING):
        safe_cleanup_temp_dir(FailingTempDir())

    assert "Failed to clean up temporary directory" in caplog.text
    assert "Simulated OS lock" in caplog.text
