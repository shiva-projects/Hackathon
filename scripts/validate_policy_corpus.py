"""
Pre-flight Policy Corpus Validator and Manifest Generator.
Per plan.md Section 14.16 & 14.12.
Validates:
- Every policy has unique policy_id + version
- Valid date formats and effective_from <= effective_to
- Valid product and jurisdiction
- Unique rule_ids and valid rule_types
- Verifies chunk SHA-256 text hashes
"""

import sys
import json
import hashlib
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.policy.policy_metadata import load_all_policies, build_corpus_manifest

ALLOWED_RULE_TYPES = {
    "dti_max",
    "loan_amount_max",
    "minimum_income",
    "minimum_tenure",
    "high_value_review",
    "required_document",
}


def validate_corpus(corpus_dir: str = "data/policy_corpus") -> bool:
    print(f"Validating policy corpus at: {corpus_dir}")
    path = Path(corpus_dir)
    if not path.exists():
        print(f"FAIL: Corpus directory {corpus_dir} does not exist.")
        return False

    policies = load_all_policies(corpus_dir)
    if not policies:
        print("FAIL: No policy markdown files found.")
        return False

    seen_keys = set()
    errors = []

    for key, doc in policies.items():
        if key in seen_keys:
            errors.append(f"Duplicate policy key: {key}")
        seen_keys.add(key)

        # Date validation
        if doc.effective_from >= doc.effective_to:
            errors.append(f"Invalid date range in {key}: {doc.effective_from} >= {doc.effective_to}")

        if not doc.product or not doc.jurisdiction:
            errors.append(f"Missing product or jurisdiction in {key}")

        # Rule validation
        seen_rules = set()
        for rule in doc.rules:
            rid = rule.get("rule_id")
            rtype = rule.get("rule_type")
            if not rid:
                errors.append(f"Rule missing rule_id in {key}")
            if rid in seen_rules:
                errors.append(f"Duplicate rule_id {rid} in {key}")
            seen_rules.add(rid)

            if rtype not in ALLOWED_RULE_TYPES:
                errors.append(f"Invalid rule_type '{rtype}' in {key} for rule {rid}")

        # Chunk hash validation
        for chunk in doc.chunks:
            expected_hash = hashlib.sha256(chunk["text"].encode("utf-8")).hexdigest()
            if chunk["text_hash"] != expected_hash:
                errors.append(f"Hash mismatch for chunk {chunk['chunk_id']} in {key}")

    if errors:
        print("Corpus validation FAILED with errors:")
        for err in errors:
            print(f" - {err}")
        return False

    # Save corpus manifest
    manifest = build_corpus_manifest(corpus_dir)
    manifest_path = path / "policy_corpus_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"SUCCESS: Policy corpus validated cleanly ({len(policies)} policies, {len(manifest['chunks'])} chunks).")
    print(f"Manifest written to: {manifest_path}")
    return True


if __name__ == "__main__":
    success = validate_corpus()
    sys.exit(0 if success else 1)
