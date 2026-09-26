"""
Policy metadata parsing and RAG chunk index generator with text hash verification.
Per plan.md Section 14.11 & 14.12.
"""

import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml
import re


class PolicyDocument:
    def __init__(
        self,
        policy_id: str,
        version: str,
        product: str,
        jurisdiction: str,
        effective_from: str,
        effective_to: str,
        rules: List[Dict[str, Any]],
        source_file: str,
        prose_content: str,
        chunks: List[Dict[str, Any]],
    ):
        self.policy_id = policy_id
        self.version = version
        self.product = product
        self.jurisdiction = jurisdiction
        self.effective_from = effective_from
        self.effective_to = effective_to
        self.rules = rules
        self.source_file = source_file
        self.prose_content = prose_content
        self.chunks = chunks

    def to_manifest_entry(self) -> Dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "product": self.product,
            "jurisdiction": self.jurisdiction,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "source_file": self.source_file,
            "rule_count": len(self.rules),
            "rules": self.rules,
        }


def parse_policy_file(file_path: str | Path) -> PolicyDocument:
    """Parses a markdown policy file with YAML frontmatter."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Policy file not found: {file_path}")

    content = path.read_text(encoding="utf-8")
    frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if not frontmatter_match:
        raise ValueError(f"Invalid policy format: Missing YAML frontmatter in {file_path}")

    fm_raw = frontmatter_match.group(1)
    prose_content = frontmatter_match.group(2).strip()

    metadata = yaml.safe_load(fm_raw)
    policy_id = metadata["policy_id"]
    version = str(metadata["version"])
    product = metadata["product"]
    jurisdiction = metadata["jurisdiction"]
    effective_from = metadata["effective_from"]
    effective_to = metadata["effective_to"]
    rules = metadata.get("rules", [])

    # Extract chunks from prose sections
    chunks = []
    # Pattern to look for ## Section headers with optional chunk annotations
    sections = re.split(r"\n(?=##\s+)", prose_content)
    for idx, sec in enumerate(sections):
        sec_text = sec.strip()
        if not sec_text:
            continue
        chunk_id_match = re.search(r"\(Chunk:\s*([\w\-]+)\)", sec_text)
        if chunk_id_match:
            chunk_id = chunk_id_match.group(1)
        else:
            chunk_id = f"{policy_id.lower()}-{version.replace('.', '')}-chunk-{idx+1:03d}"

        # Clean text hash for verification
        text_hash = hashlib.sha256(sec_text.encode("utf-8")).hexdigest()
        chunks.append({
            "chunk_id": chunk_id,
            "policy_id": policy_id,
            "version": version,
            "source_file": str(path.as_posix()),
            "text": sec_text,
            "text_hash": text_hash,
        })

    return PolicyDocument(
        policy_id=policy_id,
        version=version,
        product=product,
        jurisdiction=jurisdiction,
        effective_from=effective_from,
        effective_to=effective_to,
        rules=rules,
        source_file=str(path.as_posix()),
        prose_content=prose_content,
        chunks=chunks,
    )


def load_all_policies(corpus_dir: str | Path = "data/policy_corpus") -> Dict[str, PolicyDocument]:
    """Loads all policy markdown documents from directory."""
    directory = Path(corpus_dir)
    policies = {}
    for md_file in directory.glob("*.md"):
        doc = parse_policy_file(md_file)
        key = f"{doc.policy_id}:{doc.version}"
        policies[key] = doc
    return policies


def build_corpus_manifest(corpus_dir: str | Path = "data/policy_corpus") -> Dict[str, Any]:
    """Generates the full corpus manifest JSON for MCP resource and selector."""
    policies = load_all_policies(corpus_dir)
    manifest = {
        "policies": {},
        "chunks": {},
    }
    for key, doc in policies.items():
        manifest["policies"][key] = doc.to_manifest_entry()
        for chunk in doc.chunks:
            manifest["chunks"][chunk["chunk_id"]] = {
                "chunk_id": chunk["chunk_id"],
                "policy_id": chunk["policy_id"],
                "version": chunk["version"],
                "source_file": chunk["source_file"],
                "text_hash": chunk["text_hash"],
                "text": chunk["text"],
            }
    return manifest
