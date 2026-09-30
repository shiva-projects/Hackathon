import asyncio
import sqlite3
from pathlib import Path
from typing import Dict, Any, Optional
from langgraph.checkpoint.sqlite import SqliteSaver

import os

CHECKPOINT_DB_PATH = os.getenv("CHECKPOINT_DB_PATH", "data/checkpoints.sqlite")


class DualSqliteSaver(SqliteSaver):
    """
    Persistent SQLite Checkpointer supporting BOTH synchronous (.invoke)
    and asynchronous (.ainvoke / .astream) LangGraph execution.
    """

    async def aget_tuple(self, config: Dict[str, Any]):
        return await asyncio.to_thread(self.get_tuple, config)

    async def aput(self, config: Dict[str, Any], checkpoint: Any, metadata: Any, new_versions: Any):
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config: Dict[str, Any], writes: Any, task_id: str, task_path: str = ""):
        return await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def alist(self, config: Dict[str, Any], *, filter=None, before=None, limit=None):
        return await asyncio.to_thread(lambda: list(self.list(config, filter=filter, before=before, limit=limit)))

    def close(self) -> None:
        """Explicitly closes SQLite database connection to release OS locks."""
        if hasattr(self, "conn") and self.conn:
            try:
                self.conn.close()
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("Error closing checkpointer connection: %s", exc)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def get_checkpointer(db_path: str = CHECKPOINT_DB_PATH) -> DualSqliteSaver:
    """Creates or connects to persistent SQLite checkpointer."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    return DualSqliteSaver(conn)


def get_session_config(session_id: str, checkpoint_ns: str = "") -> Dict[str, Any]:
    """Generates standard LangGraph thread configuration dictionary."""
    return {"configurable": {"thread_id": session_id, "checkpoint_ns": checkpoint_ns}}


def checkpoint_exists(session_id: str, db_path: str = CHECKPOINT_DB_PATH) -> bool:
    """Checks whether a valid checkpoint exists for the specified session_id."""
    checkpointer = get_checkpointer(db_path)
    try:
        cfg = get_session_config(session_id)
        tup = checkpointer.get_tuple(cfg)
        return tup is not None and bool(tup.checkpoint and tup.checkpoint.get("channel_values"))
    finally:
        checkpointer.close()


def load_checkpoint_state(session_id: str, db_path: str = CHECKPOINT_DB_PATH) -> Optional[Dict[str, Any]]:
    """Loads and returns the persisted channel_values dictionary for session_id, or None if not found."""
    checkpointer = get_checkpointer(db_path)
    try:
        cfg = get_session_config(session_id)
        tup = checkpointer.get_tuple(cfg)
        if not tup or not tup.checkpoint:
            return None
        return dict(tup.checkpoint.get("channel_values", {}))
    finally:
        checkpointer.close()

