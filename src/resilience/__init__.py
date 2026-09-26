"""Resilience module for retry, timeout, and fallback."""
from src.resilience.timeout import (
    with_timeout,
    MCP_TIMEOUT_SECONDS,
    GEMINI_TIMEOUT_SECONDS,
    ToolTimeoutError,
    ModelTimeoutError,
)
from src.resilience.retry import (
    with_retry,
    MAX_ATTEMPTS,
    INITIAL_BACKOFF_SECONDS,
    MAX_BACKOFF_SECONDS,
)
from src.resilience.fallback import handle_mcp_failure, handle_gemini_failure

__all__ = [
    "with_timeout",
    "MCP_TIMEOUT_SECONDS",
    "GEMINI_TIMEOUT_SECONDS",
    "ToolTimeoutError",
    "ModelTimeoutError",
    "with_retry",
    "MAX_ATTEMPTS",
    "INITIAL_BACKOFF_SECONDS",
    "MAX_BACKOFF_SECONDS",
    "handle_mcp_failure",
    "handle_gemini_failure",
]
