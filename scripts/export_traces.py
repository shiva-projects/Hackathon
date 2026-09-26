"""
Export Phoenix Spans to Parquet.
Per plan.md Section 7.2 & 8.
Reads Phoenix/OpenInference spans and saves to traces/phoenix_spans.parquet.
"""

import sys
import json
from pathlib import Path
import pandas as pd

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.observability.tracing import tracer


def export_traces(output_path: str = "traces/phoenix_spans.parquet") -> str:
    print(f"Exporting traces to: {output_path}")
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    df = tracer.export_spans_dataframe(output_path)

    # If Phoenix collector had spans, mark them as phoenix-measured
    if df is not None and not df.empty and len(df) > 1:
        if "trace_source" not in df.columns:
            df["trace_source"] = "phoenix"
        df.to_parquet(out_p, index=False)
        print(f"Exported {len(df)} spans directly from Phoenix to {output_path}.")
        return output_path

    # Otherwise, reconstruct trace dataset from actual execution logs with exact measured wall-clock latencies
    records = []

    # 1. Ingest measured LLM calls (thinking spans)
    llm_path = Path("logs/llm_calls.jsonl")
    if llm_path.exists():
        for line in llm_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            lat = r.get("latency_ms")
            records.append({
                "span_id": f"span-llm-{len(records)+1:04d}",
                "name": f"llm.{r.get('provider', 'llm')}",
                "span_kind": "thinking",
                "latency_ms": float(lat) if lat is not None else None,
                "run_id": r.get("run_id", "RUN-001"),
                "step_id": f"step-llm-{r.get('provider', 'model')}",
                "status": "success",
                "application_id": "APP-001",
                "trace_source": "reconstructed",
            })

    # 2. Ingest measured Tool calls (tool spans)
    tc_path = Path("logs/tool_calls.jsonl")
    if tc_path.exists():
        for line in tc_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            lat = r.get("latency_ms")
            records.append({
                "span_id": f"span-tool-{len(records)+1:04d}",
                "name": r.get("tool_name", "tool_call"),
                "span_kind": "tool",
                "latency_ms": float(lat) if lat is not None else None,
                "run_id": r.get("run_id", "RUN-001"),
                "step_id": r.get("step_id", "step-tool"),
                "status": r.get("status", "success"),
                "application_id": r.get("application_id", "APP-001"),
                "trace_source": "reconstructed",
            })

    # 3. Ingest measured Agent actions (acting/thinking spans)
    aa_path = Path("logs/agent_actions.jsonl")
    if aa_path.exists():
        for line in aa_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            span_kind = "thinking" if ("intent" in r.get("action", "") or "rationale" in r.get("action", "")) else "acting"
            lat = r.get("latency_ms")
            records.append({
                "span_id": f"span-agent-{len(records)+1:04d}",
                "name": r.get("actor", "agent"),
                "span_kind": span_kind,
                "latency_ms": float(lat) if lat is not None else None,
                "run_id": r.get("run_id", "RUN-001"),
                "step_id": f"step-{r.get('action')}",
                "status": "success",
                "application_id": r.get("application_id", "APP-001"),
                "trace_source": "reconstructed",
            })

    if records:
        df = pd.DataFrame(records)
        df.to_parquet(out_p, index=False)
        print(f"Exported {len(df)} spans to {output_path} (reconstructed from measured execution logs).")
        return output_path

    print(f"Exported spans to {output_path}.")
    return output_path


if __name__ == "__main__":
    export_traces()
