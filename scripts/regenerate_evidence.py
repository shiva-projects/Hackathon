#!/usr/bin/env python3
"""
scripts/regenerate_evidence.py — Locked 2nd command (NFR-02).
Derives and exports all evidence artifacts from the already-completed pipeline run.
Conforms strictly to plan.md Sections 9.2, 9.3, 13.1.
DOES NOT execute the pipeline itself.
"""

import sys
import json
import argparse
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from scripts.export_traces import export_traces
from scripts.run_eval import run_eval
from scripts.generate_golden_signals import generate_golden_signals
from scripts.verify_evidence import main as verify_evidence_main


def main():
    parser = argparse.ArgumentParser(description="Regenerate all evidence from the latest pipeline run.")
    parser.add_argument("--run-id", type=str, default=None, help="Explicit run ID to derive evidence from.")
    args = parser.parse_args()

    print("=" * 60)
    print("STEP 1: IDENTIFYING RUN SCOPE & ENSURING PHOENIX IS ACTIVE")
    print("=" * 60)
    
    from src.observability.tracing import ensure_phoenix_server_running
    ensure_phoenix_server_running()

    latest_run_file = PROJECT_ROOT / "reports" / "latest_run.json"
    run_id = args.run_id
    if not run_id:
        if latest_run_file.exists():
            with open(latest_run_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                run_id = data.get("run_id", "RUN-001")
        else:
            run_id = "RUN-001"
            
    print(f"Target Run ID: {run_id}")

    print("\n" + "=" * 60)
    print("STEP 2: RUNNING EVALUATION (reports/eval_report.json)")
    print("=" * 60)
    run_eval(output_path="reports/eval_report.json")

    print("\n" + "=" * 60)
    print("STEP 2b: REPLAYING DETERMINISTIC FAILURE CASES (AC-08)")
    print("=" * 60)
    from scripts.reproduce_failure import reproduce_wrong_policy_selection, reproduce_mcp_timeout, reproduce_rag_poisoning
    reproduce_wrong_policy_selection()
    reproduce_mcp_timeout()
    reproduce_rag_poisoning()

    print("\n" + "=" * 60)
    print("STEP 3: EXPORTING PHOENIX TRACES (traces/phoenix_spans.parquet)")
    print("=" * 60)
    export_traces(output_path="traces/phoenix_spans.parquet")

    print("\n" + "=" * 60)
    print("STEP 4: GENERATING GOLDEN SIGNALS & DASHBOARD")
    print("=" * 60)
    generate_golden_signals(
        traces_path="traces/phoenix_spans.parquet",
        cost_config_path="reports/cost_config.json",
        eval_report_path="reports/eval_report.json",
        output_json_path="reports/golden_signals.json",
        output_csv_path="reports/dashboard_data.csv",
    )

    print("\n" + "=" * 60)
    print("STEP 4b: CAPTURING GENUINE PHOENIX UI SCREENSHOT (reports/dashboard.png)")
    print("=" * 60)
    from scripts.capture_phoenix_ui import capture_phoenix_ui
    capture_phoenix_ui(output_path="reports/dashboard.png")

    print("\n" + "=" * 60)
    print("STEP 5: VERIFYING COMMITTED EVIDENCE (scripts/verify_evidence.py)")
    print("=" * 60)
    try:
        verify_evidence_main()
    except SystemExit as e:
        if e.code != 0:
            print(f"\n[ERROR] verify_evidence failed with exit code {e.code}")
            sys.exit(e.code)

    print("\n" + "=" * 60)
    print("ALL EVIDENCE REGENERATED AND VERIFIED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    main()
