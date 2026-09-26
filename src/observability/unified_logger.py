"""
Unified Event Logger for BC-AAIE-HACK-02.
Atomic dual-write architecture fanning out to per-concern logs AND logs/unified_trace.jsonl.
Per plan.md Section 7.5 & 14.8.
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from src.observability.span_sanitizer import sanitize_data

_LOG_LOCK = threading.Lock()


def get_iso_timestamp() -> str:
    """Returns standard ISO 8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(file_path: str | Path, record: Dict[str, Any]) -> None:
    """Safely appends a JSON line to the target file."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")


def log_event(event_type: str, source_log: str, record: Dict[str, Any]) -> Dict[str, Any]:
    """
    The single choke point for all logging in the repository (plan.md Section 7.5).
    Applies PII redaction once, then writes atomically to:
    1. The per-concern source log
    2. logs/unified_trace.jsonl
    """
    # Ensure timestamp
    if "timestamp" not in record:
        record["timestamp"] = get_iso_timestamp()

    # Sanitize sensitive data before writing
    clean_record = sanitize_data(record)

    # 1. Write to per-concern log
    append_jsonl(source_log, clean_record)

    # 2. Write to unified trace with provenance fields
    unified_record = {
        **clean_record,
        "event_type": event_type,
        "source_log": source_log,
    }
    append_jsonl("logs/unified_trace.jsonl", unified_record)

    return clean_record


def log_tool_call(
    agent: str,
    tool_name: str,
    args: Dict[str, Any],
    result: Any,
    latency_ms: float,
    status: str = "success",
    run_id: str = "default_run",
    step_id: Optional[str] = None,
    tool_call_id: Optional[str] = None,
    attempt: int = 1,
    application_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Writes a tool invocation record to logs/tool_calls.jsonl.
    Carries run_id, step_id, tool_call_id, and attempt per plan.md Section 14.18.
    """
    record = {
        "timestamp": get_iso_timestamp(),
        "run_id": run_id,
        "step_id": step_id or f"step-{tool_name}",
        "tool_call_id": tool_call_id or f"tc-{tool_name}-{int(datetime.now().timestamp()*1000)}",
        "attempt": attempt,
        "application_id": application_id,
        "agent": agent,
        "tool_name": tool_name,
        "args": args,
        "result": result,
        "latency_ms": round(latency_ms, 2),
        "status": status,
    }
    return log_event("tool_call", "logs/tool_calls.jsonl", record)


def log_agent_action(
    actor: str,
    action: str,
    tool: Optional[str],
    decision: str,
    run_id: str = "default_run",
    application_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Writes a consequential agent action/refusal to logs/agent_actions.jsonl.
    Per AC-10.
    """
    record = {
        "timestamp": get_iso_timestamp(),
        "run_id": run_id,
        "application_id": application_id,
        "actor": actor,
        "action": action,
        "tool": tool,
        "decision": decision,
        "details": details or {},
    }
    return log_event("agent_action", "logs/agent_actions.jsonl", record)


def log_mcp_event(
    event_type: str,  # "resource_read" | "tool_call"
    resource_or_tool: str,
    caller: str,
    details: Optional[Dict[str, Any]] = None,
    run_id: str = "default_run",
    application_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Writes MCP tool calls and resource_read events to logs/mcp_transcript.jsonl.
    Per AC-07, plan.md Section 4.5 & 14.3.
    """
    record = {
        "timestamp": get_iso_timestamp(),
        "run_id": run_id,
        "application_id": application_id,
        "type": event_type,
        "resource": resource_or_tool if event_type == "resource_read" else None,
        "tool_name": resource_or_tool if event_type == "tool_call" else None,
        "caller": caller,
        "details": details or {},
    }
    return log_event("mcp_transcript", "logs/mcp_transcript.jsonl", record)


def log_human_review(
    review_id: str,
    application_id: str,
    reviewer_id: str,
    ai_recommendation: Optional[str],
    final_decision: str,
    review_reason: str,
    run_id: str = "default_run",
) -> Dict[str, Any]:
    """
    Writes human review decisions to logs/human_reviews.jsonl.
    Per AC-03, plan.md Section 14.2 & 6.1.
    """
    record = {
        "timestamp": get_iso_timestamp(),
        "run_id": run_id,
        "review_id": review_id,
        "application_id": application_id,
        "reviewer_id": reviewer_id,
        "ai_recommendation": ai_recommendation,
        "final_decision": final_decision,
        "review_reason": review_reason,
        "decision_source": "human",
    }
    return log_event("human_review", "logs/human_reviews.jsonl", record)
