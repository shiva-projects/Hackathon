"""
Policy citation resolution and text hash verification tests (plan.md Section 7.1, 14.8 & 14.12).
Verifies:
1. Cited source_file exists on disk
2. Cited chunk_id exists
3. Cited version matches selected policy
4. SHA-256 text_hash matches disk content (recomputed and checked per Section 14.12)
"""

import hashlib
import json
from pathlib import Path
import pytest
from src.tools.rag_tool import (
    retrieve_policy_chunks,
    _get_embedding_model,
    _reset_embedding_model,
    _get_chroma_collection,
    RAGReproducibilityError,
    CorpusIntegrityError,
)
from src.policy.policy_selector import select_applicable_policy
from src.policy.policy_metadata import extract_canonical_chunk_from_file


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

        # Check hash integrity against actual file on disk via canonical extraction (Section 14.12)
        assert "text_hash" in cit
        canonical_chunk = extract_canonical_chunk_from_file(src_path, cit["chunk_id"])
        assert canonical_chunk is not None, f"Chunk {cit['chunk_id']} not found in source file {cit['source_file']}"
        assert cit["text"] == canonical_chunk["text"]

        recomputed_hash = hashlib.sha256(cit["text"].encode("utf-8")).hexdigest()
        assert cit["text_hash"] == recomputed_hash, "SHA-256 text_hash mismatch (corpus tampering detected)"


def test_offline_retrieval_uses_local_model_and_reproducible():
    selection = select_applicable_policy("personal_loan", "IN", "2026-05-01")
    assert selection.is_success
    policy = selection.policy

    # Prove model loads strictly locally without network
    model = _get_embedding_model(require_local=True)
    assert model is not None

    citations = retrieve_policy_chunks("affordability DTI ratio limits", selected_policy=policy)
    assert len(citations) > 0
    for cit in citations:
        assert cit["policy_id"] == "PL-001"
        assert cit["version"] == "v2.0"
        assert "text_hash" in cit
        assert len(cit["text_hash"]) == 64


def test_missing_local_model_fails_with_reproducibility_error(monkeypatch):
    import sentence_transformers

    def mock_init(*args, **kwargs):
        raise OSError("Local snapshot files not found in cache")

    _reset_embedding_model()
    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", mock_init)

    try:
        with pytest.raises(RAGReproducibilityError, match="strictly prohibited for reproducible"):
            _get_embedding_model(require_local=True)
    finally:
        _reset_embedding_model()


def test_tampered_manifest_hash_fails_closed(tmp_path):
    selection = select_applicable_policy("personal_loan", "IN", "2026-05-01")
    policy = selection.policy

    real_manifest_path = Path("data/policy_corpus/policy_corpus_manifest.json")
    manifest = json.loads(real_manifest_path.read_text(encoding="utf-8"))

    # Tamper with chunk-dti-002 hash
    if "chunk-dti-002" in manifest["chunks"]:
        manifest["chunks"]["chunk-dti-002"]["text_hash"] = "0" * 64

    tampered_manifest_file = tmp_path / "tampered_manifest.json"
    tampered_manifest_file.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(CorpusIntegrityError, match="hash mismatch"):
        retrieve_policy_chunks(
            "affordability DTI ratio limits",
            selected_policy=policy,
            manifest_path=str(tampered_manifest_file),
        )


def test_missing_chunk_in_source_file_fails_closed(tmp_path):
    selection = select_applicable_policy("personal_loan", "IN", "2026-05-01")
    policy = selection.policy

    real_manifest_path = Path("data/policy_corpus/policy_corpus_manifest.json")
    manifest = json.loads(real_manifest_path.read_text(encoding="utf-8"))

    # Insert a fictitious chunk not present in source file
    manifest["chunks"]["chunk-ghost-999"] = {
        "chunk_id": "chunk-ghost-999",
        "policy_id": "PL-001",
        "version": "v2.0",
        "source_file": "data/policy_corpus/PL_retail_personal_loan_v2.md",
        "text_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "text": "Fictitious rule that does not exist in source markdown",
    }

    ghost_manifest_file = tmp_path / "ghost_manifest.json"
    ghost_manifest_file.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(CorpusIntegrityError, match="not found in source file"):
        retrieve_policy_chunks(
            "Fictitious rule that does not exist in source markdown",
            selected_policy=policy,
            manifest_path=str(ghost_manifest_file),
        )


def test_chroma_exact_membership_verification():
    selection = select_applicable_policy("personal_loan", "IN", "2026-05-01")
    policy = selection.policy

    citations = retrieve_policy_chunks("minimum acceptable monthly gross income", selected_policy=policy)
    assert len(citations) > 0

    coll = _get_chroma_collection("policy_corpus")
    if coll is not None:
        chunk_ids = [c["chunk_id"] for c in citations]
        res = coll.get(ids=chunk_ids, include=["metadatas"])
        found_ids = set(res.get("ids", []))
        for cid in chunk_ids:
            assert cid in found_ids
        for meta in res.get("metadatas", []):
            assert meta["policy_id"] == "PL-001"
            assert meta["version"] == "v2.0"
