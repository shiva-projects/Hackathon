#!/usr/bin/env python3
"""
scripts/show_evidence.py — Offline read-only demo fallback viewer.
Conforms strictly to plan.md Section 16.2.
Reads ONLY committed files — NO live API or tool calls.
"""

import sys
import json
import argparse
from pathlib import Path
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent


def show_evidence(app_id: str):
    print("=" * 60)
    print(f"OFFLINE EVIDENCE SUMMARY: {app_id}")
    print("=" * 60)
    
    # 1. Output result
    result_path = REPO_ROOT / "outputs" / "sample_results" / f"{app_id}.json"
    if not result_path.exists():
        # try without .json if passed
        result_path = REPO_ROOT / "outputs" / "sample_results" / f"{Path(app_id).stem}.json"
        
    if result_path.exists():
        with open(result_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        print("\n[POLICY SELECTION & CITATIONS]")
        policy = data.get("policy_selected", {})
        print(f"  Policy ID   : {policy.get('policy_id')} (version: {policy.get('version')})")
        print(f"  Title       : {policy.get('title')}")
        citations = data.get("policy_citations", [])
        print(f"  Citations   : {len(citations)} rules cited")
        for c in citations:
            print(f"    - [{c.get('rule_id')}] {c.get('matched_text', '')[:60]}... (hash: {c.get('text_hash', '')[:12]}...)")
            
        print("\n[AFFORDABILITY & COMPUTATIONS]")
        afford = data.get("affordability", {})
        print(f"  Monthly Income: {afford.get('monthly_gross_income')}")
        print(f"  Monthly Oblig : {afford.get('monthly_obligations')}")
        print(f"  DTI Ratio     : {afford.get('dti')}")
        print(f"  Dispos Income : {afford.get('disposable_income')}")
        breaches = afford.get("breaches", [])
        print(f"  Breaches      : {breaches if breaches else 'None'}")
        
        print("\n[RISK EVALUATION]")
        flags = data.get("risk_flags", [])
        print(f"  Flags         : {flags if flags else 'None'}")
        
        print("\n[DECISION CONTRACT]")
        print(f"  AI Recommendation : {data.get('ai_recommendation')}")
        print(f"  Decision Status   : {data.get('decision_status')}")
        print(f"  Request Status    : {data.get('request_status')}")
        print(f"  Final Decision    : {data.get('final_decision')}")
        print(f"  Human Review Req  : {data.get('human_review_required')}")
        if data.get("rationale"):
            print(f"  Rationale Excerpt : {data.get('rationale')[:120]}...")
    else:
        print(f"Notice: No committed result found at outputs/sample_results/{app_id}.json")
        
    # 2. Review history
    print("\n[HUMAN REVIEW AUDIT TRAIL]")
    review_log = REPO_ROOT / "logs" / "human_reviews.jsonl"
    reviews_found = 0
    if review_log.exists():
        with open(review_log, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                if rec.get("application_id") == app_id or rec.get("application_id") == Path(app_id).stem:
                    reviews_found += 1
                    print(f"  [{rec.get('timestamp')}] Reviewer: {rec.get('reviewer_id')} -> {rec.get('final_decision') or rec.get('decision')} (Reason: {rec.get('review_reason')})")
    if reviews_found == 0:
        print("  No human review records logged for this application.")

    # 3. Traces summary
    print("\n[PHOENIX TRACE SPANS]")
    parquet_path = REPO_ROOT / "traces" / "phoenix_spans.parquet"
    if parquet_path.exists():
        try:
            df = pd.read_parquet(parquet_path)
            app_stem = Path(app_id).stem
            app_spans = df[df["application_id"] == app_stem] if "application_id" in df.columns else pd.DataFrame()
            if len(app_spans) > 0:
                print(f"  Total Spans for {app_stem}: {len(app_spans)}")
                for _, row in app_spans.head(5).iterrows():
                    name = row.get("name", "span")
                    kind = row.get("span_kind", "")
                    lat = row.get("latency_ms", 0.0)
                    print(f"    - {name:<25} [{kind:<8}] latency: {lat:.1f}ms")
            else:
                print(f"  Trace file present ({len(df)} total spans across all runs).")
        except Exception as e:
            print(f"  Trace read error: {e}")
    else:
        print("  traces/phoenix_spans.parquet not found.")
        
    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Show offline committed evidence for an application.")
    parser.add_argument("--application", "-a", type=str, required=True, help="Application ID (e.g. APP-001)")
    args = parser.parse_args()
    show_evidence(args.application)


if __name__ == "__main__":
    main()
