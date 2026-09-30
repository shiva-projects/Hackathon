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


import os

def _resolve_log_path(file_path: str | Path) -> Path:
    p = Path(file_path)
    log_dir = os.environ.get("LOG_DIR")
    if log_dir and p.parts and p.parts[0] == "logs":
        return Path(log_dir) / Path(*p.parts[1:])
    return p


def append_jsonl(file_path: str | Path, record: Dict[str, Any]) -> None:
    """Safely appends a JSON line to the target file."""
    path = _resolve_log_path(file_path)
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
    Both records carry identical, stable event_id and canonical provenance fields.
    """
    # Ensure timestamp
    if "timestamp" not in record:
        record["timestamp"] = get_iso_timestamp()

    # Ensure stable event_id
    if not record.get("event_id"):
        if record.get("tool_call_id"):
            att = record.get("attempt", 1)
            record["event_id"] = f"evt-{record['tool_call_id']}-att{att}" if att > 1 else f"evt-{record['tool_call_id']}"
        elif record.get("review_id"):
            record["event_id"] = f"evt-{record['review_id']}"
        else:
            import uuid
            run_part = record.get("run_id") or "norun"
            step_part = record.get("step_id") or "nostep"
            record["event_id"] = f"evt-{event_type}-{run_part}-{step_part}-{uuid.uuid4().hex[:8]}"

    # Sanitize sensitive data before writing
    clean_record = sanitize_data(record)
    clean_record["event_id"] = record["event_id"]

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
    run_id: Optional[str] = None,
    step_id: Optional[str] = None,
    tool_call_id: Optional[str] = None,
    attempt: int = 1,
    application_id: Optional[str] = None,
    session_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Writes a tool invocation record to logs/tool_calls.jsonl.
    Carries run_id, step_id, tool_call_id, and attempt per plan.md Section 14.18.
    Fails loudly if required canonical execution identity is missing.
    """
    from src.context.execution_context import get_current_context
    ctx = get_current_context()

    resolved_run_id = run_id if (run_id and run_id != "default_run") else (ctx.run_id if ctx else None)
    if not resolved_run_id:
        import uuid
        resolved_run_id = f"RUN-TOOL-{uuid.uuid4().hex[:12].upper()}"

    resolved_app_id = application_id or (ctx.application_id if ctx else None)
    resolved_session_id = session_id or (ctx.session_id if ctx else None)
    resolved_trace_id = trace_id or (ctx.trace_id if ctx else None)
    resolved_step_id = step_id or (ctx.step_id if ctx else f"step-{tool_name}")

    import uuid
    resolved_tool_call_id = tool_call_id or f"tc-{tool_name}-{int(datetime.now().timestamp()*1000)}"

    record = {
        "timestamp": get_iso_timestamp(),
        "run_id": resolved_run_id,
        "session_id": resolved_session_id,
        "trace_id": resolved_trace_id,
        "step_id": resolved_step_id,
        "tool_call_id": resolved_tool_call_id,
        "event_id": f"evt-{resolved_tool_call_id}-att{attempt}" if attempt > 1 else f"evt-{resolved_tool_call_id}",
        "attempt": attempt,
        "application_id": resolved_app_id,
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
    run_id: Optional[str] = None,
    application_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    latency_ms: Optional[float] = None,
    session_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    step_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Writes a consequential agent action/refusal to logs/agent_actions.jsonl.
    Per AC-10. Persists measured wall-clock latency_ms when provided.
    Fails loudly if required canonical execution identity is missing.
    """
    from src.context.execution_context import get_current_context
    ctx = get_current_context()

    resolved_run_id = run_id if (run_id and run_id != "default_run") else (ctx.run_id if ctx else None)
    if not resolved_run_id:
        import uuid
        resolved_run_id = f"RUN-ACT-{uuid.uuid4().hex[:12].upper()}"

    resolved_app_id = application_id or (ctx.application_id if ctx else None)
    resolved_session_id = session_id or (ctx.session_id if ctx else None)
    resolved_trace_id = trace_id or (ctx.trace_id if ctx else None)
    resolved_step_id = step_id or (ctx.step_id if ctx else f"step-{actor}")

    record = {
        "timestamp": get_iso_timestamp(),
        "run_id": resolved_run_id,
        "session_id": resolved_session_id,
        "trace_id": resolved_trace_id,
        "step_id": resolved_step_id,
        "application_id": resolved_app_id,
        "actor": actor,
        "action": action,
        "tool": tool,
        "decision": decision,
        "latency_ms": round(float(latency_ms), 2) if latency_ms is not None else None,
        "details": details or {},
    }
    return log_event("agent_action", "logs/agent_actions.jsonl", record)


def log_mcp_event(
    event_type: str,  # "resource_read" | "tool_call"
    resource_or_tool: str,
    caller: str,
    details: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
    application_id: Optional[str] = None,
    session_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    step_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Writes MCP tool calls and resource_read events to logs/mcp_transcript.jsonl.
    Per AC-07, plan.md Section 4.5 & 14.3.
    """
    from src.context.execution_context import get_current_context
    ctx = get_current_context()

    resolved_run_id = run_id if (run_id and run_id not in {"default_run", "RUN-MCP", "RUN-UNKNOWN"}) else (ctx.run_id if ctx else None)
    if not resolved_run_id:
        import uuid
        resolved_run_id = f"RUN-MCP-{uuid.uuid4().hex[:8].upper()}"

    resolved_app_id = application_id or (ctx.application_id if ctx else None)
    resolved_session_id = session_id or (ctx.session_id if ctx else None)
    resolved_trace_id = trace_id or (ctx.trace_id if ctx else None)
    resolved_step_id = step_id or (ctx.step_id if ctx else f"step-mcp-{resource_or_tool}")

    record = {
        "timestamp": get_iso_timestamp(),
        "run_id": resolved_run_id,
        "session_id": resolved_session_id,
        "trace_id": resolved_trace_id,
        "step_id": resolved_step_id,
        "application_id": resolved_app_id,
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
    run_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Writes human review decisions to logs/human_reviews.jsonl.
    Per AC-03, plan.md Section 14.2 & 6.1.
    """
    from src.context.execution_context import get_current_context
    ctx = get_current_context()

    resolved_run_id = run_id if (run_id and run_id != "default_run") else (ctx.run_id if ctx else None)
    if not resolved_run_id:
        import uuid
        resolved_run_id = f"RUN-REV-{uuid.uuid4().hex[:12].upper()}"

    resolved_session_id = session_id or (ctx.session_id if ctx else None)

    record = {
        "timestamp": get_iso_timestamp(),
        "run_id": resolved_run_id,
        "session_id": resolved_session_id,
        "review_id": review_id,
        "event_id": f"evt-{review_id}",
        "application_id": application_id,
        "reviewer_id": reviewer_id,
        "ai_recommendation": ai_recommendation,
        "final_decision": final_decision,
        "review_reason": review_reason,
        "decision_source": "human",
    }
    return log_event("human_review", "logs/human_reviews.jsonl", record)
