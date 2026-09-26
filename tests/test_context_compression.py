"""
Tests for Context Compression with minimum-effectiveness target (plan.md Section 13.10 & 14.21).
Asserts:
- Compression triggers on large history (data/sample_applications/context_stress.json)
- after_tokens <= before_tokens * 0.5 (strictly > 50% token reduction)
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

    # Assert compression triggered
    assert stats["compression_triggered"] is True

    # Assert strict minimum reduction target (plan.md Section 13.10)
    assert stats["after_tokens"] < stats["before_tokens"]
    assert stats["after_tokens"] <= stats["before_tokens"] * 0.5
    assert stats["reduction_percentage"] >= 50.0


def test_short_history_does_not_trigger_compression():
    short_messages = [{"role": "user", "content": "Hello."}]
    compressed_msgs, stats = compress_interaction_history(short_messages, token_threshold=500)
    assert stats["compression_triggered"] is False
    assert stats["before_tokens"] == stats["after_tokens"]
