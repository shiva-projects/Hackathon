"""Context engineering package: write, select, compress, isolate, quarantine."""
from src.context.quarantine import quarantine_untrusted_text
from src.context.select import select_agent_context, AGENT_ALLOWED_CONTEXT
from src.context.isolate import verify_context_isolation
from src.context.compress import compress_interaction_history, estimate_token_count
from src.context.write import write_verified_fact

from src.context.execution_context import (
    ExecutionContext,
    get_current_context,
    set_current_context,
    reset_current_context,
    resolve_run_id,
    resolve_identity,
)

__all__ = [
    "quarantine_untrusted_text",
    "select_agent_context",
    "AGENT_ALLOWED_CONTEXT",
    "verify_context_isolation",
    "compress_interaction_history",
    "estimate_token_count",
    "write_verified_fact",
    "ExecutionContext",
    "get_current_context",
    "set_current_context",
    "reset_current_context",
    "resolve_run_id",
    "resolve_identity",
]
