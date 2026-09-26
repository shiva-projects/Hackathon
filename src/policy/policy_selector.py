"""
Deterministic Policy Selector.
Per plan.md Section 4.2, 4.6 & 14.3.
Filters candidate policies based on product, jurisdiction, and effective date window:
effective_from <= application_date < effective_to.
NO LLM CALLS HERE.
"""

from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import json


class PolicySelectionResult:
    def __init__(
        self,
        status: str,  # "MATCHED", "NO_APPLICABLE_POLICY", "POLICY_CONFLICT"
        policy: Optional[Dict[str, Any]] = None,
        candidate_ids: Optional[List[str]] = None,
        reason: Optional[str] = None,
    ):
        self.status = status
        self.policy = policy
        self.candidate_ids = candidate_ids or []
        self.reason = reason

    @property
    def is_success(self) -> bool:
        return self.status == "MATCHED" and self.policy is not None


def select_applicable_policy(
    product: str,
    jurisdiction: str,
    application_date: str,
    resource_manifest: Optional[Dict[str, Any]] = None,
    manifest_path: str | Path = "data/policy_corpus/policy_corpus_manifest.json",
) -> PolicySelectionResult:
    """
    Selects the applicable policy deterministically by matching:
    1. product == policy.product
    2. jurisdiction == policy.jurisdiction
    3. effective_from <= application_date < effective_to (effective_from inclusive, effective_to exclusive)

    Candidate list is strictly derived from the resource manifest (Section 14.3).
    """
    if resource_manifest is None:
        path = Path(manifest_path)
        if not path.exists():
            raise FileNotFoundError(f"Policy manifest not found: {manifest_path}")
        with open(path, "r", encoding="utf-8") as f:
            resource_manifest = json.load(f)

    policies_dict = resource_manifest.get("policies", {})
    candidate_ids = list(policies_dict.keys())

    matched_policies = []

    for key, p_meta in policies_dict.items():
        # Match product (case-insensitive)
        if p_meta.get("product", "").lower() != product.lower():
            continue

        # Match jurisdiction (case-insensitive)
        if p_meta.get("jurisdiction", "").upper() != jurisdiction.upper():
            continue

        eff_from = p_meta.get("effective_from", "")
        eff_to = p_meta.get("effective_to", "")

        # Check effective window: effective_from <= application_date < effective_to
        if eff_from <= application_date < eff_to:
            matched_policies.append(p_meta)

    # Resolution logic per Section 4.2
    if len(matched_policies) == 1:
        selected = matched_policies[0]
        return PolicySelectionResult(
            status="MATCHED",
            policy=selected,
            candidate_ids=candidate_ids,
            reason=f"Selected {selected['policy_id']} {selected['version']} for {product} ({jurisdiction}) on {application_date}",
        )
    elif len(matched_policies) == 0:
        return PolicySelectionResult(
            status="NO_APPLICABLE_POLICY",
            policy=None,
            candidate_ids=candidate_ids,
            reason=f"No applicable policy found for {product} in {jurisdiction} on {application_date}",
        )
    else:
        # > 1 match is a policy conflict (Section 4.6)
        matched_keys = [f"{p['policy_id']}:{p['version']}" for p in matched_policies]
        return PolicySelectionResult(
            status="POLICY_CONFLICT",
            policy=None,
            candidate_ids=candidate_ids,
            reason=f"Policy conflict: multiple matching policies found ({', '.join(matched_keys)})",
        )
