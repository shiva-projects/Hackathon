"""
Authorization Layer for Loan Origination & Underwriting Copilot.
Enforces access control boundaries right after input guardrails.
Per plan.md Section 14.1 & Non-Negotiable Rule 7.
"""

from typing import Literal, Dict, Set, Optional
from src.observability.unified_logger import log_agent_action

# Static authorization mapping fixture per plan.md Section 14.1
# Loan Officers have broader application access; Applicants have strictly self-access
AUTHORIZATION_FIXTURE: Dict[str, Set[str]] = {
    "LO-001": {
        "APP-001", "APP-004", "APP-011", "APP-VERSION-DIFF", "APP-STRESS-01",
        "APP-AMB-01", "APP-OUT-01", "APP-INJ-01", "APP-CROSS-01",
        "GOLD-01", "GOLD-04", "GOLD-05", "GOLD-06", "GOLD-07", "GOLD-08",
        "GOLD-09", "GOLD-10", "GOLD-11", "GOLD-12", "GOLD-13", "GOLD-14",
        "GOLD-15", "GOLD-16", "GOLD-17", "GOLD-18", "GOLD-19", "GOLD-20",
    },
    "LO-002": {"APP-002", "APP-003", "GOLD-02", "GOLD-03"},
    "APPLICANT-001": {"APP-001"},
    "APPLICANT-002": {"APP-002"},
    "APPLICANT-003": {"APP-003"},
    "APPLICANT-004": {"APP-004"},
}


def register_custom_application(application_id: str, officer_id: str = "LO-001", applicant_id: str = None) -> None:
    """Registers a dynamically created custom application to grant officer and self access."""
    if officer_id in AUTHORIZATION_FIXTURE:
        AUTHORIZATION_FIXTURE[officer_id].add(application_id)
    else:
        AUTHORIZATION_FIXTURE[officer_id] = {application_id}
    if applicant_id:
        AUTHORIZATION_FIXTURE.setdefault(applicant_id, set()).add(application_id)


from src.context.execution_context import resolve_run_id


def authorize(
    requester_id: str,
    application_id: str,
    run_id: Optional[str] = None,
) -> Literal["AUTHORIZED", "DENIED"]:
    """
    Checks if requester_id is permitted to access application_id.
    Strictly data-driven with no wildcard prefix bypasses.
    Logs access decisions to logs/agent_actions.jsonl.
    """
    resolved_run_id = resolve_run_id(run_id, required=False)
    allowed_apps = AUTHORIZATION_FIXTURE.get(requester_id, set())
    is_allowed = application_id in allowed_apps

    if is_allowed:
        log_agent_action(
            actor=requester_id,
            action="authorization_check",
            tool=None,
            decision="AUTHORIZED",
            run_id=resolved_run_id,
            application_id=application_id,
            details={"status": "ACCESS_GRANTED"},
        )
        return "AUTHORIZED"
    else:
        log_agent_action(
            actor=requester_id,
            action="authorization_check",
            tool=None,
            decision="DENIED",
            run_id=resolved_run_id,
            application_id=application_id,
            details={"status": "ACCESS_DENIED", "reason": "AUTHORIZATION_DENIED"},
        )
        return "DENIED"
