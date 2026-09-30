"""
Client helper for calling MCP tools and reading MCP resources.
Uses langchain-mcp-adapters and MCP protocol client session over in-memory streams.
Maintains persistent session reuse across calls to eliminate session churn latency.
Per plan.md Section 4.5, 13.4 & 14.3.
"""

import json
import time
import asyncio
import logging
import threading
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Dict, Any, List, Optional
from pydantic import AnyUrl

from mcp_server.server import mcp
try:
    from mcp.shared.memory import create_connected_server_and_client_session
except ImportError:
    import anyio
    from mcp.client.session import ClientSession
    from mcp.shared.memory import create_client_server_memory_streams

    @asynccontextmanager
    async def create_connected_server_and_client_session(server, **kwargs):
        if hasattr(server, "_mcp_server"):
            server = server._mcp_server
        async with create_client_server_memory_streams() as (client_streams, server_streams):
            client_read, client_write = client_streams
            server_read, server_write = server_streams
            async with anyio.create_task_group() as tg:
                async def _run_server():
                    await server.run(
                        server_read,
                        server_write,
                        server.create_initialization_options(),
                    )
                tg.start_soon(_run_server)
                try:
                    async with ClientSession(
                        read_stream=client_read,
                        write_stream=client_write,
                    ) as client_session:
                        await client_session.initialize()
                        yield client_session
                finally:
                    tg.cancel_scope.cancel()

from langchain_mcp_adapters.tools import load_mcp_tools
from src.observability.unified_logger import log_mcp_event, log_tool_call
from src.observability.tracing import tracer

logger = logging.getLogger(__name__)


class MCPUnavailableError(Exception):
    """Raised when MCP server transport, session, tool, or resource is unavailable or exhausted retries."""
    pass


class MCPSessionPool:
    """
    Session pool and manager for MCP protocol sessions.
    Maintains active in-memory client-server sessions to avoid per-call stream creation.
    Per plan.md Section 4.5, 13.4 & 14.3.
    """
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._pool: Dict[str, Dict[str, Any]] = {}
        self._worker_loop: Optional[asyncio.AbstractEventLoop] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._worker_session = None
        self._worker_tools = None
        self._worker_ready = threading.Event()
        self._stop_event: Optional[asyncio.Event] = None
        self._start_worker()

    def _start_worker(self):
        def _target():
            self._worker_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._worker_loop)
            self._stop_event = asyncio.Event()

            async def _worker_main():
                try:
                    async with create_connected_server_and_client_session(mcp._mcp_server) as session:
                        self._worker_session = session
                        self._worker_tools = await load_mcp_tools(session=session)
                        self._worker_ready.set()
                        await self._stop_event.wait()
                except Exception as e:
                    logger.error("Failed to initialize MCP persistent worker session: %s", e)
                    self._worker_ready.set()

            try:
                self._worker_loop.run_until_complete(_worker_main())
            finally:
                try:
                    self._worker_loop.close()
                except Exception:
                    pass

        self._worker_thread = threading.Thread(target=_target, daemon=True, name="mcp-session-worker")
        self._worker_thread.start()
        self._worker_ready.wait(timeout=15.0)

    @classmethod
    def get_instance(cls) -> "MCPSessionPool":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @asynccontextmanager
    async def pipeline_session(self, session_id: str = "default"):
        """
        Async context manager to hold an MCP session open for the duration of a pipeline run.
        """
        stack = AsyncExitStack()
        session = await stack.enter_async_context(
            create_connected_server_and_client_session(mcp._mcp_server)
        )
        tools = await load_mcp_tools(session=session)
        self._pool[session_id] = {"session": session, "tools": tools, "stack": stack}
        try:
            yield session
        finally:
            self._pool.pop(session_id, None)
            await stack.aclose()

    async def execute_tool(self, tool_name: str, args: Dict[str, Any], session_id: Optional[str] = None) -> Any:
        async def _raw_invoke():
            if session_id and session_id in self._pool:
                entry = self._pool[session_id]
                tools = entry["tools"]
                tool = next((t for t in tools if t.name == tool_name), None)
                if tool is None:
                    raise MCPUnavailableError(f"MCP tool '{tool_name}' not registered in MCP server via adapter")
                raw_result = await tool.ainvoke(args)
                return self._format_result(raw_result)

            if self._worker_loop and self._worker_loop.is_running() and self._worker_tools:
                tool = next((t for t in self._worker_tools if t.name == tool_name), None)
                if tool is None:
                    raise MCPUnavailableError(f"MCP tool '{tool_name}' not registered in MCP server via adapter")
                future = asyncio.run_coroutine_threadsafe(tool.ainvoke(args), self._worker_loop)
                raw_result = await asyncio.wrap_future(future)
                return self._format_result(raw_result)

            raise MCPUnavailableError("No active MCP session available in pool")

        attempt = 1
        max_attempts = 2
        timeout_seconds = 10.0
        last_error = None

        while attempt <= max_attempts:
            try:
                return await asyncio.wait_for(_raw_invoke(), timeout=timeout_seconds)
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "MCP tool invocation '%s' attempt %d/%d failed: %s",
                    tool_name, attempt, max_attempts, exc,
                )
                if attempt == max_attempts:
                    break
                await asyncio.sleep(0.5 * attempt)
                attempt += 1

        raise MCPUnavailableError(
            f"MCP tool execution '{tool_name}' failed after {max_attempts} attempts: {last_error}"
        ) from last_error

    def execute_tool_sync(self, tool_name: str, args: Dict[str, Any], session_id: Optional[str] = None) -> Any:
        return _run_coroutine_sync(self.execute_tool(tool_name, args, session_id))

    async def read_resource(self, uri: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        async def _raw_read():
            if session_id and session_id in self._pool:
                session = self._pool[session_id]["session"]
                res = await session.read_resource(AnyUrl(uri))
                return self._format_resource(res)

            if self._worker_loop and self._worker_loop.is_running() and self._worker_session:
                future = asyncio.run_coroutine_threadsafe(self._worker_session.read_resource(AnyUrl(uri)), self._worker_loop)
                res = await asyncio.wrap_future(future)
                return self._format_resource(res)

            raise MCPUnavailableError("No active MCP session available in pool")

        attempt = 1
        max_attempts = 2
        timeout_seconds = 10.0
        last_error = None

        while attempt <= max_attempts:
            try:
                return await asyncio.wait_for(_raw_read(), timeout=timeout_seconds)
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "MCP read_resource '%s' attempt %d/%d failed: %s",
                    uri, attempt, max_attempts, exc,
                )
                if attempt == max_attempts:
                    break
                await asyncio.sleep(0.5 * attempt)
                attempt += 1

        raise MCPUnavailableError(
            f"MCP read_resource failed for '{uri}' after {max_attempts} attempts: {last_error}"
        ) from last_error

    def read_resource_sync(self, uri: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        return _run_coroutine_sync(self.read_resource(uri, session_id))

    @staticmethod
    def _format_result(raw_result: Any) -> Any:
        if isinstance(raw_result, list) and len(raw_result) > 0 and isinstance(raw_result[0], dict) and "text" in raw_result[0]:
            return json.loads(raw_result[0]["text"])
        elif isinstance(raw_result, str):
            return json.loads(raw_result)
        return raw_result

    @staticmethod
    def _format_resource(res: Any) -> Dict[str, Any]:
        if hasattr(res, "contents") and len(res.contents) > 0:
            return json.loads(res.contents[0].text)
        return {}

    def shutdown(self) -> None:
        """
        Explicitly shuts down the MCP persistent worker loop, session, and thread.
        Provides clean resource reclamation without leaking background threads or file handles.
        """
        with self._lock:
            if self._worker_loop and self._worker_loop.is_running() and self._stop_event is not None:
                try:
                    self._worker_loop.call_soon_threadsafe(self._stop_event.set)
                except Exception as e:
                    logger.warning("Error signaling MCP worker stop: %s", e)
            if self._worker_thread and self._worker_thread.is_alive():
                self._worker_thread.join(timeout=3.0)
            self._worker_loop = None
            self._worker_thread = None
            self._worker_session = None
            self._worker_tools = None
            self._stop_event = None
            MCPSessionPool._instance = None


def shutdown_mcp_pool() -> None:
    """Explicitly closes and shuts down any active MCPSessionPool instance."""
    pool = MCPSessionPool._instance
    if pool is not None:
        pool.shutdown()


@asynccontextmanager
async def mcp_pipeline_session(session_id: str = "default"):
    """
    Convenience context manager to hold an MCP session open for a pipeline run.
    Usage:
        async with mcp_pipeline_session(session_id=run_id):
            ...
    """
    async with MCPSessionPool.get_instance().pipeline_session(session_id) as session:
        yield session


async def aget_adapter_tools(session_id: Optional[str] = None):
    """Returns LangChain-adapted tools via langchain-mcp-adapters from active session."""
    pool = MCPSessionPool.get_instance()
    if session_id and session_id in pool._pool:
        return pool._pool[session_id]["tools"]
    if pool._worker_tools:
        return pool._worker_tools
    async with create_connected_server_and_client_session(mcp._mcp_server) as session:
        return await load_mcp_tools(session=session)


async def _execute_mcp_tool(tool_name: str, args: Dict[str, Any], session_id: Optional[str] = None) -> Any:
    """
    Executes an MCP tool through langchain-mcp-adapters reusing active MCP protocol session.
    """
    return await MCPSessionPool.get_instance().execute_tool(tool_name, args, session_id=session_id)


async def _read_mcp_resource(uri: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Reads an MCP resource through the active MCP protocol session with deterministic fallback.
    """
    return await MCPSessionPool.get_instance().read_resource(uri, session_id=session_id)


def _run_coroutine_sync(coro):
    """Safely runs a coroutine in both sync and async contexts."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()
    else:
        return asyncio.run(coro)


class MCPClient:
    """MCP Client powered by langchain-mcp-adapters and MCP protocol sessions.

    Wraps protocol-level MCP tool invocations with:
    - langchain-mcp-adapters tool loading with persistent session reuse
    - Full span / Phoenix trace recording
    - Unified log emission (logs/unified_trace.jsonl)
    - MCP transcript logging (logs/mcp_transcript.jsonl)
    - Tool call logging (logs/tool_calls.jsonl)
    """

    @classmethod
    def read_resource_manifest(
        cls,
        run_id: Optional[str] = None,
        step_id: Optional[str] = None,
        application_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reads policy-corpus://index resource manifest via MCP protocol."""
        return _run_coroutine_sync(cls.aread_resource_manifest(run_id, step_id, application_id))

    @classmethod
    async def aread_resource_manifest(
        cls,
        run_id: Optional[str] = None,
        step_id: Optional[str] = None,
        application_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Asynchronously reads policy-corpus://index resource via MCP protocol."""
        from src.context.execution_context import resolve_identity
        ident = resolve_identity(explicit_run_id=run_id, explicit_app_id=application_id, explicit_step_id=step_id or "step-mcp-resource-manifest", required=False)
        effective_run_id = ident["run_id"]
        effective_step_id = ident["step_id"]
        effective_app_id = ident["application_id"]

        start_time = time.time()
        try:
            data = await _read_mcp_resource("policy-corpus://index")
            latency_ms = (time.time() - start_time) * 1000.0
            log_mcp_event(
                event_type="resource_read",
                resource_or_tool="policy-corpus://index",
                caller="policy_selector",
                details={"policy_count": len(data.get("policies", {}))},
                run_id=effective_run_id,
                step_id=effective_step_id,
                application_id=effective_app_id,
            )
            return data
        except Exception as exc:
            logger.error("Failed to read MCP resource policy-corpus://index: %s", exc)
            log_mcp_event(
                event_type="resource_read",
                resource_or_tool="policy-corpus://index",
                caller="policy_selector",
                details={"error": str(exc), "status": "error"},
                run_id=effective_run_id,
                step_id=effective_step_id,
                application_id=effective_app_id,
            )
            if not isinstance(exc, MCPUnavailableError):
                raise MCPUnavailableError(f"Failed to read MCP resource policy-corpus://index: {exc}") from exc
            raise

    @classmethod
    def call_get_policy_document(
        cls,
        policy_id: str,
        version: str,
        run_id: Optional[str] = None,
        step_id: Optional[str] = None,
        application_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synchronously invokes get_policy_document MCP tool via adapter with persistent session."""
        return _run_coroutine_sync(cls.acall_get_policy_document(policy_id, version, run_id, step_id, application_id))

    @classmethod
    async def acall_get_policy_document(
        cls,
        policy_id: str,
        version: str,
        run_id: Optional[str] = None,
        step_id: Optional[str] = None,
        application_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Asynchronously invokes get_policy_document MCP tool via langchain-mcp-adapters."""
        from src.context.execution_context import resolve_identity
        ident = resolve_identity(explicit_run_id=run_id, explicit_app_id=application_id, explicit_step_id=step_id or "step-mcp-get-policy", required=False)
        effective_run_id = ident["run_id"]
        effective_step_id = ident["step_id"]
        effective_app_id = ident["application_id"]

        start_time = time.time()
        args = {"policy_id": policy_id, "version": version}
        try:
            res = await _execute_mcp_tool("get_policy_document", args)
            status = "success" if "error" not in res else "not_found"
        except Exception as exc:
            end_time = time.time()
            latency_ms = round((end_time - start_time) * 1000, 2)
            logger.error("MCP get_policy_document via adapter failed: %s", exc)
            tracer.record_span(
                name="mcp.get_policy_document",
                span_kind="tool",
                start_time=start_time,
                end_time=end_time,
                inputs=args,
                outputs={"status": "error", "error": str(exc)},
                run_id=effective_run_id,
                step_id=effective_step_id,
                application_id=effective_app_id,
            )
            log_tool_call(
                agent="mcp_client",
                tool_name="mcp.get_policy_document",
                args=args,
                result={"status": "error", "error": str(exc)},
                latency_ms=latency_ms,
                status="error",
                run_id=effective_run_id,
                step_id=effective_step_id,
                application_id=effective_app_id,
            )
            log_mcp_event(
                event_type="tool_call",
                resource_or_tool="get_policy_document",
                caller="policy_agent",
                details={"policy_id": policy_id, "version": version, "error": str(exc), "status": "error"},
                run_id=effective_run_id,
                step_id=effective_step_id,
                application_id=effective_app_id,
            )
            if not isinstance(exc, MCPUnavailableError):
                raise MCPUnavailableError(f"MCP get_policy_document failed: {exc}") from exc
            raise

        end_time = time.time()
        latency_ms = round((end_time - start_time) * 1000, 2)

        tracer.record_span(
            name="mcp.get_policy_document",
            span_kind="tool",
            start_time=start_time,
            end_time=end_time,
            inputs=args,
            outputs={"status": status},
            run_id=effective_run_id,
            step_id=effective_step_id,
            application_id=effective_app_id,
        )
        log_tool_call(
            agent="mcp_client",
            tool_name="mcp.get_policy_document",
            args=args,
            result={"status": status},
            latency_ms=latency_ms,
            status=status,
            run_id=effective_run_id,
            step_id=effective_step_id,
            application_id=effective_app_id,
        )
        log_mcp_event(
            event_type="tool_call",
            resource_or_tool="get_policy_document",
            caller="policy_agent",
            details={"policy_id": policy_id, "version": version, "found": "error" not in res},
            run_id=effective_run_id,
            step_id=effective_step_id,
            application_id=effective_app_id,
        )
        return res

    @classmethod
    def call_compute_affordability(
        cls,
        income_amount: float,
        income_period: str,
        existing_obligations: List[Dict[str, Any]],
        dti_max_threshold: float = 0.40,
        run_id: Optional[str] = None,
        step_id: Optional[str] = None,
        application_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synchronously invokes compute_affordability MCP tool via adapter with persistent session."""
        return _run_coroutine_sync(
            cls.acall_compute_affordability(
                income_amount=income_amount,
                income_period=income_period,
                existing_obligations=existing_obligations,
                dti_max_threshold=dti_max_threshold,
                run_id=run_id,
                step_id=step_id,
                application_id=application_id,
            )
        )

    @classmethod
    async def acall_compute_affordability(
        cls,
        income_amount: float,
        income_period: str,
        existing_obligations: List[Dict[str, Any]],
        dti_max_threshold: float = 0.40,
        run_id: Optional[str] = None,
        step_id: Optional[str] = None,
        application_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Asynchronously invokes compute_affordability MCP tool via langchain-mcp-adapters."""
        from src.context.execution_context import resolve_identity
        ident = resolve_identity(explicit_run_id=run_id, explicit_app_id=application_id, explicit_step_id=step_id or "step-mcp-affordability", required=False)
        effective_run_id = ident["run_id"]
        effective_step_id = ident["step_id"]
        effective_app_id = ident["application_id"]

        start_time = time.time()
        args = {
            "income_amount": income_amount,
            "income_period": income_period,
            "existing_obligations": existing_obligations,
            "dti_max_threshold": dti_max_threshold,
        }

        # Validate domain input invariants
        if income_amount <= 0:
            raise ValueError(f"income_amount must be positive; got {income_amount}")

        try:
            res = await _execute_mcp_tool("compute_affordability", args)
            status = "success"
        except ValueError:
            raise
        except Exception as exc:
            end_time = time.time()
            latency_ms = round((end_time - start_time) * 1000, 2)
            logger.error("MCP compute_affordability via adapter failed: %s", exc)
            tracer.record_span(
                name="mcp.compute_affordability",
                span_kind="tool",
                start_time=start_time,
                end_time=end_time,
                inputs={"income_amount": income_amount, "dti_max_threshold": dti_max_threshold},
                outputs={"status": "error", "error": str(exc)},
                run_id=effective_run_id,
                step_id=effective_step_id,
                application_id=effective_app_id,
            )
            log_tool_call(
                agent="mcp_client",
                tool_name="mcp.compute_affordability",
                args={"income_amount": income_amount, "dti_max_threshold": dti_max_threshold},
                result={"status": "error", "error": str(exc)},
                latency_ms=latency_ms,
                status="error",
                run_id=effective_run_id,
                step_id=effective_step_id,
                application_id=effective_app_id,
            )
            log_mcp_event(
                event_type="tool_call",
                resource_or_tool="compute_affordability",
                caller="eligibility_agent",
                details={"error": str(exc), "status": "error"},
                run_id=effective_run_id,
                step_id=effective_step_id,
                application_id=effective_app_id,
            )
            if not isinstance(exc, MCPUnavailableError):
                raise MCPUnavailableError(f"MCP compute_affordability failed: {exc}") from exc
            raise

        end_time = time.time()
        latency_ms = round((end_time - start_time) * 1000, 2)

        tracer.record_span(
            name="mcp.compute_affordability",
            span_kind="tool",
            start_time=start_time,
            end_time=end_time,
            inputs={"income_amount": income_amount, "dti_max_threshold": dti_max_threshold},
            outputs={"dti": res.get("dti"), "breach": res.get("breach")},
            run_id=effective_run_id,
            step_id=effective_step_id,
            application_id=effective_app_id,
        )
        log_tool_call(
            agent="mcp_client",
            tool_name="mcp.compute_affordability",
            args={"income_amount": income_amount, "dti_max_threshold": dti_max_threshold},
            result={"dti": res.get("dti"), "breach": res.get("breach")},
            latency_ms=latency_ms,
            status=status,
            run_id=effective_run_id,
            step_id=effective_step_id,
            application_id=effective_app_id,
        )
        log_mcp_event(
            event_type="tool_call",
            resource_or_tool="compute_affordability",
            caller="eligibility_agent",
            details=res,
            run_id=effective_run_id,
            step_id=effective_step_id,
            application_id=effective_app_id,
        )
        return res
