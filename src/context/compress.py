"""
Context Compression and Summarization module.
Reduces token volume on long context histories by >50%.
Per plan.md Section 13.10 & 14.21.
"""

from typing import Dict, Any, List, Tuple


def estimate_token_count(text: str) -> int:
    """Estimates token count (~4 characters per token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def compress_interaction_history(
    messages: List[Dict[str, Any]],
    token_threshold: int = 1000,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Compresses verbose interaction history into a concise factual summary
    when total estimated tokens exceed token_threshold.
    Guarantees >= 50% reduction on verbose inputs.
    """
    raw_text = " ".join([m.get("content", "") for m in messages])
    before_tokens = estimate_token_count(raw_text)

    if before_tokens <= token_threshold:
        return messages, {
            "compression_triggered": False,
            "before_tokens": before_tokens,
            "after_tokens": before_tokens,
            "reduction_percentage": 0.0,
        }

    # Extract salient facts into compact structured bullet points
    salient_facts = []
    for msg in messages:
        content = msg.get("content", "")
        role = msg.get("role", "user")
        # Keep key lines with numbers, decisions, or applicant facts
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        for line in lines:
            if any(kw in line.lower() for kw in ["income", "loan", "dti", "amount", "approved", "refer", "document"]):
                salient_facts.append(f"{role}: {line[:80]}")

    if not salient_facts:
        salient_facts = [f"Summary of {len(messages)} prior turns"]

    compressed_summary = "FACT_SUMMARY:\n" + "\n".join(salient_facts[:5])
    after_tokens = estimate_token_count(compressed_summary)

    # Ensure at least 50% reduction
    if after_tokens > before_tokens * 0.5:
        compressed_summary = compressed_summary[: len(raw_text) // 3]
        after_tokens = estimate_token_count(compressed_summary)

    reduction = round((1.0 - (after_tokens / before_tokens)) * 100.0, 1)

    compressed_messages = [{"role": "system", "content": compressed_summary}]

    return compressed_messages, {
        "compression_triggered": True,
        "before_tokens": before_tokens,
        "after_tokens": after_tokens,
        "reduction_percentage": reduction,
    }
