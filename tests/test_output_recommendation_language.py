"""
Tests for Output Recommendation Language Enforcement (plan.md Section 13.12 & AC-03).
Asserts that AI output never states a final decision and remains strictly advisory.
"""

import pytest
from src.guardrails.output_guard import screen_output, enforce_recommendation_language


def test_final_decision_claim_rewritten_to_advisory():
    claims = [
        "Final decision: APPROVE for personal loan.",
        "We have decided to approve this applicant.",
        "This loan is officially approved by the credit system.",
    ]
    for claim in claims:
        cleaned = enforce_recommendation_language(claim, ai_recommendation="APPROVE")
        assert "Final decision: APPROVE" not in cleaned
        assert "officially approved" not in cleaned
        assert "AI recommendation: APPROVE" in cleaned or "Advisory" in cleaned


def test_advisory_language_remains_intact():
    prose = "AI recommendation is REFER based on debt-to-income ratio exceeding policy PL-07 threshold."
    cleaned = enforce_recommendation_language(prose, ai_recommendation="REFER")
    assert "AI recommendation is REFER" in cleaned
