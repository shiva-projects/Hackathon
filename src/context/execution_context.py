"""
Canonical Execution Context Model for BC-AAIE-HACK-02.
Enforces execution identity across graph execution, MCP, tools, Phoenix tracing, audit logging, and human review.
Per Phase 3 specifications and plan.md Section 14.18.

Semantic difference between run_id and session_id:
- session_id:
    Represents the end-to-end conversation or applicant lifecycle session.
    Persists across multiple turns, process restarts, interruptions, and human reviews
    (e.g., across clarification questions and --resume-session invocations).
- run_id:
    Represents a single, continuous pipeline invocation or graph execution attempt.
    A single session_id can encompass multiple run_ids (for example, the initial run
    that yields a clarification question, followed by a resumed run that finishes underwriting).
    Every consequential log event, tool call, span, and review record MUST be bound to
    the exact run_id during which it was produced, while also referencing session_id.
"""

from dataclasses import dataclass, field
import uuid
import contextvars
from typing import Optional, Dict, Any


@dataclass
class ExecutionContext:
    """
    Canonical execution context holding required execution identities.
    No consequential event may execute without these values.
    """
    run_id: str
    session_id: str
    application_id: str
    trace_id: str = field(default_factory=lambda: f"trace-{uuid.uuid4().hex[:16]}")
    step_id: Optional[str] = None
    span_id: Optional[str] = None
    tool_call_id: Optional[str] = None
    attempt: int = 1

    def __post_init__(self):
        if not self.run_id or self.run_id in {"default_run", "RUN-MCP", "RUN-UNKNOWN"}:
            raise ValueError(f"Invalid or prohibited run_id in ExecutionContext: '{self.run_id}'")
        if not self.session_id or self.session_id in {"default-session", "RUN-UNKNOWN"}:
            raise ValueError(f"Invalid or prohibited session_id in ExecutionContext: '{self.session_id}'")
        if not self.application_id or self.application_id in {"APP-UNKNOWN"}:
            raise ValueError(f"Invalid or prohibited application_id in ExecutionContext: '{self.application_id}'")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "application_id": self.application_id,
            "trace_id": self.trace_id,
            "step_id": self.step_id,
            "span_id": self.span_id,
            "tool_call_id": self.tool_call_id,
            "attempt": self.attempt,
        }


_current_context: contextvars.ContextVar[Optional[ExecutionContext]] = contextvars.ContextVar(
    "current_execution_context", default=None
)


def get_current_context() -> Optional[ExecutionContext]:
    """Retrieves ambient execution context for the current async task/thread."""
    return _current_context.get()


def set_current_context(
    ctx: Optional[ExecutionContext] = None,
    *,
    run_id: Optional[str] = None,
    session_id: Optional[str] = None,
    application_id: Optional[str] = None,
    step_id: Optional[str] = None,
    tool_call_id: Optional[str] = None,
    attempt: int = 1,
) -> contextvars.Token:
    """Sets ambient execution context for the current async task/thread."""
    if ctx is None:
        if not run_id or not session_id or not application_id:
            raise ValueError("set_current_context requires either an ExecutionContext object or run_id, session_id, and application_id kwargs")
        ctx = ExecutionContext(
            run_id=run_id,
            session_id=session_id,
            application_id=application_id,
            step_id=step_id,
            tool_call_id=tool_call_id,
            attempt=attempt,
        )
    return _current_context.set(ctx)


def reset_current_context(token: contextvars.Token) -> None:
    """Resets ambient execution context back to previous token."""
    _current_context.reset(token)


def resolve_run_id(explicit_run_id: Optional[str] = None, required: bool = True) -> str:
    """
    Resolves canonical run_id from explicit argument or ambient ExecutionContext.
    Fails loudly if required and no valid identity exists.
    """
    if explicit_run_id and explicit_run_id not in {"default_run", "RUN-MCP", "RUN-UNKNOWN"}:
        return explicit_run_id
    ctx = get_current_context()
    if ctx and ctx.run_id and ctx.run_id not in {"default_run", "RUN-MCP", "RUN-UNKNOWN"}:
        return ctx.run_id
    if required:
        raise ValueError("Missing mandatory canonical run_id in consequential execution context")
    return f"RUN-AUTO-{uuid.uuid4().hex[:12].upper()}"


def resolve_identity(
    explicit_run_id: Optional[str] = None,
    explicit_session_id: Optional[str] = None,
    explicit_app_id: Optional[str] = None,
    explicit_step_id: Optional[str] = None,
    required: bool = True,
) -> Dict[str, Any]:
    """
    Resolves complete canonical identity dictionary from explicit args or ambient context.
    """
    ctx = get_current_context()
    run_id = explicit_run_id or (ctx.run_id if ctx else None)
    session_id = explicit_session_id or (ctx.session_id if ctx else None)
    app_id = explicit_app_id or (ctx.application_id if ctx else None)
    step_id = explicit_step_id or (ctx.step_id if ctx else None)
    trace_id = ctx.trace_id if ctx else f"trace-{uuid.uuid4().hex[:16]}"

    if required:
        if not run_id or run_id in {"default_run", "RUN-MCP", "RUN-UNKNOWN"}:
            raise ValueError(f"Missing mandatory canonical run_id: got '{run_id}'")
        if not app_id or app_id == "APP-UNKNOWN":
            raise ValueError(f"Missing mandatory canonical application_id: got '{app_id}'")

    return {
        "run_id": run_id or f"RUN-AUTO-{uuid.uuid4().hex[:12].upper()}",
        "session_id": session_id or f"SESS-AUTO-{uuid.uuid4().hex[:12].upper()}",
        "application_id": app_id or "APP-AUTO",
        "step_id": step_id,
        "trace_id": trace_id,
    }
