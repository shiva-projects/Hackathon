"""
Observability and Phoenix Tracing Integration.
Captures spans with category mapping: thinking (LLM), acting (agent orchestration), tool (MCP/RAG).
Per plan.md Section 7.2 & Non-Negotiable Rule 9 (Phoenix failures never block underwriting).
"""

import os
import time
import asyncio
from typing import Optional, Dict, Any, Callable
from pathlib import Path
import pandas as pd

# Global references for lazy loading
_PHOENIX_AVAILABLE = None
_px_client = None
_phoenix_session = None


class ExecutionTracer:
    """
    Manages in-process tracing spans, exporting Phoenix spans and local span records.
    """

    def __init__(self, project_name: str = "loan-copilot"):
        self.project_name = project_name
        self.spans = []
        self._initialized = False

    def initialize(self) -> bool:
        """Initializes Phoenix and OpenInference instrumentation if available."""
        global _PHOENIX_AVAILABLE, _phoenix_session, _px_client
        if _PHOENIX_AVAILABLE is False:
            return False

        try:
            if _PHOENIX_AVAILABLE is None:
                import phoenix as px
                from openinference.instrumentation.langchain import LangChainInstrumentor
                _PHOENIX_AVAILABLE = True

            endpoint = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")
            try:
                LangChainInstrumentor().instrument()
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug(f"LangChainInstrumentor already instrumented or failed: {e}")
            try:
                _px_client = px.Client(endpoint=endpoint)
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug(f"Phoenix px.Client unavailable on {endpoint}: {e}")
                _px_client = None
            self._initialized = True
            return True
        except Exception as e:
            _PHOENIX_AVAILABLE = False
            print(f"Warning: Phoenix instrumentation degraded: {e}")
            return False

    def record_span(
        self,
        name: str,
        span_kind: str,  # "thinking", "acting", "tool"
        start_time: float,
        end_time: float,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        run_id: str,
        step_id: Optional[str] = None,
        application_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Manually records a structured span with sanitization."""
        from src.observability.span_sanitizer import sanitize_data

        latency_ms = (end_time - start_time) * 1000.0
        span = {
            "name": name,
            "span_kind": span_kind,  # "thinking" | "acting" | "tool"
            "start_time": start_time,
            "end_time": end_time,
            "latency_ms": round(latency_ms, 2),
            "run_id": run_id,
            "step_id": step_id or f"step-{name}",
            "application_id": application_id,
            "inputs": sanitize_data(inputs),
            "outputs": sanitize_data(outputs),
            "error": error,
            "status": "error" if error else "success",
        }
        self.spans.append(span)
        return span

    def export_spans_dataframe(self, output_path: str = "traces/phoenix_spans.parquet") -> Optional[pd.DataFrame]:
        """
        Exports collected spans to parquet dataframe.
        First tries px.Client().get_spans_dataframe(), falls back to local span collection.
        """
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        df = None
        if _PHOENIX_AVAILABLE and _px_client:
            try:
                px_df = _px_client.get_spans_dataframe()
                if px_df is not None and not px_df.empty:
                    df = px_df
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug(f"Phoenix client get_spans_dataframe unavailable: {e}")

        if df is None or df.empty:
            # Create dataframe from recorded spans if present
            if self.spans:
                df = pd.DataFrame(self.spans)
            else:
                # No spans recorded - do not fabricate fake spans or fake latency
                df = pd.DataFrame(columns=[
                    "name", "span_kind", "latency_ms", "run_id", "step_id", "status"
                ])

        # Save to parquet only if valid dataframe exists
        if not df.empty:
            try:
                df.to_parquet(out_p, index=False)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Parquet export failed ({e}), writing jsonl fallback")
                df.to_json(out_p.with_suffix(".jsonl"), orient="records", lines=True)

        return df


# Global singleton tracer
tracer = ExecutionTracer()


def traced_node(name: str, span_kind: str, fn: Callable) -> Any:
    """
    Wraps a LangGraph node function with real execution tracing.
    Exposes both synchronous (.invoke) and asynchronous (.ainvoke / .astream) entry points via RunnableLambda.
    """
    import inspect
    import concurrent.futures
    from langchain_core.runnables import RunnableLambda

    is_async = inspect.iscoroutinefunction(fn)

    async def async_wrapper(state: Dict[str, Any]) -> Dict[str, Any]:
        start = time.time()
        session_id = state.get("session_id", "RUN-UNKNOWN")
        app_id = state.get("application_id", "APP-UNKNOWN")
        try:
            if is_async:
                result = await fn(state)
            else:
                result = fn(state)
            end = time.time()
            tracer.record_span(
                name=name,
                span_kind=span_kind,
                start_time=start,
                end_time=end,
                inputs={"application_id": app_id, "step_count": state.get("step_count", 0), "intent": state.get("intent")},
                outputs={"request_status": result.get("request_status"), "ai_recommendation": result.get("ai_recommendation")},
                run_id=session_id,
                application_id=app_id,
                step_id=f"step-{name}",
            )
            return result
        except Exception as e:
            end = time.time()
            tracer.record_span(
                name=name,
                span_kind=span_kind,
                start_time=start,
                end_time=end,
                inputs={"application_id": app_id},
                outputs={"error": str(e)},
                run_id=session_id,
                application_id=app_id,
                step_id=f"step-{name}",
                error=str(e),
            )
            raise

    def sync_wrapper(state: Dict[str, Any]) -> Dict[str, Any]:
        start = time.time()
        session_id = state.get("session_id", "RUN-UNKNOWN")
        app_id = state.get("application_id", "APP-UNKNOWN")
        try:
            if is_async:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    result = pool.submit(lambda: asyncio.run(fn(state))).result()
            else:
                result = fn(state)
            end = time.time()
            tracer.record_span(
                name=name,
                span_kind=span_kind,
                start_time=start,
                end_time=end,
                inputs={"application_id": app_id, "step_count": state.get("step_count", 0), "intent": state.get("intent")},
                outputs={"request_status": result.get("request_status"), "ai_recommendation": result.get("ai_recommendation")},
                run_id=session_id,
                application_id=app_id,
                step_id=f"step-{name}",
            )
            return result
        except Exception as e:
            end = time.time()
            tracer.record_span(
                name=name,
                span_kind=span_kind,
                start_time=start,
                end_time=end,
                inputs={"application_id": app_id},
                outputs={"error": str(e)},
                run_id=session_id,
                application_id=app_id,
                step_id=f"step-{name}",
                error=str(e),
            )
            raise

    return RunnableLambda(sync_wrapper, afunc=async_wrapper)
