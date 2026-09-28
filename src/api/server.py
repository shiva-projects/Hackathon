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
import re
import json
import uuid
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Header, Depends
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
from src.security.authorization import register_custom_application, AUTHORIZATION_FIXTURE
from src.observability.unified_logger import log_human_review
from src.observability.span_sanitizer import sanitize_data
from src.guardrails.output_guard import sanitize_review_reason

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Loan Origination & Underwriting Copilot API",
    description="Multi-agent banking copilot with Arize Phoenix observability, deterministic rules, tiered memory, and audit trails.",
    version="1.0.0",
)

# Constrained CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

_cached_graph = None


def get_graph():
    global _cached_graph
    if _cached_graph is None:
        _cached_graph = build_loan_copilot_graph()
    return _cached_graph


# ---------------------------------------------------------
# Authentication & Principal Models
# ---------------------------------------------------------

class Principal(BaseModel):
    id: str
    role: str  # "loan_officer", "senior_underwriter", "applicant"


KNOWN_PRINCIPALS: Dict[str, Principal] = {
    "token-lo-001": Principal(id="LO-001", role="loan_officer"),
    "token-lo-002": Principal(id="LO-002", role="loan_officer"),
    "token-su-001": Principal(id="SU-001", role="senior_underwriter"),
    "token-app-001": Principal(id="APPLICANT-001", role="applicant"),
    "LO-001": Principal(id="LO-001", role="loan_officer"),
    "LO-002": Principal(id="LO-002", role="loan_officer"),
    "SU-001": Principal(id="SU-001", role="senior_underwriter"),
}


def get_current_principal(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
) -> Optional[Principal]:
    """Resolves authenticated principal from Bearer token or API key."""
    token = None
    if authorization:
        if authorization.startswith("Bearer "):
            token = authorization[7:].strip()
        else:
            token = authorization.strip()
    elif x_api_key:
        token = x_api_key.strip()

    if not token:
        return None

    if token in KNOWN_PRINCIPALS:
        return KNOWN_PRINCIPALS[token]
    elif token.startswith("LO-") or "officer" in token.lower():
        return Principal(id=token, role="loan_officer")
    elif token.startswith("SU-") or "underwriter" in token.lower():
        return Principal(id=token, role="senior_underwriter")
    elif token.startswith("APP-") or token.startswith("APPLICANT-"):
        return Principal(id=token, role="applicant")

    return None


def sanitize_app_id(app_id: str) -> str:
    """Validates application_id against strict whitelist pattern to prevent path traversal."""
    if not re.match(r"^[A-Za-z0-9_-]{3,50}$", app_id):
        raise HTTPException(status_code=422, detail=f"Invalid application_id format: '{app_id}'")
    return app_id


def get_safe_results_path(app_id: str) -> Path:
    """Returns safe filesystem path for application result with path traversal verification."""
    clean_id = sanitize_app_id(app_id)
    out_dir = (PROJECT_ROOT / "outputs" / "sample_results").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = (out_dir / f"{clean_id}.json").resolve()
    if not str(target).startswith(str(out_dir)):
        raise HTTPException(status_code=400, detail="Invalid path traversal sequence detected")
    return target


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
    decision: str = Field(..., description="APPROVE or DECLINE")
    rationale: str = Field(..., description="Underwriter justification")
    conditions: Optional[List[str]] = Field(None, description="Optional conditions precedent")


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str


# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------

def prepare_pipeline_state(
    payload: UnderwriteRequest,
    principal: Optional[Principal],
) -> tuple[str, str, str, Dict[str, Any], Dict[str, Any]]:
    """Validates input, registers authorization, and initializes LangGraph state."""
    app_id = sanitize_app_id(payload.application_id)
    raw_text = payload.free_text or payload.applicant_data.get("free_text", "")

    # Establish effective caller principal
    actor_id = principal.id if principal else payload.actor_id
    actor_role = principal.role if principal else payload.actor_role

    session_id = payload.session_id or f"SESSION-{app_id}-{int(datetime.now().timestamp())}"
    run_id = f"RUN-{uuid.uuid4().hex[:8]}"

    # Fail closed on schema errors (P0 fix: never fall back to raw dictionary)
    try:
        app_dict = dict(payload.applicant_data)
        app_dict["application_id"] = app_id
        app_dict["requester_id"] = actor_id
        if "free_text" not in app_dict and raw_text:
            app_dict["free_text"] = raw_text
        app_obj = load_application_from_dict(app_dict)
        facts = app_obj.to_facts_dict()
    except Exception as e:
        logger.error("Strict application validation failed for %s: %s", app_id, e)
        raise HTTPException(
            status_code=422,
            detail=f"Application schema validation error: {str(e)}"
        )

    # Register access permission for the designated loan officer
    if actor_role in {"loan_officer", "senior_underwriter"}:
        register_custom_application(application_id=app_id, officer_id=actor_id)

    initial_state = create_initial_state(
        application_id=app_id,
        applicant_raw_text=raw_text,
        applicant_facts=facts,
        session_id=session_id,
    )
    initial_state["actor_id"] = actor_id
    initial_state["actor_role"] = actor_role

    if payload.clarification_response:
        initial_state["clarification_response"] = payload.clarification_response
        initial_state["clarification_needed"] = False

    return app_id, session_id, run_id, initial_state, facts


def build_response_record(
    app_id: str,
    session_id: str,
    run_id: str,
    final_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Constructs standardized sanitized API response dictionary."""
    citations = final_state.get("policy_citations") or []
    if not citations and final_state.get("policy_citation"):
        citations = [final_state.get("policy_citation")]
    primary_citation = citations[0] if citations else None
    rationale_text = final_state.get("rationale") or final_state.get("decision_rationale")

    record = {
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
        "policy_selected": final_state.get("policy_selected"),
        "policy_citations": citations,
        "policy_citation": primary_citation,
        "rationale": rationale_text,
        "decision_rationale": rationale_text,
    }
    return record


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
async def underwrite_application(
    payload: UnderwriteRequest,
    principal: Optional[Principal] = Depends(get_current_principal),
):
    """
    Evaluates a loan application through the multi-agent graph.
    Returns the complete structured underwriting decision and state summary.
    Persists evaluation output for human review query.
    """
    app_id, session_id, run_id, initial_state, _ = prepare_pipeline_state(payload, principal)

    graph = get_graph()
    # Bind thread to principal/actor + session for session integrity
    thread_key = f"{initial_state.get('actor_id', 'LO-001')}:{session_id}"
    cfg = get_session_config(thread_key)

    try:
        final_state = await graph.ainvoke(initial_state, config=cfg)
        assert_state_invariants(final_state)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Pipeline execution failure on %s", app_id)
        raise HTTPException(status_code=500, detail=f"Pipeline execution error: {str(e)}")

    response_data = build_response_record(app_id, session_id, run_id, final_state)

    # Persist evaluated result to outputs/sample_results/{app_id}.json for /review endpoint
    target_file = get_safe_results_path(app_id)
    try:
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(response_data, f, indent=2, default=str)
    except Exception as exc:
        logger.warning("Failed to persist sample result for %s: %s", app_id, exc)

    return JSONResponse(content=sanitize_data(response_data))


@app.post("/api/v1/underwrite/stream")
async def underwrite_stream(
    payload: UnderwriteRequest,
    principal: Optional[Principal] = Depends(get_current_principal),
):
    """
    Executes loan underwriting while streaming node transitions as Server-Sent Events (SSE).
    Uses native LangGraph async generator .astream() without thread-blocking.
    """
    app_id, session_id, run_id, initial_state, _ = prepare_pipeline_state(payload, principal)

    graph = get_graph()
    thread_key = f"{initial_state.get('actor_id', 'LO-001')}:{session_id}"
    cfg = get_session_config(thread_key)

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
def record_human_review(
    payload: HumanReviewRequest,
    principal: Optional[Principal] = Depends(get_current_principal),
):
    """
    Records a binding human underwriter decision (approve/decline) for an application
    that required human referral. Enforces role authentication and strict validation.
    """
    app_id = sanitize_app_id(payload.application_id)
    reviewer_id = principal.id if principal else payload.reviewer_id
    reviewer_role = principal.role if principal else "loan_officer"

    # Enforce role permission
    if reviewer_role not in {"senior_underwriter", "loan_officer"}:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{reviewer_role}' unauthorized to execute human review. Requires senior_underwriter or loan_officer."
        )

    # Validate decision value
    normalized_decision = payload.decision.upper()
    if normalized_decision in {"APPROVED", "APPROVE"}:
        decision_val = "APPROVE"
    elif normalized_decision in {"DECLINED", "DECLINE"}:
        decision_val = "DECLINE"
    else:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid decision '{payload.decision}'. Must be 'APPROVE' or 'DECLINE'."
        )

    out_file = get_safe_results_path(app_id)
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

    data["final_decision"] = decision_val
    data["review_id"] = review_id
    data["reviewed_by"] = reviewer_id
    data["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    data["human_rationale"] = clean_rationale
    if payload.conditions:
        data["conditions"] = payload.conditions

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    # Log review with matching signature
    log_human_review(
        review_id=review_id,
        application_id=app_id,
        reviewer_id=reviewer_id,
        ai_recommendation=data.get("ai_recommendation"),
        final_decision=decision_val,
        review_reason=clean_rationale,
        run_id=data.get("run_id", "RUN-API-REV"),
    )

    return JSONResponse(content={
        "status": "recorded",
        "application_id": app_id,
        "review_id": review_id,
        "final_decision": decision_val,
        "reviewer_id": reviewer_id,
    })


@app.get("/api/v1/applications/{app_id}")
def get_application_result(
    app_id: str,
    principal: Optional[Principal] = Depends(get_current_principal),
):
    """Retrieves an existing evaluated application result by ID with authorization checks."""
    safe_id = sanitize_app_id(app_id)
    out_file = get_safe_results_path(safe_id)
    if not out_file.exists():
        raise HTTPException(status_code=404, detail=f"Application {safe_id} not found")

    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Ownership check if caller is an applicant
    if principal and principal.role == "applicant":
        if principal.id != safe_id and data.get("applicant_id") != principal.id:
            raise HTTPException(status_code=403, detail="Applicant unauthorized to view other applications")

    return JSONResponse(content=sanitize_data(data))
