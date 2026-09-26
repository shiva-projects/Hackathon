"""
Tests for Context Compression with minimum-effectiveness target and adversarial scenarios.
Per plan.md Section 13.10 & 14.21.
"""

import json
from pathlib import Path
import pytest
from src.context.compress import compress_interaction_history, estimate_token_count


def test_context_compression_achieves_greater_than_50_percent_reduction():
    stress_file = Path("data/sample_applications/context_stress.json")
    assert stress_file.exists()
    data = json.loads(stress_file.read_text(encoding="utf-8"))
    messages = data.get("interaction_history", [])

    compressed_msgs, stats = compress_interaction_history(messages, token_threshold=100)

    # Assert compression triggered and succeeded
    assert stats["compression_triggered"] is True
    assert stats["compression_successful"] is True

    # Assert strict minimum reduction target (plan.md Section 13.10)
    assert stats["after_tokens"] < stats["before_tokens"]
    assert stats["after_tokens"] <= stats["before_tokens"] * 0.5
    assert stats["reduction_percentage"] >= 50.0

    # Ensure no arbitrary mid-word chopping occurred
    summary = compressed_msgs[0]["content"]
    assert "FACTUAL_CONTEXT_SUMMARY" in summary
    assert not summary.endswith("...")
    assert not any(line.endswith(("inc", "dt", "appr")) for line in summary.splitlines())


def test_short_history_does_not_trigger_compression():
    short_messages = [{"role": "user", "content": "Hello."}]
    compressed_msgs, stats = compress_interaction_history(short_messages, token_threshold=500)
    assert stats["compression_triggered"] is False
    assert stats["compression_successful"] is True
    assert stats["before_tokens"] == stats["after_tokens"]
    assert compressed_msgs == short_messages


def test_adversarial_very_repetitive_text():
    """Adversarial test: 20 repeated messages with verbose chatter."""
    repeated_msg = (
        "Hello assistant! I am following up on my personal loan application for 500000 INR. "
        "My monthly income is 80000 INR and my current EMI obligations are 15000 INR. "
        "Please provide an update as soon as possible, thank you very much!"
    )
    messages = [{"role": "user", "content": repeated_msg} for _ in range(15)]
    compressed_msgs, stats = compress_interaction_history(messages, token_threshold=100)

    assert stats["compression_triggered"] is True
    assert stats["compression_successful"] is True
    assert stats["reduction_percentage"] >= 50.0
    summary = compressed_msgs[0]["content"]
    assert "repeated 15 times" in summary or "500000" in summary
    assert "User" in summary


def test_adversarial_long_structured_text():
    """Adversarial test: Detailed financial schedule across multiple turns."""
    messages = [
        {"role": "user", "content": f"Obligation entry #{i}: Loan amount 50000 INR, monthly EMI 3200 INR with tenure 18 months."}
        for i in range(12)
    ] + [
        {"role": "assistant", "content": "Computed total EMI obligations: 38400 INR. Monthly income 120000 INR. Under policy PL-07, DTI is 32.0% which satisfies threshold."}
    ]
    compressed_msgs, stats = compress_interaction_history(messages, token_threshold=80)

    assert stats["compression_triggered"] is True
    assert stats["compression_successful"] is True
    assert stats["reduction_percentage"] >= 50.0
    summary = compressed_msgs[0]["content"]
    # Critical underwriting conclusion remains intact
    assert "DTI" in summary or "PL-07" in summary or "32.0%" in summary


def test_adversarial_naive_truncation_would_destroy_end_information():
    """
    Adversarial test: Critical approval verdict is at the very end of a verbose message.
    Naive character slicing [:len//3] would wipe out the end verdict.
    """
    filler = "We discussed introductory formalities and verified email addresses. " * 15
    critical_end = "Under Rule PL-09, the applicant is approved with interest concession."
    messages = [
        {"role": "assistant", "content": filler + critical_end}
    ]

    compressed_msgs, stats = compress_interaction_history(messages, token_threshold=50)

    assert stats["compression_triggered"] is True
    assert stats["compression_successful"] is True
    assert stats["reduction_percentage"] >= 50.0

    summary = compressed_msgs[0]["content"]
    # The crucial end information is preserved
    assert "approved" in summary.lower() or "pl-09" in summary.lower()
