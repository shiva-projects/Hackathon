"""
Comprehensive Fail-Closed Tests for Human Review Flow.
Per Phase 5 of antigravity_implementation_checklist.md:
- Rejects empty decision.
- Rejects empty reason / short reason (< 5 characters).
- Rejects invalid decision strings.
- Rejects unauthorized reviewers (both API and CLI) via shared authorization policy.
- Rejects human review for applications that do not require review.
- Handles user cancellation (Ctrl-C / EOF) leaving final decision unset.
- Supports canonical decisions: APPROVE, REFER, DECLINE.
- Verifies records are persisted to outputs/sample_results and logs/human_reviews.jsonl.
"""

import json
from pathlib import Path
import pytest
from unittest.mock import patch
from starlette.testclient import TestClient

from src.api.server import app
from src.domain.models import HumanDecision, HumanReviewSubmission
from src.security.authorization import register_custom_application
from scripts.run_pipeline import execute_human_review


@pytest.fixture
def client():
    yield TestClient(app)


@pytest.fixture
def review_fixture_apps(tmp_path):
    """Sets up sample results files for testing human reviews, preserving authentic evidence on teardown."""
    res_dir = Path("outputs/sample_results")
    res_dir.mkdir(parents=True, exist_ok=True)

    app4_file = res_dir / "APP-004.json"
    app1_file = res_dir / "APP-001.json"

    app4_backup = app4_file.read_bytes() if app4_file.exists() else None
    app1_backup = app1_file.read_bytes() if app1_file.exists() else None

    try:
        # 1. APP-004 requires human review (LO-001 is authorized)
        app4_data = {
            "application_id": "APP-004",
            "session_id": "SESSION-APP-004-TEST",
            "run_id": "RUN-TEST-004",
            "request_status": "COMPLETED",
            "decision_status": "DETERMINED",
            "ai_recommendation": "REFER",
            "human_review_required": True,
            "final_decision": None,
            "review_id": None,
            "rationale": "High value loan requires underwriter confirmation.",
        }
        with open(app4_file, "w", encoding="utf-8") as f:
            json.dump(app4_data, f, indent=2)

        # 2. APP-001 does NOT require human review (ai_recommendation = APPROVE)
        app1_data = {
            "application_id": "APP-001",
            "session_id": "SESSION-APP-001-TEST",
            "run_id": "RUN-TEST-001",
            "request_status": "COMPLETED",
            "decision_status": "DETERMINED",
            "ai_recommendation": "APPROVE",
            "human_review_required": False,
            "final_decision": None,
            "review_id": None,
            "rationale": "All rules passed.",
        }
        with open(app1_file, "w", encoding="utf-8") as f:
            json.dump(app1_data, f, indent=2)

        yield {"app_requires_review": "APP-004", "app_no_review": "APP-001"}
    finally:
        if app4_backup is not None:
            app4_file.write_bytes(app4_backup)
        if app1_backup is not None:
            app1_file.write_bytes(app1_backup)


def test_api_rejects_missing_or_empty_decision(client, review_fixture_apps):
    payload = {
        "application_id": "APP-004",
        "reviewer_id": "LO-001",
        "decision": "",
        "review_reason": "Valid reason exceeding minimum length",
    }
    response = client.post("/api/v1/review", json=payload)
    assert response.status_code == 422


def test_api_rejects_invalid_decision_string(client, review_fixture_apps):
    payload = {
        "application_id": "APP-004",
        "reviewer_id": "LO-001",
        "decision": "MAYBE",
        "review_reason": "Valid reason exceeding minimum length",
    }
    response = client.post("/api/v1/review", json=payload)
    assert response.status_code == 422


def test_api_rejects_empty_or_short_reason(client, review_fixture_apps):
    payload = {
        "application_id": "APP-004",
        "reviewer_id": "LO-001",
        "decision": "APPROVE",
        "review_reason": "ok",
    }
    response = client.post("/api/v1/review", json=payload)
    assert response.status_code == 422


def test_api_rejects_unauthorized_reviewer(client, review_fixture_apps):
    # LO-002 is NOT authorized for APP-004 per AUTHORIZATION_FIXTURE
    payload = {
        "application_id": "APP-004",
        "reviewer_id": "LO-002",
        "decision": "APPROVE",
        "review_reason": "Reviewer is unauthorized to review this application.",
    }
    response = client.post("/api/v1/review", json=payload)
    assert response.status_code == 403
    assert "unauthorized" in response.text.lower()


def test_api_rejects_review_when_not_required(client, review_fixture_apps):
    # APP-001 human_review_required is False
    payload = {
        "application_id": "APP-001",
        "reviewer_id": "LO-001",
        "decision": "DECLINE",
        "review_reason": "Overriding when human review is not required.",
    }
    response = client.post("/api/v1/review", json=payload)
    assert response.status_code == 400
    assert "does not require human review" in response.text.lower()


def test_api_supports_approve_refer_decline(client, review_fixture_apps):
    # Test all three canonical decisions via API
    for decision in ["APPROVE", "REFER", "DECLINE"]:
        payload = {
            "application_id": "APP-004",
            "reviewer_id": "LO-001",
            "decision": decision,
            "review_reason": f"Underwriter verified conditions for {decision}.",
        }
        response = client.post("/api/v1/review", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "recorded"
        assert data["final_decision"] == decision
        assert data["application_id"] == "APP-004"


def test_cli_rejects_unauthorized_reviewer(review_fixture_apps):
    app_file = "data/sample_applications/APP-004.json"
    # LO-002 is unauthorized for APP-004
    with pytest.raises(PermissionError) as exc_info:
        execute_human_review(
            app_file=app_file,
            reviewer_id="LO-002",
            interactive=False,
            override_decision="APPROVE",
            review_reason="Attempting unauthorized approval.",
        )
    assert "NOT authorized" in str(exc_info.value)


def test_cli_rejects_empty_or_invalid_decision(review_fixture_apps):
    app_file = "data/sample_applications/APP-004.json"
    with pytest.raises(ValueError):
        execute_human_review(
            app_file=app_file,
            reviewer_id="LO-001",
            interactive=False,
            override_decision="",
            review_reason="Valid underwriter reason.",
        )

    with pytest.raises(ValueError):
        execute_human_review(
            app_file=app_file,
            reviewer_id="LO-001",
            interactive=False,
            override_decision="INVALID_CHOICE",
            review_reason="Valid underwriter reason.",
        )


def test_cli_rejects_empty_reason(review_fixture_apps):
    app_file = "data/sample_applications/APP-004.json"
    with pytest.raises(ValueError):
        execute_human_review(
            app_file=app_file,
            reviewer_id="LO-001",
            interactive=False,
            override_decision="APPROVE",
            review_reason="",
        )


def test_cli_ctrl_c_leaves_final_decision_unset(review_fixture_apps):
    app_file = "data/sample_applications/APP-004.json"
    res_path = Path("outputs/sample_results/APP-004.json")

    # Read original state before interrupt
    with open(res_path, "r", encoding="utf-8") as f:
        orig_data = json.load(f)
    assert orig_data.get("final_decision") is None

    # Simulate KeyboardInterrupt on input
    with patch("builtins.input", side_effect=KeyboardInterrupt):
        result = execute_human_review(
            app_file=app_file,
            reviewer_id="LO-001",
            interactive=True,
            override_decision=None,
            review_reason=None,
        )

    assert result["status"] == "CANCELLED"
    assert result["final_decision"] is None

    # Verify file remains unset
    with open(res_path, "r", encoding="utf-8") as f:
        current_data = json.load(f)
    assert current_data.get("final_decision") is None


def test_cli_valid_decision_persists_to_file_and_logs(review_fixture_apps):
    app_file = "data/sample_applications/APP-004.json"
    res_path = Path("outputs/sample_results/APP-004.json")
    logs_file = Path("logs/human_reviews.jsonl")

    res = execute_human_review(
        app_file=app_file,
        reviewer_id="LO-001",
        interactive=False,
        override_decision="DECLINE",
        review_reason="Collateral valuation insufficient after manual appraisal.",
    )

    assert res["final_decision"] == "DECLINE"
    assert res["review_id"].startswith("REV-APP-004")

    # Check persistence in sample_results
    with open(res_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["final_decision"] == "DECLINE"
    assert data["review_id"] == res["review_id"]
    assert data["reviewed_by"] == "LO-001"
    assert "Collateral valuation insufficient" in data["human_rationale"]

    # Check persistence in logs/human_reviews.jsonl
    assert logs_file.exists()
    with open(logs_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    last_line = json.loads(lines[-1].strip())
    assert last_line["review_id"] == res["review_id"]
    assert last_line["application_id"] == "APP-004"
    assert last_line["final_decision"] == "DECLINE"
    assert last_line["reviewer_id"] == "LO-001"
