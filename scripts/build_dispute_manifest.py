"""
Build manifest for Dispute & Chargeback Rules Corpus.
"""
import hashlib
import json
import re
from pathlib import Path

def build_dispute_manifest():
    corpus_dir = Path("data/dispute_rules")
    chunks = {}

    for f in sorted(corpus_dir.glob("*.md")):
        content = f.read_text(encoding="utf-8")
        sections = re.split(r"\n(?=###?\s+)", content)
        for i, sec in enumerate(sections):
            sec = sec.strip()
            if not sec or len(sec) < 30:
                continue
            
            # Find chunk_id if present
            m_id = re.search(r"Chunk ID:\s*`([^`]+)`", sec)
            chunk_id = m_id.group(1) if m_id else f"{f.stem}-chunk-{i:03d}"
            
            # Find rule code
            m_rule = re.search(r"###?\s+(?:Rule\s+)?([A-Za-z0-9\.\-\/]+)", sec)
            rule_code = m_rule.group(1) if m_rule else "DISP-GEN"
            
            text_hash = hashlib.sha256(sec.encode("utf-8")).hexdigest()
            chunks[chunk_id] = {
                "chunk_id": chunk_id,
                "rule_code": rule_code,
                "source_file": str(f).replace("\\", "/"),
                "text": sec,
                "text_hash": text_hash,
                "policy_id": "DISPUTE_RULES_2026",
                "version": "v1.0",
            }

    manifest = {
        "corpus_name": "Card Dispute & Chargeback Rules",
        "total_chunks": len(chunks),
        "chunks": chunks,
    }

    out_file = corpus_dir / "dispute_manifest.json"
    with open(out_file, "w", encoding="utf-8") as mf:
        json.dump(manifest, mf, indent=2)

    print(f"Generated dispute manifest with {len(chunks)} chunks at {out_file}")
    return manifest

if __name__ == "__main__":
    build_dispute_manifest()
