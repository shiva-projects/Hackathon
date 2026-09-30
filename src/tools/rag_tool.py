"""
Targeted RAG Tool for Lending Policy Corpus.
Uses ChromaDB and Sentence-Transformers ('all-MiniLM-L6-v2') for semantic vector retrieval.
Retrieval is strictly scoped to the deterministically selected policy (policy_id + version).
Generates verifiable citations with source_file, chunk_id, and SHA-256 text_hash.
Per plan.md Section 4.2, 7.1, 14.8 & 14.12.
"""

import time
import hashlib
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np
from src.observability.unified_logger import log_tool_call
from src.observability.tracing import tracer

_EMBEDDING_MODEL = None
_CHROMA_CLIENT = None
_CHROMA_COLLECTIONS: Dict[str, Any] = {}


class RAGReproducibilityError(RuntimeError):
    """Raised when embedding model cannot be loaded locally without network."""
    pass


class CorpusIntegrityError(RuntimeError):
    """Raised when policy chunk tampering or hash mismatch is detected."""
    pass


def _reset_embedding_model() -> None:
    """Resets the cached embedding model instance (used for testing)."""
    global _EMBEDDING_MODEL
    _EMBEDDING_MODEL = None


def _get_embedding_model(require_local: bool = True):
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            try:
                # Require local files only — network download prohibited for reproducible offline runs
                _EMBEDDING_MODEL = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
            except Exception as e:
                if require_local:
                    raise RAGReproducibilityError(
                        "Local embedding model 'all-MiniLM-L6-v2' not found. "
                        "Network download is strictly prohibited for reproducible offline runs. "
                        f"Ensure model is cached locally. Underlying error: {e}"
                    ) from e
                raise
        except ImportError as e:
            raise RAGReproducibilityError(
                f"sentence_transformers library not installed: {e}"
            ) from e
    return _EMBEDDING_MODEL


def _get_chroma_collection(collection_name: str = "policy_corpus"):
    global _CHROMA_CLIENT, _CHROMA_COLLECTIONS
    if collection_name in _CHROMA_COLLECTIONS:
        return _CHROMA_COLLECTIONS[collection_name]
    try:
        import chromadb
        if _CHROMA_CLIENT is None:
            _CHROMA_CLIENT = chromadb.Client()
        coll = _CHROMA_CLIENT.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        _CHROMA_COLLECTIONS[collection_name] = coll
        return coll
    except Exception as e:
        print(f"Warning: could not initialize ChromaDB: {e}")
        return None


def extract_rule_id(chunk_text: str) -> str:
    import re
    m = re.search(r"\b(PL-[\w\-]+|UK-MORT-[\w\-]+)\b", chunk_text)
    return m.group(1) if m else "PL-GENERAL"


def extract_all_rule_ids(chunk_text: str) -> List[str]:
    import re
    return re.findall(r"\b(PL-[\w\-]+|UK-MORT-[\w\-]+)\b", chunk_text)


def retrieve_policy_chunks(
    query: str,
    selected_policy: Dict[str, Any],
    manifest_path: str = "data/policy_corpus/policy_corpus_manifest.json",
    top_k: int = 3,
    run_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    RAG retrieval restricted strictly to selected policy's version and chunks.
    Uses dense vector similarity (all-MiniLM-L6-v2) + ChromaDB index.
    Guarantees that every retrieved chunk's policy_id and version match policy_selected.
    """
    from src.context.execution_context import resolve_run_id
    effective_run_id = resolve_run_id(run_id, required=False)
    start_time = time.time()
    p_path = Path(manifest_path)
    if not p_path.exists():
        from src.policy.policy_metadata import build_corpus_manifest
        manifest = build_corpus_manifest()
    else:
        with open(p_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

    target_policy_id = selected_policy.get("policy_id")
    target_version = str(selected_policy.get("version"))

    # 1. Strict pre-filtering to candidate chunks of the selected policy
    candidate_chunks = [
        c for c in manifest.get("chunks", {}).values()
        if c.get("policy_id") == target_policy_id and str(c.get("version")) == target_version
    ]

    if not candidate_chunks:
        return []

    # 2. Dense Vector Retrieval with Sentence-Transformers + ChromaDB
    model = _get_embedding_model(require_local=True)
    if model is None:
        raise RAGReproducibilityError("Local embedding model 'all-MiniLM-L6-v2' unavailable.")

    chroma_coll = _get_chroma_collection("policy_corpus")

    scored_chunks = []

    try:
        # Check if candidates are in collection
        chunk_ids = [c["chunk_id"] for c in candidate_chunks]
        chunk_texts = [c["text"] for c in candidate_chunks]
        metadatas = [
            {"policy_id": c["policy_id"], "version": str(c["version"]), "chunk_id": c["chunk_id"]}
            for c in candidate_chunks
        ]

        if chroma_coll:
            # Exact chunk ID and metadata membership verification in ChromaDB (NEVER collection.count())
            existing_data = chroma_coll.get(ids=chunk_ids, include=["metadatas"])
            existing_ids = set(existing_data.get("ids", []) or [])
            existing_meta_map = {
                cid: meta
                for cid, meta in zip(
                    existing_data.get("ids", []) or [],
                    existing_data.get("metadatas", []) or [],
                )
            }

            missing_indices = []
            for idx, c in enumerate(candidate_chunks):
                cid = c["chunk_id"]
                if cid not in existing_ids:
                    missing_indices.append(idx)
                else:
                    meta = existing_meta_map.get(cid) or {}
                    if meta.get("policy_id") != c["policy_id"] or str(meta.get("version")) != str(c["version"]):
                        missing_indices.append(idx)

            # Upsert any chunks missing or having mismatched metadata
            if missing_indices:
                missing_ids = [candidate_chunks[i]["chunk_id"] for i in missing_indices]
                missing_texts = [candidate_chunks[i]["text"] for i in missing_indices]
                missing_metas = [metadatas[i] for i in missing_indices]
                missing_embeddings = model.encode(missing_texts).tolist()
                chroma_coll.upsert(
                    ids=missing_ids,
                    documents=missing_texts,
                    embeddings=missing_embeddings,
                    metadatas=missing_metas,
                )

            # Verify exact membership in Chroma after upsert
            verify_data = chroma_coll.get(ids=chunk_ids, include=["metadatas"])
            verified_ids = set(verify_data.get("ids", []) or [])
            if not set(chunk_ids).issubset(verified_ids):
                unindexed = set(chunk_ids) - verified_ids
                raise CorpusIntegrityError(
                    f"Chroma membership verification failed: chunks {unindexed} missing from Chroma collection."
                )

            # Query Chroma with query embedding
            query_emb = model.encode([query]).tolist()
            query_res = chroma_coll.query(
                query_embeddings=query_emb,
                n_results=min(top_k * 2, len(candidate_chunks)),
                where={"$and": [{"policy_id": target_policy_id}, {"version": target_version}]},
            )
            retrieved_ids = query_res["ids"][0] if query_res["ids"] else []
            distances = query_res["distances"][0] if "distances" in query_res and query_res["distances"] else [0.0] * len(retrieved_ids)
            id_to_chunk = {c["chunk_id"]: c for c in candidate_chunks}

            for cid, dist in zip(retrieved_ids, distances):
                if cid in id_to_chunk:
                    sim_score = max(0.0, 1.0 - float(dist))
                    c = id_to_chunk[cid]
                    scored_chunks.append((c, sim_score))
        else:
            # Direct cosine similarity fallback
            query_emb = model.encode([query]).tolist()
            doc_embs = model.encode(chunk_texts)
            q_emb = np.array(query_emb[0])
            for c, d_emb in zip(candidate_chunks, doc_embs):
                cos_sim = float(np.dot(q_emb, d_emb) / (np.linalg.norm(q_emb) * np.linalg.norm(d_emb) + 1e-9))
                scored_chunks.append((c, cos_sim))
    except (CorpusIntegrityError, RAGReproducibilityError):
        raise
    except Exception as e:
        fallback_reason = str(e)
        scored_chunks = []
        from src.observability.unified_logger import log_event
        log_event(
            "rag_degraded_mode",
            "logs/agent_actions.jsonl",
            {
                "event": "rag_degraded_mode",
                "primary": "chromadb",
                "fallback": "lexical",
                "reason": fallback_reason,
                "run_id": run_id,
            },
        )

    # Fallback to token overlap if vector scoring was empty
    if not scored_chunks:
        import re
        q_tokens = set(re.findall(r"\b\w{3,}\b", query.lower()))
        for c in candidate_chunks:
            c_tokens = set(re.findall(r"\b\w{3,}\b", c["text"].lower()))
            overlap = len(q_tokens.intersection(c_tokens))
            scored_chunks.append((c, float(overlap)))

        # Enforce minimum relevance score for lexical retrieval (do not accept zero-overlap chunks)
        MIN_RELEVANCE_SCORE = 1.0
        scored_chunks = [(c, s) for c, s in scored_chunks if s >= MIN_RELEVANCE_SCORE]
        if not scored_chunks:
            return []

    # Sort descending by score
    scored_chunks.sort(key=lambda x: x[1], reverse=True)
    top_candidates = scored_chunks[:top_k]

    # 3. Canonical source extraction and hash integrity verification
    from src.policy.policy_metadata import extract_canonical_chunk_from_file

    results = []
    for chunk, score in top_candidates:
        chunk_id = chunk.get("chunk_id")
        src_file = Path(chunk.get("source_file", ""))
        expected_manifest_hash = chunk.get("text_hash")

        if not src_file.exists():
            raise CorpusIntegrityError(
                f"Corpus integrity violation: source file '{src_file}' does not exist for chunk {chunk_id}."
            )

        # Canonical source extraction
        canonical_chunk = extract_canonical_chunk_from_file(src_file, chunk_id)
        if not canonical_chunk:
            raise CorpusIntegrityError(
                f"Corpus integrity violation: chunk '{chunk_id}' not found in source file '{src_file}' using canonical extraction."
            )

        canonical_text = canonical_chunk["text"]
        computed_canonical_hash = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()

        # Compare canonical hash with manifest hash
        if expected_manifest_hash and computed_canonical_hash != expected_manifest_hash:
            raise CorpusIntegrityError(
                f"Corpus integrity violation: chunk {chunk_id} hash mismatch. "
                f"Expected manifest hash {expected_manifest_hash}, computed canonical hash {computed_canonical_hash}."
            )

        # Verify policy_id and version match target
        if canonical_chunk["policy_id"] != target_policy_id or str(canonical_chunk["version"]) != str(target_version):
            raise CorpusIntegrityError(
                f"Corpus integrity violation: chunk {chunk_id} policy/version "
                f"({canonical_chunk['policy_id']} {canonical_chunk['version']}) does not match selected policy "
                f"({target_policy_id} {target_version})."
            )

        rule_ids = extract_all_rule_ids(canonical_text)
        primary_rule_id = rule_ids[0] if rule_ids else extract_rule_id(canonical_text)

        # Record policy ID/version/hash in retrieval evidence
        results.append({
            "policy_id": canonical_chunk["policy_id"],
            "version": canonical_chunk["version"],
            "rule_id": primary_rule_id,
            "rule_ids": rule_ids,
            "source_file": chunk["source_file"],
            "chunk_id": chunk_id,
            "text_hash": computed_canonical_hash,
            "text": canonical_text,
            "score": round(score, 4),
        })

    end_time = time.time()
    latency_ms = round((end_time - start_time) * 1000.0, 2)

    # Log real measured tool call
    log_tool_call(
        agent="policy_agent",
        tool_name="retrieve_policy_chunks",
        args={"query": query, "policy_id": target_policy_id, "version": target_version},
        result=[{"chunk_id": r["chunk_id"], "rule_id": r["rule_id"], "score": r["score"]} for r in results],
        latency_ms=latency_ms,
        status="success",
        run_id=run_id,
    )

    # Record real tool span in tracer
    tracer.record_span(
        name="rag.retrieve_policy_chunks",
        span_kind="tool",
        start_time=start_time,
        end_time=end_time,
        inputs={"query": query, "policy_id": target_policy_id, "version": target_version},
        outputs={"chunks_found": len(results), "top_chunk_id": results[0]["chunk_id"] if results else None},
        run_id=effective_run_id,
        step_id="step-rag-retrieval",
    )

    return results


async def aretrieve_policy_chunks(
    query: str,
    selected_policy: Dict[str, Any],
    manifest_path: str = "data/policy_corpus/policy_corpus_manifest.json",
    top_k: int = 3,
    run_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Asynchronously executes targeted policy chunk retrieval."""
    import asyncio
    return await asyncio.to_thread(
        retrieve_policy_chunks,
        query=query,
        selected_policy=selected_policy,
        manifest_path=manifest_path,
        top_k=top_k,
        run_id=run_id,
    )
