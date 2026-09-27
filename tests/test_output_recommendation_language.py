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


from decimal import Decimal
from src.guardrails.output_guard import validate_rationale_numeric_consistency
from src.prompts import build_rationale_prompt, RATIONALE_SYSTEM_PROMPT_V1


def test_rationale_numeric_consistency_validation():
    # 1. Matching DTI passes
    consistent_prose = "Applicant DTI of 35.0% is within standard limits."
    is_valid, msg = validate_rationale_numeric_consistency(consistent_prose, "APPROVE", Decimal("0.35"))
    assert is_valid is True

    # 2. Hallucinated DTI flagged
    hallucinated_prose = "The borrower exhibits a DTI of 15.0% with stable employment history."
    is_valid, msg = validate_rationale_numeric_consistency(hallucinated_prose, "REFER", Decimal("0.55"))
    assert is_valid is False
    assert "Hallucinated DTI" in msg

    # 3. Opposing recommendation flagged
    opposing_prose = "We strongly approve this application due to excellent profile."
    is_valid, msg = validate_rationale_numeric_consistency(opposing_prose, "REFER", Decimal("0.55"))
    assert is_valid is False
    assert "contradicting deterministic recommendation" in msg

    # 4. screen_output attaches correction on hallucination
    corrected = screen_output(hallucinated_prose, "REFER", dti=Decimal("0.55"))
    assert "[Correction: Official deterministic assessment is REFER based on calculated DTI of 55.0%]" in corrected


def test_versioned_prompt_construction():
    prompt = build_rationale_prompt(
        recommendation="REFER",
        policy_version="v2.0",
        dti=Decimal("0.52"),
        breach=True,
        reasons=["DTI 52.0% breaches 40.0% threshold"],
    )
    assert RATIONALE_SYSTEM_PROMPT_V1 in prompt
    assert "AI Recommendation: REFER" in prompt
    assert "Calculated Debt-to-Income (DTI): 52.0%" in prompt
    assert "DTI Breach Status: BREACH DETECTED" in prompt

