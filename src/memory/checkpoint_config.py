"""
SQLite Checkpoint Configuration for LangGraph Tier 2 Session Memory.
Per plan.md Section 14.4 & 4.3.
Enables cross-turn state restoration and process-restart resume via session_id.
"""

import sqlite3
from pathlib import Path
from typing import Dict, Any
from langgraph.checkpoint.sqlite import SqliteSaver

CHECKPOINT_DB_PATH = "data/checkpoints.sqlite"


def get_checkpointer(db_path: str = CHECKPOINT_DB_PATH) -> SqliteSaver:
    """Creates or connects to persistent SQLite checkpointer."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    return SqliteSaver(conn)


def get_session_config(session_id: str, checkpoint_ns: str = "") -> Dict[str, Any]:
    """Generates standard LangGraph thread configuration dictionary."""
    return {"configurable": {"thread_id": session_id, "checkpoint_ns": checkpoint_ns}}
