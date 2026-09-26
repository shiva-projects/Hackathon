"""
Tests for Observability and Phoenix Tracing.
Verifies that the tracing layer only records real measured latencies and never fabricates fake spans or latencies.
"""

import time
import pytest
import pandas as pd
from src.observability.tracing import ExecutionTracer


def test_tracer_does_not_fabricate_latency_when_empty(tmp_path):
    """Verifies that an empty tracer never outputs synthetic 150ms or fake latency rows."""
    tracer = ExecutionTracer(project_name="test-empty")
    assert len(tracer.spans) == 0

    out_file = tmp_path / "test_spans.parquet"
    df = tracer.export_spans_dataframe(str(out_file))

    assert isinstance(df, pd.DataFrame)
    if not df.empty:
        # If any rows exist, none can be fabricated default latency 150.0ms
        assert not (df["latency_ms"] == 150.0).any(), "Fabricated 150ms latency detected in export!"
    else:
        assert len(df) == 0


def test_tracer_records_real_measured_latency():
    """Verifies that recorded spans compute latency directly from measured start/end timestamps."""
    tracer = ExecutionTracer(project_name="test-real")
    t0 = time.time()
    time.sleep(0.02)  # sleep 20ms
    t1 = time.time()

    span = tracer.record_span(
        name="test_node",
        span_kind="acting",
        start_time=t0,
        end_time=t1,
        inputs={"key": "val"},
        outputs={"status": "ok"},
        run_id="RUN-TEST",
    )

    expected_latency = (t1 - t0) * 1000.0
    assert abs(span["latency_ms"] - expected_latency) < 1.0
    assert span["latency_ms"] >= 15.0  # at least ~20ms, not arbitrary 150.0
    assert span["latency_ms"] != 150.0
