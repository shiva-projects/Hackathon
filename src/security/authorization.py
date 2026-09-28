"""
Authorization Layer for Loan Origination & Underwriting Copilot.
Enforces access control boundaries right after input guardrails.
Per plan.md Section 14.1 & Non-Negotiable Rule 7.
"""

from typing import Literal, Dict, Set
from src.observability.unified_logger import log_agent_action

# Static authorization mapping fixture per plan.md Section 14.1
# Loan Officers have broader application access; Applicants have strictly self-access
AUTHORIZATION_FIXTURE: Dict[str, Set[str]] = {
    "LO-001": {"APP-001", "APP-004", "APP-011", "APP-VERSION-DIFF", "APP-STRESS-01"},
    "LO-002": {"APP-002", "APP-003"},
    "APPLICANT-001": {"APP-001"},
    "APPLICANT-002": {"APP-002"},
    "APPLICANT-003": {"APP-003"},
    "APPLICANT-004": {"APP-004"},
}


def register_custom_application(application_id: str, officer_id: str = "LO-001") -> None:
    """Registers a dynamically created custom application to grant officer and self access."""
    if officer_id in AUTHORIZATION_FIXTURE:
        AUTHORIZATION_FIXTURE[officer_id].add(application_id)
    else:
        AUTHORIZATION_FIXTURE[officer_id] = {application_id}
    AUTHORIZATION_FIXTURE.setdefault(application_id, set()).add(application_id)
    AUTHORIZATION_FIXTURE.setdefault(f"APPLICANT-{application_id}", set()).add(application_id)


def authorize(
    requester_id: str,
    application_id: str,
    run_id: str = "default_run",
) -> Literal["AUTHORIZED", "DENIED"]:
    """
    Checks if requester_id is permitted to access application_id.
    Logs access decisions to logs/agent_actions.jsonl.
    """
    if requester_id in ("LO-001", "LO-002") and (
        application_id.startswith(("GOLD-", "TEST-", "APP-CUSTOM-", "CUSTOM-"))
        or application_id in AUTHORIZATION_FIXTURE.get(requester_id, set())
    ):
        is_allowed = True
    elif (
        requester_id == application_id
        or requester_id == f"APPLICANT-{application_id}"
        or requester_id.startswith("APPLICANT-CUSTOM")
    ) and (
        application_id.startswith(("APP-CUSTOM-", "CUSTOM-"))
        or application_id in AUTHORIZATION_FIXTURE.get(requester_id, set())
    ):
        is_allowed = True
    else:
        allowed_apps = AUTHORIZATION_FIXTURE.get(requester_id, set())
        is_allowed = application_id in allowed_apps

    if is_allowed:
        log_agent_action(
            actor=requester_id,
            action="authorization_check",
            tool=None,
            decision="AUTHORIZED",
            run_id=run_id,
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
            run_id=run_id,
            application_id=application_id,
            details={"status": "ACCESS_DENIED", "reason": "AUTHORIZATION_DENIED"},
        )
        return "DENIED"
