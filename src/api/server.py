"""
FastAPI HTTP & Streaming Server for Loan Origination & Underwriting Copilot.
Per Section 7.7 and 8.1 of qn.txt (Extra Credit Bonus).
Provides:
  - GET  /health -> Service health and version status
  - POST /api/v1/underwrite -> Synchronous underwriting decision evaluation
  - POST /api/v1/underwrite/stream -> SSE streaming events showing agent nodes as they execute
  - POST /api/v1/review -> Human-in-the-loop review recording
  - GET  /api/v1/applications/{app_id} -> Query underwriting outputs
"""

import sys
import json
import uuid
import asyncio
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.state import create_initial_state, assert_state_invariants
from src.ingestion.application_loader import load_application_from_dict
from src.graph import build_loan_copilot_graph
from src.memory.checkpoint_config import get_session_config
from src.observability.unified_logger import log_human_review, log_event
from src.observability.span_sanitizer import sanitize_data
from src.guardrails.output_guard import sanitize_review_reason


app = FastAPI(
    title="Loan Origination & Underwriting Copilot API",
    description="Multi-agent banking copilot with Arize Phoenix observability, deterministic rules, tiered memory, and audit trails.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Reusable graph instance
_cached_graph = None


def get_graph():
    global _cached_graph
    if _cached_graph is None:
        _cached_graph = build_loan_copilot_graph()
    return _cached_graph


# ---------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------

class UnderwriteRequest(BaseModel):
    application_id: str = Field(..., description="Unique application ID (e.g., APP-001)")
    applicant_data: Dict[str, Any] = Field(..., description="Application attributes and financial details")
    free_text: Optional[str] = Field(None, description="Untrusted free-text applicant note")
    actor_id: str = Field("LO-001", description="Identifier of calling actor")
    actor_role: str = Field("loan_officer", description="Role: loan_officer, senior_underwriter, applicant")
    session_id: Optional[str] = Field(None, description="Optional conversation/session ID")
    clarification_response: Optional[str] = Field(None, description="Clarification text if resuming")


class HumanReviewRequest(BaseModel):
    application_id: str = Field(..., description="Target application ID")
    reviewer_id: str = Field(..., description="Reviewer employee ID")
    decision: str = Field(..., description="APPROVED or DECLINED")
    rationale: str = Field(..., description="Underwriter justification")
    conditions: Optional[List[str]] = Field(None, description="Optional conditions precedent")


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str


# ---------------------------------------------------------
# Endpoints
# ---------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
def health():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        service="loan-origination-copilot",
        version="1.0.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/api/v1/underwrite")
async def underwrite_application(payload: UnderwriteRequest):
    """
    Evaluates a loan application through the multi-agent graph.
    Returns the complete structured underwriting decision and state summary.
    """
    app_id = payload.application_id
    raw_text = payload.free_text or payload.applicant_data.get("free_text", "")
    session_id = payload.session_id or f"SESSION-{app_id}-{int(datetime.now().timestamp())}"
    run_id = f"RUN-{uuid.uuid4().hex[:8]}"

    try:
        app_dict = dict(payload.applicant_data)
        app_dict["application_id"] = app_id
        app_dict["requester_id"] = payload.actor_id
        if "free_text" not in app_dict and raw_text:
            app_dict["free_text"] = raw_text
        app_obj = load_application_from_dict(app_dict)
        facts = app_obj.to_facts_dict()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Could not parse strict application schema ({e}), using raw applicant data")
        facts = dict(payload.applicant_data)
        facts["application_id"] = app_id
        facts["requester_id"] = payload.actor_id

    initial_state = create_initial_state(
        application_id=app_id,
        applicant_raw_text=raw_text,
        applicant_facts=facts,
        session_id=session_id,
    )
    initial_state["actor_id"] = payload.actor_id
    initial_state["actor_role"] = payload.actor_role

    if payload.clarification_response:
        initial_state["clarification_response"] = payload.clarification_response
        initial_state["clarification_needed"] = False

    graph = get_graph()
    cfg = get_session_config(session_id)

    try:
        final_state = await graph.ainvoke(initial_state, config=cfg)
        assert_state_invariants(final_state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline execution error: {str(e)}")

    response_data = {
        "application_id": app_id,
        "session_id": session_id,
        "run_id": run_id,
        "request_status": final_state.get("request_status"),
        "refusal_reason": final_state.get("refusal_reason"),
        "decision_status": final_state.get("decision_status"),
        "unable_reason": final_state.get("unable_reason"),
        "ai_recommendation": final_state.get("ai_recommendation"),
        "human_review_required": final_state.get("human_review_required"),
        "final_decision": final_state.get("final_decision"),
        "review_id": final_state.get("review_id"),
        "affordability": final_state.get("affordability", {}),
        "rule_evaluations": final_state.get("rule_evaluations", []),
        "risk_flags": final_state.get("risk_flags", []),
        "policy_citation": final_state.get("policy_citation"),
        "decision_rationale": final_state.get("decision_rationale"),
    }

    # Sanitize any accidental PII before returning
    return JSONResponse(content=sanitize_data(response_data))


@app.post("/api/v1/underwrite/stream")
async def underwrite_stream(payload: UnderwriteRequest):
    """
    Executes loan underwriting while streaming node transitions as Server-Sent Events (SSE).
    Uses native LangGraph async generator .astream() without thread-blocking.
    """
    app_id = payload.application_id
    raw_text = payload.free_text or payload.applicant_data.get("free_text", "")
    session_id = payload.session_id or f"SESSION-{app_id}-{int(datetime.now().timestamp())}"
    run_id = f"RUN-{uuid.uuid4().hex[:8]}"

    try:
        app_dict = dict(payload.applicant_data)
        app_dict["application_id"] = app_id
        app_dict["requester_id"] = payload.actor_id
        if "free_text" not in app_dict and raw_text:
            app_dict["free_text"] = raw_text
        app_obj = load_application_from_dict(app_dict)
        facts = app_obj.to_facts_dict()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Could not parse strict application schema ({e}), using raw applicant data")
        facts = dict(payload.applicant_data)
        facts["application_id"] = app_id
        facts["requester_id"] = payload.actor_id

    initial_state = create_initial_state(
        application_id=app_id,
        applicant_raw_text=raw_text,
        applicant_facts=facts,
        session_id=session_id,
    )
    initial_state["actor_id"] = payload.actor_id
    initial_state["actor_role"] = payload.actor_role

    if payload.clarification_response:
        initial_state["clarification_response"] = payload.clarification_response
        initial_state["clarification_needed"] = False

    graph = get_graph()
    cfg = get_session_config(session_id)

    async def sse_generator():
        yield f"event: connect\ndata: {json.dumps({'status': 'connected', 'application_id': app_id, 'session_id': session_id})}\n\n"
        try:
            async for node_dict in graph.astream(initial_state, config=cfg, stream_mode="updates"):
                for node_name, node_update in node_dict.items():
                    event_data = {
                        "event": "node_update",
                        "node": node_name,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "state_keys": list(node_update.keys()),
                    }
                    if "ai_recommendation" in node_update:
                        event_data["ai_recommendation"] = node_update["ai_recommendation"]
                    if "decision_status" in node_update:
                        event_data["decision_status"] = node_update["decision_status"]
                    if "request_status" in node_update:
                        event_data["request_status"] = node_update["request_status"]

                    yield f"event: node_update\ndata: {json.dumps(sanitize_data(event_data))}\n\n"

            yield f"event: stream_end\ndata: {json.dumps({'event': 'stream_end'})}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'event': 'error', 'error': str(exc)})}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")


@app.post("/api/v1/review")
def record_human_review(payload: HumanReviewRequest):
    """
    Records a binding human underwriter decision (approve/decline) for an application
    that required human referral.
    """
    app_id = payload.application_id
    out_dir = Path("outputs/sample_results")
    out_file = out_dir / f"{app_id}.json"

    if not out_file.exists():
        raise HTTPException(status_code=404, detail=f"Application result for {app_id} not found.")

    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not data.get("human_review_required"):
        raise HTTPException(
            status_code=400,
            detail=f"Application {app_id} does not require human review (ai_recommendation={data.get('ai_recommendation')})"
        )

    clean_rationale = sanitize_review_reason(payload.rationale)
    review_id = f"REV-{app_id}-{int(datetime.now().timestamp())}"
    decision_val = payload.decision.upper()

    data["final_decision"] = decision_val
    data["review_id"] = review_id
    data["reviewed_by"] = payload.reviewer_id
    data["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    data["human_rationale"] = clean_rationale
    if payload.conditions:
        data["conditions"] = payload.conditions

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    log_human_review(
        application_id=app_id,
        reviewer_id=payload.reviewer_id,
        decision=decision_val,
        reason=clean_rationale,
        review_id=review_id,
        run_id=data.get("run_id", "RUN-API-REV"),
        conditions=payload.conditions,
    )

    return JSONResponse(content={
        "status": "recorded",
        "application_id": app_id,
        "review_id": review_id,
        "final_decision": decision_val,
    })


@app.get("/api/v1/applications/{app_id}")
def get_application_result(app_id: str):
    """Retrieves an existing evaluated application result by ID."""
    out_file = Path("outputs/sample_results") / f"{app_id}.json"
    if not out_file.exists():
        raise HTTPException(status_code=404, detail=f"Application {app_id} not found")

    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return JSONResponse(content=sanitize_data(data))
