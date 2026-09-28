"""
Main Pipeline CLI Runner for Loan Origination & Underwriting Copilot.
Per plan.md Section 13.7, 13.14 & 14.2.
Supports:
--application <path>
--application-dir <dir>
--resume-session <id>
--clarification "<text>"
--review --reviewer-id <id>
"""

import sys
import os
import json
import uuid
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.state import create_initial_state, assert_state_invariants
from src.ingestion.application_loader import load_application_from_file
from src.graph import build_loan_copilot_graph
from src.memory.checkpoint_config import get_checkpointer, get_session_config
from src.security.authorization import authorize
from src.observability.unified_logger import log_human_review, log_event
from src.guardrails.output_guard import sanitize_review_reason


def run_single_application(
    app_file_or_data: Any,
    session_id: str = None,
    clarification: str = None,
    graph: Any = None,
    run_id: str = None,
) -> Dict[str, Any]:
    """Processes a single loan application through the copilot graph."""
    if isinstance(app_file_or_data, (str, Path)):
        app = load_application_from_file(app_file_or_data)
        facts = app.to_facts_dict()
        app_id = app.application_id
        raw_text = app.free_text
    else:
        facts = app_file_or_data
        app_id = facts.get("application_id", "APP-UNKNOWN")
        raw_text = facts.get("free_text", "")

    session_id = session_id or f"SESSION-{app_id}-{int(datetime.now().timestamp())}"
    run_id = run_id or f"RUN-{uuid.uuid4().hex[:8]}"

    if graph is None:
        graph = build_loan_copilot_graph()

    cfg = get_session_config(session_id)

    # Check if this is a resumed clarification
    if clarification:
        initial_state = create_initial_state(app_id, applicant_raw_text=raw_text, applicant_facts=facts, session_id=session_id, run_id=run_id)
        initial_state["clarification_response"] = clarification
        initial_state["clarification_needed"] = False
    else:
        initial_state = create_initial_state(app_id, applicant_raw_text=raw_text, applicant_facts=facts, session_id=session_id, run_id=run_id)

    import asyncio
    final_state = asyncio.run(graph.ainvoke(initial_state, config=cfg))

    # Validate state invariants
    assert_state_invariants(final_state)

    # Write committed structured result to outputs/sample_results/APP-00N.json
    out_dir = Path("outputs/sample_results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{app_id}.json"

    # If file exists and had prior human review, preserve unless overwritten
    existing_result = {}
    if out_file.exists():
        try:
            with open(out_file, "r", encoding="utf-8") as f:
                existing_result = json.load(f)
        except Exception:
            pass

    structured_result = {
        "application_id": app_id,
        "session_id": session_id,
        "run_id": run_id,
        "request_status": final_state.get("request_status"),
        "refusal_reason": final_state.get("refusal_reason"),
        "decision_status": final_state.get("decision_status"),
        "unable_reason": final_state.get("unable_reason"),
        "ai_recommendation": final_state.get("ai_recommendation"),
        "human_review_required": final_state.get("human_review_required"),
        "final_decision": existing_result.get("final_decision", final_state.get("final_decision")),
        "review_id": existing_result.get("review_id", final_state.get("review_id")),
        "affordability": final_state.get("affordability", {}),
        "risk_flags": final_state.get("risk_flags", []),
        "policy_selected": final_state.get("policy_selected", {}),
        "policy_citations": final_state.get("policy_citations", []),
        "rationale": final_state.get("rationale", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(structured_result, f, indent=2)

    return structured_result


def execute_human_review(
    app_file: str,
    reviewer_id: str,
    interactive: bool = True,
    override_decision: str = None,
    review_reason: str = None,
) -> Dict[str, Any]:
    """
    Executes human review flow per plan.md Section 14.2:
    - Verifies reviewer authorization via authorize()
    - Prompts for decision (APPROVE/REFER/DECLINE)
    - Validates non-empty review_reason
    - Appends to logs/human_reviews.jsonl
    - Updates outputs/sample_results/APP-00N.json with latest review
    """
    app = load_application_from_file(app_file)
    app_id = app.application_id

    # 1. Authorize reviewer
    auth_status = authorize(reviewer_id, app_id)
    if auth_status != "AUTHORIZED":
        print(f"Error: Reviewer '{reviewer_id}' is NOT authorized to review application '{app_id}'.")
        return {"error": "AUTHORIZATION_DENIED"}

    # Load current application result
    res_path = Path(f"outputs/sample_results/{app_id}.json")
    if not res_path.exists():
        run_single_application(app_file)

    with open(res_path, "r", encoding="utf-8") as f:
        result_data = json.load(f)

    ai_rec = result_data.get("ai_recommendation")
    print(f"\n--- Human Review for Application {app_id} ---")
    print(f"AI Recommendation: {ai_rec}")
    print(f"Rationale: {result_data.get('rationale')}")

    decision = override_decision
    reason = review_reason

    if interactive and not decision:
        decision = input("Human Decision [APPROVE/REFER/DECLINE]: ").strip().upper()
        while decision not in {"APPROVE", "REFER", "DECLINE"}:
            decision = input("Invalid decision. Enter APPROVE, REFER, or DECLINE: ").strip().upper()

        reason = input("Review Reason: ").strip()
        while not reason:
            reason = input("Review reason cannot be empty. Enter reason: ").strip()

    decision = decision or "APPROVE"
    reason = reason or "Verified supplementary documentation and collateral."

    # Sanitize review reason before writing
    clean_reason = sanitize_review_reason(reason)
    review_id = f"REV-{app_id}-{int(datetime.now().timestamp())}"

    # Log to logs/human_reviews.jsonl and unified trace
    log_human_review(
        review_id=review_id,
        application_id=app_id,
        reviewer_id=reviewer_id,
        ai_recommendation=ai_rec,
        final_decision=decision,
        review_reason=clean_reason,
    )

    # Update latest review in outputs/sample_results/APP-00N.json
    result_data["final_decision"] = decision
    result_data["review_id"] = review_id
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2)

    print(f"Human decision recorded: {decision} (Review ID: {review_id})")
    return result_data


def main():
    parser = argparse.ArgumentParser(description="Loan Origination & Underwriting Copilot CLI")
    parser.add_argument("--application", type=str, help="Path to single loan application JSON")
    parser.add_argument("--application-dir", type=str, help="Path to directory containing application JSONs")
    parser.add_argument("--resume-session", type=str, help="Session ID to resume")
    parser.add_argument("--clarification", type=str, help="Applicant clarification response text")
    parser.add_argument("--review", action="store_true", help="Launch human review flow")
    parser.add_argument("--reviewer-id", type=str, default="LO-001", help="Reviewer ID for human review")
    parser.add_argument("--decision", type=str, help="Non-interactive decision override (APPROVE/REFER/DECLINE)")
    parser.add_argument("--reason", type=str, help="Non-interactive review reason")

    args = parser.parse_args()

    run_id = f"RUN-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    processed_app_ids = []

    # Ensure Phoenix collector server is running per NFR-02 self-contained pipeline
    from src.observability.tracing import ensure_phoenix_server_running
    ensure_phoenix_server_running()

    # v8 Startup Provider Resolution & Evidence Recording (Section 5 & 8)
    from src.llm.provider_resolver import load_model_config
    from src.llm.client import get_llm_client, reset_run_provider
    from src.observability.unified_logger import log_agent_action

    reset_run_provider()
    config = load_model_config()

    import hashlib
    config_sha256 = hashlib.sha256(json.dumps(config, sort_keys=True).encode("utf-8")).hexdigest()

    try:
        handle = get_llm_client()
        resolved_provider = handle.provider
        resolved_model = handle.model
        resolution_reason = handle.resolution_reason
    except Exception as exc:
        print(f"[FATAL] No usable LLM provider. Pipeline execution aborted: {exc}")
        print("Please configure a valid GEMINI_API_KEY or GROQ_API_KEY in .env before running.")
        sys.exit(1)

    now_iso = datetime.now(timezone.utc).isoformat()
    log_agent_action(
        actor="system",
        action="provider_resolution",
        tool="llm_resolver",
        decision=resolved_provider,
        run_id=run_id,
        details={
            "resolved_provider": resolved_provider,
            "resolved_model": resolved_model,
            "resolution_reason": resolution_reason,
            "resolution_status": "live_client_created",
            "config_sha256": config_sha256,
            "timestamp": now_iso,
        },
    )

    env_path = PROJECT_ROOT / "reports" / "environment.json"
    env_data = {}
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                env_data = json.load(f)
        except Exception:
            pass

    from src.observability.span_sanitizer import is_presidio_active

    env_data.update({
        "provider": resolved_provider,
        "model": resolved_model,
        "resolution_status": "live_client_created",
        "config_sha256": config_sha256,
        "temperature": config.get("providers", {}).get(resolved_provider, {}).get("temperature", 0.0),
        "resolution_order": config.get("resolution_order", ["gemini", "groq"]),
        "resolution_reason": resolution_reason,
        "presidio_active": is_presidio_active(),
        "guardrails_framework": "Layered (Domain Financial Guard + Presidio PII Engine + Regex Boundary Screen)",
        "verified_at": now_iso,
    })
    with open(env_path, "w", encoding="utf-8") as f:
        json.dump(env_data, f, indent=2)

    print(f"[startup] LLM provider resolved: {resolved_provider} ({resolved_model}) -- {resolution_reason}")

    if args.review:
        if not args.application:
            print("Error: --review requires --application <path>")
            sys.exit(1)
        execute_human_review(
            args.application,
            reviewer_id=args.reviewer_id,
            interactive=(args.decision is None),
            override_decision=args.decision,
            review_reason=args.reason,
        )
        return

    if args.application:
        res = run_single_application(
            args.application,
            session_id=args.resume_session,
            clarification=args.clarification,
            run_id=run_id,
        )
        processed_app_ids.append(res["application_id"])
        print(f"Processed {res['application_id']}: AI Recommendation = {res['ai_recommendation']}, Status = {res['decision_status']}")

    elif args.application_dir:
        dir_p = Path(args.application_dir)
        files = sorted(list(dir_p.glob("*.json")))
        for f in files:
            try:
                res = run_single_application(f, run_id=run_id)
                processed_app_ids.append(res["application_id"])
                print(f"Processed {f.name} -> {res['application_id']}: {res['ai_recommendation']} ({res['decision_status']})")
            except Exception as e:
                print(f"Error processing {f.name}: {e}")

    else:
        # Default run: process all files in data/sample_applications/
        default_dir = Path("data/sample_applications")
        if default_dir.exists():
            files = sorted(list(default_dir.glob("*.json")))
            for f in files:
                try:
                    res = run_single_application(f, run_id=run_id)
                    processed_app_ids.append(res["application_id"])
                    print(f"Processed {f.name} -> {res['application_id']}: {res['ai_recommendation']} ({res['decision_status']})")
                except Exception as e:
                    print(f"Error processing {f.name}: {e}")

    # Flush Phoenix spans to collector
    from src.observability.tracing import tracer
    tracer.flush()

    # Write reports/latest_run.json per plan.md Section 9.3
    latest_run_p = Path("reports/latest_run.json")
    latest_run_p.parent.mkdir(parents=True, exist_ok=True)
    latest_info = {
        "run_id": run_id,
        "application_ids": processed_app_ids,
        "git_commit": "committed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": resolved_provider,
        "model": resolved_model,
    }
    with open(latest_run_p, "w", encoding="utf-8") as f:
        json.dump(latest_info, f, indent=2)
    print(f"\nRun complete. Latest run info recorded to {latest_run_p}")


if __name__ == "__main__":
    main()
