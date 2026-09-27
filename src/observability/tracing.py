"""
Observability and Phoenix OTEL Tracing Integration.
Captures spans with category mapping: thinking (LLM), acting (agent orchestration), tool (MCP/RAG).

Phoenix OTEL wiring:
  - Uses phoenix.otel.register() to create a real TracerProvider with OTLP exporter.
  - Passes the TracerProvider into LangChainInstrumentor so LangGraph spans go to Phoenix.
  - ExecutionTracer records application-level spans for latency and audit logging.
  - ExecutionTracer.spans are application metrics, NOT Phoenix OTEL spans.

Per plan.md Section 7.2 & Non-Negotiable Rule 9 (Phoenix failures never block underwriting).
"""

import os
import time
import asyncio
import logging
from typing import Optional, Dict, Any, Callable
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)

# Global references for lazy loading
_PHOENIX_AVAILABLE = None
_px_client = None
_phoenix_session = None
_tracer_provider = None  # Real OTEL TracerProvider registered via phoenix.otel.register()


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Checks if a TCP port is open and accepting connections."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.0)
    try:
        res = s.connect_ex((host, port))
        return res == 0
    except Exception:
        return False
    finally:
        s.close()


def ensure_phoenix_server_running(port: int = 6006) -> bool:
    """
    Ensures that a Phoenix collector server is actively running and accepting connections.
    If not already running on port 6006, launches px.launch_app(port=port, host="127.0.0.1", run_in_thread=True).
    This guarantees that the single documented pipeline run command is completely self-contained per NFR-02.
    """
    global _phoenix_session
    import time

    if is_port_in_use(port):
        logger.info("[Phoenix OTEL] Phoenix collector already running on port %d", port)
        return True

    try:
        import phoenix as px
        logger.info("[Phoenix OTEL] Auto-launching in-process Phoenix server on port %d...", port)
        _phoenix_session = px.launch_app(port=port, host="127.0.0.1", run_in_thread=True)
        for _ in range(12):
            time.sleep(0.5)
            if is_port_in_use(port):
                logger.info("[Phoenix OTEL] Phoenix server successfully started and listening on port %d", port)
                return True
        logger.warning("[Phoenix OTEL] Phoenix launch_app called, port %d check timed out", port)
        return True
    except Exception as e:
        logger.warning("[Phoenix OTEL] Could not auto-launch Phoenix server: %s", e)
        return False


class ExecutionTracer:
    """
    Manages in-process application-level tracing spans.

    IMPORTANT: ExecutionTracer.spans are application-level audit records
    measuring node execution times. They are NOT Phoenix OTEL spans.
    Phoenix OTEL spans are emitted automatically by LangChainInstrumentor
    through the registered TracerProvider and sent to the Phoenix collector.
    """

    def __init__(self, project_name: str = "loan-copilot"):
        self.project_name = project_name
        self.spans = []
        self._initialized = False

    def initialize(self) -> bool:
        """
        Initializes real Phoenix OTEL instrumentation.

        Uses phoenix.otel.register() to create a TracerProvider with a real
        OTLP/HTTP exporter pointing at the running Phoenix instance.
        Passes the TracerProvider to LangChainInstrumentor so LangGraph
        LLM/chain spans are automatically captured and sent to Phoenix.
        """
        global _PHOENIX_AVAILABLE, _phoenix_session, _px_client, _tracer_provider
        if _PHOENIX_AVAILABLE is False:
            return False

        try:
            if _PHOENIX_AVAILABLE is None:
                _PHOENIX_AVAILABLE = True

            port = int(os.environ.get("PHOENIX_PORT", "6006"))
            endpoint_base = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", f"http://localhost:{port}")
            project_name = os.environ.get("PHOENIX_PROJECT_NAME", self.project_name)

            # Auto-ensure Phoenix server is running so collector is live
            ensure_phoenix_server_running(port)

            # Ensure OTLPSpanExporter has _headers attribute (fixes bug in phoenix 20.16 / otel in Python 3.13)
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                if not hasattr(OTLPSpanExporter, "_headers"):
                    OTLPSpanExporter._headers = {}
            except Exception:
                pass

            # --- Step 1: Register real OTEL TracerProvider with Phoenix OTLP exporter ---
            try:
                from phoenix.otel import register as phoenix_register
                _tracer_provider = phoenix_register(
                    project_name=project_name,
                    endpoint=f"{endpoint_base}/v1/traces",
                    batch=False,
                    verbose=False,
                )
                logger.info(
                    "[Phoenix OTEL] TracerProvider registered. "
                    "OTLP exporter → %s/v1/traces (project=%s)",
                    endpoint_base, project_name,
                )
            except Exception as e:
                logger.warning("[Phoenix OTEL] register() failed (%s). Spans will NOT reach Phoenix.", e)
                _tracer_provider = None

            # --- Step 2: Instrument LangChain/LangGraph with the real TracerProvider ---
            try:
                from openinference.instrumentation.langchain import LangChainInstrumentor
                instrumentor = LangChainInstrumentor()
                if _tracer_provider is not None:
                    instrumentor.instrument(tracer_provider=_tracer_provider)
                else:
                    instrumentor.instrument()
                logger.info("[Phoenix OTEL] LangChainInstrumentor wired.")
            except Exception as e:
                logger.debug("LangChainInstrumentor already instrumented or failed: %s", e)

            # --- Step 3: Create Phoenix Client for querying spans from Phoenix ---
            try:
                from phoenix.client import Client
                _px_client = Client(base_url=endpoint_base)
                logger.info("[Phoenix OTEL] Client connected to %s", endpoint_base)
            except Exception as e:
                logger.debug("Phoenix Client unavailable on %s: %s", endpoint_base, e)
                _px_client = None

            self._initialized = True
            return True

        except Exception as e:
            _PHOENIX_AVAILABLE = False
            logger.warning("Phoenix instrumentation degraded: %s", e)
            return False

    def flush(self) -> None:
        """Flushes tracer provider spans to Phoenix collector."""
        global _tracer_provider
        if _tracer_provider is not None:
            try:
                _tracer_provider.force_flush(timeout_millis=5000)
            except Exception:
                pass

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
        """
        Records an application-level span with measured wall-clock latency.
        These spans are application audit records — NOT Phoenix OTEL spans.
        Phoenix OTEL spans are emitted automatically by LangChainInstrumentor.
        """
        from src.observability.span_sanitizer import sanitize_data

        latency_ms = (end_time - start_time) * 1000.0
        span = {
            "span_id": f"span-{name}-{int(start_time*1000)}",
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
            "trace_source": "application_tracer",  # explicit: NOT Phoenix OTEL spans
        }
        self.spans.append(span)
        return span

    def export_spans_dataframe(self, output_path: str = "traces/phoenix_spans.parquet") -> Optional[pd.DataFrame]:
        """
        Exports span data to parquet.

        Priority:
        1. Try Phoenix client get_spans_dataframe() — real Phoenix OTEL spans.
        2. Fall back to locally collected application-level spans.
        3. If neither, return empty DataFrame.

        The trace_source column always documents where each record came from.
        """
        global _px_client, _PHOENIX_AVAILABLE
        if not self._initialized:
            self.initialize()
        self.flush()
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        port = int(os.environ.get("PHOENIX_PORT", "6006"))
        endpoint_base = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", f"http://localhost:{port}")
        ensure_phoenix_server_running(port)

        if _px_client is None:
            try:
                from phoenix.client import Client
                _px_client = Client(base_url=endpoint_base)
            except Exception as e:
                logger.debug("Phoenix Client init in export_spans_dataframe failed: %s", e)

        df = None
        # Try Phoenix collector first (real OTEL spans)
        if _PHOENIX_AVAILABLE and _px_client:
            try:
                px_df = _px_client.spans.get_spans_dataframe(project_name=self.project_name, limit=10000, timeout=30)
                if px_df is not None and not px_df.empty:
                    # Enrich Phoenix dataframe with standardized analysis columns
                    if "latency_ms" not in px_df.columns and "start_time" in px_df.columns and "end_time" in px_df.columns:
                        px_df["latency_ms"] = (pd.to_datetime(px_df["end_time"]) - pd.to_datetime(px_df["start_time"])).dt.total_seconds() * 1000.0
                    if "context.span_id" in px_df.columns and "span_id" not in px_df.columns:
                        px_df["span_id"] = px_df["context.span_id"]
                    if "context.trace_id" in px_df.columns and "run_id" not in px_df.columns:
                        px_df["run_id"] = px_df["context.trace_id"]
                    if "attributes.openinference.span.kind" in px_df.columns:
                        def _map_kind(k):
                            s = str(k).upper()
                            if "LLM" in s:
                                return "thinking"
                            if "TOOL" in s:
                                return "tool"
                            return "acting"
                        px_df["span_kind"] = px_df["attributes.openinference.span.kind"].apply(_map_kind)
                    px_df["trace_source"] = "phoenix"
                    df = px_df
                    logger.info("[Phoenix OTEL] Retrieved %d spans from Phoenix collector (%d columns, trace_source=phoenix).", len(df), len(df.columns))
            except Exception as e:
                logger.debug("Phoenix client get_spans_dataframe unavailable: %s", e)

        if df is None or df.empty:
            # Use application-level span records (labelled explicitly as such)
            if self.spans:
                df = pd.DataFrame(self.spans)
                logger.info(
                    "[ExecutionTracer] Phoenix not available or empty. "
                    "Using %d application-level spans (trace_source=application_tracer).",
                    len(df),
                )
            else:
                logger.warning("No spans available from Phoenix or application tracer.")
                df = pd.DataFrame(columns=[
                    "name", "span_kind", "latency_ms", "run_id", "step_id", "status", "trace_source"
                ])

        if not df.empty:
            try:
                df.to_parquet(out_p, index=False)
            except Exception as e:
                logger.warning("Parquet export failed (%s), writing jsonl fallback", e)
                df.to_json(out_p.with_suffix(".jsonl"), orient="records", lines=True)

        return df

    def get_phoenix_span_count(self) -> int:
        """
        Queries Phoenix collector for number of spans currently stored.
        Returns 0 if Phoenix is unavailable or returns no data.
        """
        global _px_client, _PHOENIX_AVAILABLE
        if not self._initialized:
            self.initialize()
        self.flush()

        port = int(os.environ.get("PHOENIX_PORT", "6006"))
        endpoint_base = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", f"http://localhost:{port}")
        ensure_phoenix_server_running(port)

        if _px_client is None:
            try:
                from phoenix.client import Client
                _px_client = Client(base_url=endpoint_base)
            except Exception:
                pass

        if not (_PHOENIX_AVAILABLE and _px_client):
            return 0
        try:
            px_df = _px_client.spans.get_spans_dataframe(project_name=self.project_name, limit=10000)
            if px_df is not None and not px_df.empty:
                return len(px_df)
        except Exception as e:
            logger.debug("Could not query Phoenix span count: %s", e)
        return 0


# Global singleton tracer
tracer = ExecutionTracer()


def traced_node(name: str, span_kind: str, fn: Callable) -> Any:
    """
    Wraps a LangGraph node function with real execution tracing.
    Exposes both synchronous (.invoke) and asynchronous (.ainvoke / .astream) entry points via RunnableLambda.
    Application-level span recorded by ExecutionTracer; Phoenix OTEL spans emitted automatically by LangChainInstrumentor.
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
