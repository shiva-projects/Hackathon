"""
Policy citation resolution and text hash verification tests (plan.md Section 7.1, 14.8 & 14.12).
Verifies:
1. Cited source_file exists on disk
2. Cited chunk_id exists
3. Cited version matches selected policy
4. SHA-256 text_hash matches disk content (recomputed and checked per Section 14.12)
"""

import hashlib
from pathlib import Path
import pytest
from src.tools.rag_tool import retrieve_policy_chunks
from src.policy.policy_selector import select_applicable_policy


def test_policy_citation_resolution_and_hash_integrity():
    # 1. Select policy
    selection = select_applicable_policy("personal_loan", "IN", "2026-05-01")
    assert selection.is_success
    policy = selection.policy

    # 2. Retrieve chunks
    citations = retrieve_policy_chunks("affordability DTI ratio limits", selected_policy=policy)
    assert len(citations) > 0

    for cit in citations:
        # Check source file exists
        src_path = Path(cit["source_file"])
        assert src_path.exists(), f"Cited source file does not exist: {cit['source_file']}"

        # Check version isolation (Section 4.2 & 14.8)
        assert cit["version"] == policy["version"], f"Citation version {cit['version']} does not match selected policy {policy['version']}"
        assert cit["policy_id"] == policy["policy_id"]

        # Check chunk ID
        assert "chunk_id" in cit
        assert len(cit["chunk_id"]) > 0

        # Check hash integrity against actual file on disk (Section 14.12)
        assert "text_hash" in cit
        file_content = src_path.read_text(encoding="utf-8")
        assert cit["text"] in file_content, f"Chunk text missing from source file {cit['source_file']}"

        recomputed_hash = hashlib.sha256(cit["text"].encode("utf-8")).hexdigest()
        assert cit["text_hash"] == recomputed_hash, "SHA-256 text_hash mismatch (corpus tampering detected)"
