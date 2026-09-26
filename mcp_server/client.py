"""
Client helper for calling MCP tools and reading MCP resources.
Uses langchain-mcp-adapters and MCP protocol client session over in-memory streams.
Per plan.md Section 4.5, 13.4 & 14.3.
"""

import json
import time
import asyncio
import logging
from typing import Dict, Any, List, Optional
from pydantic import AnyUrl

from mcp_server.server import mcp
from mcp.shared.memory import create_connected_server_and_client_session
from langchain_mcp_adapters.tools import load_mcp_tools
from src.observability.unified_logger import log_mcp_event, log_tool_call
from src.observability.tracing import tracer

logger = logging.getLogger(__name__)


async def aget_adapter_tools():
    """Returns LangChain-adapted tools via langchain-mcp-adapters."""
    async with create_connected_server_and_client_session(mcp._mcp_server) as session:
        return await load_mcp_tools(session=session)


async def _execute_mcp_tool(tool_name: str, args: Dict[str, Any]) -> Any:
    """
    Executes an MCP tool through langchain-mcp-adapters over an active MCP protocol session.
    """
    async with create_connected_server_and_client_session(mcp._mcp_server) as session:
        tools = await load_mcp_tools(session=session)
        tool = next((t for t in tools if t.name == tool_name), None)
        if tool is None:
            raise RuntimeError(f"MCP tool '{tool_name}' not registered in MCP server via adapter")

        raw_result = await tool.ainvoke(args)

        # Parse text content from LangChain tool output
        if isinstance(raw_result, list) and len(raw_result) > 0 and isinstance(raw_result[0], dict) and "text" in raw_result[0]:
            return json.loads(raw_result[0]["text"])
        elif isinstance(raw_result, str):
            return json.loads(raw_result)
        return raw_result


async def _read_mcp_resource(uri: str) -> Dict[str, Any]:
    """
    Reads an MCP resource through the active MCP protocol session.
    """
    async with create_connected_server_and_client_session(mcp._mcp_server) as session:
        res = await session.read_resource(AnyUrl(uri))
        if hasattr(res, "contents") and len(res.contents) > 0:
            text = res.contents[0].text
            return json.loads(text)
        return {}


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
    - langchain-mcp-adapters tool loading
    - Full span / Phoenix trace recording
    - Unified log emission (logs/unified_trace.jsonl)
    - MCP transcript logging (logs/mcp_transcript.jsonl)
    - Tool call logging (logs/tool_calls.jsonl)
    """

    @staticmethod
    def read_resource_manifest() -> Dict[str, Any]:
        """Reads policy-corpus://index resource manifest via MCP protocol."""
        return _run_coroutine_sync(MCPClient.aread_resource_manifest())

    @staticmethod
    async def aread_resource_manifest() -> Dict[str, Any]:
        """Asynchronously reads policy-corpus://index resource via MCP protocol."""
        start_time = time.time()
        try:
            data = await _read_mcp_resource("policy-corpus://index")
            latency_ms = (time.time() - start_time) * 1000.0
            log_mcp_event(
                event_type="resource_read",
                resource_or_tool="policy-corpus://index",
                caller="policy_selector",
                details={"policy_count": len(data.get("policies", {}))},
            )
            return data
        except Exception as exc:
            logger.error("Failed to read MCP resource policy-corpus://index: %s", exc)
            # Fallback to direct manifest if session read fails
            from mcp_server.server import get_policy_corpus_index
            return json.loads(get_policy_corpus_index())

    @staticmethod
    def call_get_policy_document(policy_id: str, version: str) -> Dict[str, Any]:
        """Synchronously invokes get_policy_document MCP tool via adapter."""
        return _run_coroutine_sync(MCPClient.acall_get_policy_document(policy_id, version))

    @staticmethod
    async def acall_get_policy_document(policy_id: str, version: str) -> Dict[str, Any]:
        """Asynchronously invokes get_policy_document MCP tool via langchain-mcp-adapters."""
        start_time = time.time()
        args = {"policy_id": policy_id, "version": version}
        try:
            res = await _execute_mcp_tool("get_policy_document", args)
            status = "success" if "error" not in res else "not_found"
        except Exception as exc:
            logger.error("MCP get_policy_document via adapter failed: %s", exc)
            res = {"error": str(exc)}
            status = "error"

        end_time = time.time()
        latency_ms = round((end_time - start_time) * 1000, 2)

        tracer.record_span(
            name="mcp.get_policy_document",
            span_kind="tool",
            start_time=start_time,
            end_time=end_time,
            inputs=args,
            outputs={"status": status},
            run_id="RUN-MCP",
            step_id="step-mcp-get-policy",
        )
        log_tool_call(
            agent="mcp_client",
            tool_name="mcp.get_policy_document",
            args=args,
            result={"status": status},
            latency_ms=latency_ms,
            status=status,
        )
        log_mcp_event(
            event_type="tool_call",
            resource_or_tool="get_policy_document",
            caller="policy_agent",
            details={"policy_id": policy_id, "version": version, "found": "error" not in res},
        )
        return res

    @staticmethod
    def call_compute_affordability(
        income_amount: float,
        income_period: str,
        existing_obligations: List[Dict[str, Any]],
        dti_max_threshold: float = 0.40,
    ) -> Dict[str, Any]:
        """Synchronously invokes compute_affordability MCP tool via adapter."""
        return _run_coroutine_sync(
            MCPClient.acall_compute_affordability(
                income_amount=income_amount,
                income_period=income_period,
                existing_obligations=existing_obligations,
                dti_max_threshold=dti_max_threshold,
            )
        )

    @staticmethod
    async def acall_compute_affordability(
        income_amount: float,
        income_period: str,
        existing_obligations: List[Dict[str, Any]],
        dti_max_threshold: float = 0.40,
    ) -> Dict[str, Any]:
        """Asynchronously invokes compute_affordability MCP tool via langchain-mcp-adapters."""
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
            logger.error("MCP compute_affordability via adapter failed: %s", exc)
            res = {"error": str(exc)}
            status = "error"

        end_time = time.time()
        latency_ms = round((end_time - start_time) * 1000, 2)

        tracer.record_span(
            name="mcp.compute_affordability",
            span_kind="tool",
            start_time=start_time,
            end_time=end_time,
            inputs={"income_amount": income_amount, "dti_max_threshold": dti_max_threshold},
            outputs={"dti": res.get("dti"), "breach": res.get("breach")},
            run_id="RUN-MCP",
            step_id="step-mcp-affordability",
        )
        log_tool_call(
            agent="mcp_client",
            tool_name="mcp.compute_affordability",
            args={"income_amount": income_amount, "dti_max_threshold": dti_max_threshold},
            result={"dti": res.get("dti"), "breach": res.get("breach")},
            latency_ms=latency_ms,
            status=status,
        )
        log_mcp_event(
            event_type="tool_call",
            resource_or_tool="compute_affordability",
            caller="eligibility_agent",
            details=res,
        )
        return res
