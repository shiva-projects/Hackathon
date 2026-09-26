"""
Bounded asynchronous retry with exponential backoff.
Constants locked per plan.md Section 5:
MAX_ATTEMPTS = 2, INITIAL_BACKOFF_SECONDS = 0.5, MAX_BACKOFF_SECONDS = 2.0.
"""

import asyncio
import logging
from typing import Callable, Any, TypeVar, Coroutine, Optional, Tuple, Type
from src.observability.unified_logger import log_tool_call

T = TypeVar("T")

MAX_ATTEMPTS: int = 2
INITIAL_BACKOFF_SECONDS: float = 0.5
MAX_BACKOFF_SECONDS: float = 2.0


async def with_retry(
    async_fn: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    max_attempts: int = MAX_ATTEMPTS,
    initial_backoff: float = INITIAL_BACKOFF_SECONDS,
    max_backoff: float = MAX_BACKOFF_SECONDS,
    retry_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    caller_name: str = "resilience_executor",
    **kwargs: Any,
) -> T:
    """
    Executes an async callable with bounded exponential backoff retry.
    Logs retry attempts to tool_calls.jsonl.
    """
    attempt = 1
    backoff = initial_backoff

    while attempt <= max_attempts:
        try:
            return await async_fn(*args, **kwargs)
        except retry_exceptions as e:
            if attempt == max_attempts:
                # Log final failure
                log_tool_call(
                    agent=caller_name,
                    tool_name=getattr(async_fn, "__name__", "anonymous_call"),
                    args={"attempt": attempt, "error": str(e)},
                    result=None,
                    latency_ms=0.0,
                    status="exhausted_retries",
                    attempt=attempt,
                )
                raise e

            # Log retry attempt
            log_tool_call(
                agent=caller_name,
                tool_name=getattr(async_fn, "__name__", "anonymous_call"),
                args={"attempt": attempt, "error": str(e)},
                result=None,
                latency_ms=0.0,
                status="retried",
                attempt=attempt,
            )

            await asyncio.sleep(min(backoff, max_backoff))
            backoff *= 2.0
            attempt += 1

    raise RuntimeError("Unreachable in with_retry")
