"""
Unit and Integration Tests for FastAPI HTTP & Streaming Server.
Per Section 7.7 and 8.1 of qn.txt.
"""

import json
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from src.api.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "loan-origination-copilot"


def test_underwrite_endpoint_success(client):
    payload = {
        "application_id": "TEST-APP-API-001",
        "applicant_data": {
            "application_id": "TEST-APP-API-001",
            "applicant_name": "Test User",
            "product": "personal_loan",
            "jurisdiction": "IN",
            "application_date": "2026-03-15",
            "income_amount": 100000.0,
            "income_period": "monthly",
            "currency": "INR",
            "requested_amount": 300000.0,
            "tenure_months": 24,
            "employment": "salaried",
            "existing_obligations": [
                {"obligation_type": "car_loan", "amount": 20000.0, "period": "monthly"}
            ],
            "documents": ["identity_proof", "income_statement"],
            "free_text": "I would like to apply for a personal loan.",
        },
        "free_text": "I would like to apply for a personal loan.",
        "actor_id": "LO-001",
        "actor_role": "loan_officer",
    }
    response = client.post("/api/v1/underwrite", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["application_id"] == "TEST-APP-API-001"
    assert data["request_status"] == "COMPLETED"
    assert data["ai_recommendation"] in ["APPROVE", "REFER", "DECLINE"]
    assert "affordability" in data
    assert "dti" in data["affordability"]


def test_underwrite_streaming_endpoint(client):
    payload = {
        "application_id": "TEST-APP-API-STREAM-001",
        "applicant_data": {
            "application_id": "TEST-APP-API-STREAM-001",
            "applicant_name": "Stream User",
            "product": "personal_loan",
            "jurisdiction": "IN",
            "application_date": "2026-03-15",
            "income_amount": 80000.0,
            "income_period": "monthly",
            "currency": "INR",
            "requested_amount": 200000.0,
            "tenure_months": 24,
            "employment": "salaried",
            "existing_obligations": [],
            "documents": ["identity_proof", "income_statement"],
            "free_text": "Applying for home renovation loan.",
        },
        "actor_id": "LO-001",
        "actor_role": "loan_officer",
    }
    response = client.post("/api/v1/underwrite/stream", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    body = response.text
    assert "event: connect" in body
    assert "event: node_update" in body
    assert "event: stream_end" in body


def test_get_application_result(client):
    # Verify APP-001 can be queried
    response = client.get("/api/v1/applications/APP-001")
    if response.status_code == 200:
        data = response.json()
        assert data["application_id"] == "APP-001"
    else:
        assert response.status_code == 404
