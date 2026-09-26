"""
Custom MCP Server for Loan Origination & Underwriting Copilot.
Exposes:
- Resource: policy_corpus://index
- Tool 1: get_policy_document
- Tool 2: compute_affordability
Per plan.md Section 4.5, 13.4 & 14.3.
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
try:
    from fastmcp import FastMCP
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        from mcp.server.mcpserver import MCPServer as FastMCP
from src.domain.calculations import compute_affordability as domain_compute_affordability
from src.observability.unified_logger import log_tool_call

mcp = FastMCP("LoanUnderwritingMCP")

MANIFEST_PATH = Path("data/policy_corpus/policy_corpus_manifest.json")


def _get_corpus_manifest() -> Dict[str, Any]:
    if not MANIFEST_PATH.exists():
        from src.policy.policy_metadata import build_corpus_manifest
        manifest = build_corpus_manifest()
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        return manifest
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@mcp.resource("policy-corpus://index")
def get_policy_corpus_index() -> str:
    """
    Returns the complete lending policy corpus manifest (candidate list).
    Consumed deterministically by policy_selector.py per plan.md Section 14.3.
    """
    manifest = _get_corpus_manifest()
    # MCP resource read is logged by client.py (authoritative MCP transcript layer)
    return json.dumps(manifest, indent=2)


@mcp.tool()
def get_policy_document(policy_id: str, version: str) -> str:
    """
    Tool 1: Retrieves a policy document and its chunks by policy_id and version.
    """
    start_time = time.time()
    manifest = _get_corpus_manifest()
    key = f"{policy_id}:{version}"
    policy_meta = manifest.get("policies", {}).get(key)

    if not policy_meta:
        res = {"error": f"Policy {policy_id} version {version} not found in corpus"}
    else:
        src_path = Path(policy_meta["source_file"])
        doc_content = src_path.read_text(encoding="utf-8") if src_path.exists() else ""
        res = {
            "policy_id": policy_id,
            "version": version,
            "metadata": policy_meta,
            "content": doc_content,
        }

    latency_ms = (time.time() - start_time) * 1000.0
    log_tool_call(
        agent="mcp_server",
        tool_name="get_policy_document",
        args={"policy_id": policy_id, "version": version},
        result={"found": policy_meta is not None},
        latency_ms=latency_ms,
        status="success" if policy_meta else "not_found",
    )
    # MCP tool_call is logged by client.py (authoritative MCP transcript layer)
    return json.dumps(res, indent=2)


@mcp.tool()
def compute_affordability(
    income_amount: float,
    income_period: str,
    existing_obligations: List[Dict[str, Any]],
    dti_max_threshold: float = 0.40,
) -> str:
    """
    Tool 2: Deterministically computes DTI, disposable income, and policy breach flag.
    Uses pure Decimal domain functions.
    """
    start_time = time.time()
    affordability = domain_compute_affordability(
        income_amount=income_amount,
        income_period=income_period,
        existing_obligations=existing_obligations,
        dti_max_threshold=dti_max_threshold,
    )
    res_dict = affordability.to_dict()
    latency_ms = (time.time() - start_time) * 1000.0

    log_tool_call(
        agent="mcp_server",
        tool_name="compute_affordability",
        args={
            "income_period": income_period,
            "dti_max_threshold": dti_max_threshold,
            "obligations_count": len(existing_obligations),
        },
        result={"dti": res_dict["dti"], "breach": res_dict["breach"]},
        latency_ms=latency_ms,
        status="success",
    )
    # MCP tool_call is logged by client.py (authoritative MCP transcript layer)
    return json.dumps(res_dict, indent=2)


if __name__ == "__main__":
    mcp.run()
