"""
Demonstration runner for the FastAPI streaming endpoint.
Connects to the FastAPI underwriting streaming endpoint, receives SSE events,
and records the live execution trace to logs/api_stream_demo.log.
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from starlette.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.server import app

def run_api_stream_demo():
    print("==================================================")
    print("LOAN ORIGINATION COPILOT - FASTAPI STREAMING DEMO")
    print("==================================================")

    client = TestClient(app)

    # 1. Check health
    health_resp = client.get("/health")
    print(f"[HEALTH CHECK] Status: {health_resp.status_code}, Body: {health_resp.json()}")

    # 2. Stream an underwriting request
    payload = {
        "application_id": "TEST-STREAM-DEMO-001",
        "applicant_data": {
            "application_id": "TEST-STREAM-DEMO-001",
            "applicant_name": "Priya Patel",
            "product": "personal_loan",
            "jurisdiction": "IN",
            "application_date": "2026-04-10",
            "income_amount": 95000.0,
            "income_period": "monthly",
            "currency": "INR",
            "requested_amount": 350000.0,
            "tenure_months": 24,
            "employment": "salaried",
            "existing_obligations": [
                {"obligation_type": "two_wheeler_loan", "amount": 8000.0, "period": "monthly"}
            ],
            "documents": ["identity_proof", "income_statement"],
            "free_text": "Requesting unsecured personal loan for relocation expenses.",
        },
        "actor_id": "LO-001",
        "actor_role": "loan_officer",
    }

    log_path = PROJECT_ROOT / "logs" / "api_stream_demo.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n[STREAMING] Initiating POST /api/v1/underwrite/stream for {payload['application_id']}...")
    response = client.post("/api/v1/underwrite/stream", json=payload)
    print(f"[RESPONSE] HTTP Status: {response.status_code}")
    print(f"[RESPONSE] Content-Type: {response.headers.get('content-type')}")

    lines = response.text.strip().split("\n\n")
    print(f"[SSE STREAM] Received {len(lines)} event frames:")

    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"--- FASTAPI SSE STREAMING RUN [{datetime.now(timezone.utc).isoformat()}] ---\n")
        for i, frame in enumerate(lines, 1):
            print(f"  Frame {i}: {frame}")
            f.write(f"Frame {i}:\n{frame}\n\n")

    print(f"\n[DEMO COMPLETE] Full SSE transcript written to {log_path}")

if __name__ == "__main__":
    run_api_stream_demo()
