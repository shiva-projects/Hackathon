"""
Timeout controls for MCP tools and Gemini model calls.
Constants locked per plan.md Section 5:
MCP_TIMEOUT_SECONDS = 10, GEMINI_TIMEOUT_SECONDS = 20.
"""

import asyncio
from typing import Callable, Any, TypeVar, Coroutine

T = TypeVar("T")

MCP_TIMEOUT_SECONDS: float = 10.0
GEMINI_TIMEOUT_SECONDS: float = 20.0


class ToolTimeoutError(Exception):
    """Raised when an MCP tool invocation exceeds timeout budget."""
    pass


class ModelTimeoutError(Exception):
    """Raised when a Gemini LLM invocation exceeds timeout budget."""
    pass


async def with_timeout(
    coro: Coroutine[Any, Any, T],
    timeout_seconds: float,
    timeout_error_type: type = ToolTimeoutError,
    error_message: str = "Operation timed out",
) -> T:
    """Executes a coroutine with a strict asyncio timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        raise timeout_error_type(f"{error_message} after {timeout_seconds}s") from exc
