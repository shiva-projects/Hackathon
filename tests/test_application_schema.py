"""
Unit tests for LoanApplication schema validation & normalization (plan.md Section 8.3 & 14.9).
"""

from decimal import Decimal
import pytest
from pydantic import ValidationError
from src.ingestion.application_loader import (
    LoanApplication,
    Obligation,
    load_application_from_dict,
)


def test_valid_loan_application_monthly():
    data = {
        "application_id": "APP-001",
        "applicant_name": "Rohan Sharma",
        "product": "personal_loan",
        "jurisdiction": "IN",
        "application_date": "2026-03-15",
        "income_amount": 100000.0,
        "income_period": "monthly",
        "currency": "INR",
        "requested_amount": 500000.0,
        "tenure_months": 36,
        "employment": "salaried",
        "existing_obligations": [
            {"obligation_type": "car_loan", "amount": 20000.0, "period": "monthly"},
            {"obligation_type": "credit_card", "amount": 10000.0, "period": "monthly"},
        ],
        "documents": ["identity_proof", "income_statement", "bank_statement"],
        "free_text": "Looking for loan for home improvement.",
    }
    app = load_application_from_dict(data)
    assert app.application_id == "APP-001"
    assert app.monthly_gross_income == Decimal("100000.00")
    assert app.total_monthly_obligations == Decimal("30000.00")
    facts = app.to_facts_dict()
    assert facts["monthly_gross_income"] == 100000.0
    assert facts["total_monthly_obligations"] == 30000.0


def test_annual_income_and_obligation_normalization():
    data = {
        "application_id": "APP-002",
        "applicant_name": "Priya Verma",
        "product": "personal_loan",
        "jurisdiction": "IN",
        "application_date": "2026-04-10",
        "income_amount": 1200000.0,  # 1.2M annual = 100,000 monthly
        "income_period": "annual",
        "currency": "inr",  # should be capitalized
        "requested_amount": 300000.0,
        "tenure_months": 24,
        "employment": "salaried",
        "existing_obligations": [
            {"obligation_type": "education_loan", "amount": 240000.0, "period": "annual"}  # 20,000 monthly
        ],
        "documents": ["identity_proof", "income_statement"],
    }
    app = load_application_from_dict(data)
    assert app.currency == "INR"
    assert app.monthly_gross_income == Decimal("100000.00")
    assert app.total_monthly_obligations == Decimal("20000.00")


def test_negative_income_rejected():
    data = {
        "application_id": "APP-003",
        "applicant_name": "Test User",
        "product": "personal_loan",
        "jurisdiction": "IN",
        "application_date": "2026-03-15",
        "income_amount": -50000.0,  # Negative income must be rejected
        "income_period": "monthly",
        "requested_amount": 200000.0,
        "tenure_months": 12,
        "employment": "salaried",
    }
    with pytest.raises(ValidationError):
        load_application_from_dict(data)


def test_zero_requested_amount_rejected():
    data = {
        "application_id": "APP-004",
        "applicant_name": "Test User",
        "product": "personal_loan",
        "jurisdiction": "IN",
        "application_date": "2026-03-15",
        "income_amount": 50000.0,
        "requested_amount": 0.0,  # Zero requested amount must be rejected
        "tenure_months": 12,
        "employment": "salaried",
    }
    with pytest.raises(ValidationError):
        load_application_from_dict(data)


def test_invalid_date_format_rejected():
    data = {
        "application_id": "APP-005",
        "applicant_name": "Test User",
        "product": "personal_loan",
        "jurisdiction": "IN",
        "application_date": "15-03-2026",  # Must be YYYY-MM-DD
        "income_amount": 50000.0,
        "requested_amount": 100000.0,
        "tenure_months": 12,
        "employment": "salaried",
    }
    with pytest.raises(ValidationError):
        load_application_from_dict(data)
