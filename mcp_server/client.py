"""
Client helper for calling MCP tools and reading MCP resources.
Allows agents and selectors to consume MCP server functionality with full transcript logging.
"""

import json
from typing import Dict, Any, List, Optional
from mcp_server.server import get_policy_corpus_index, get_policy_document, compute_affordability


class MCPClient:
    """Synchronous & Async-capable MCP Client for internal agent usage."""

    @staticmethod
    def read_resource_manifest() -> Dict[str, Any]:
        """Reads policy_corpus://index resource and returns the parsed manifest."""
        raw_json = get_policy_corpus_index()
        return json.loads(raw_json)

    @staticmethod
    def call_get_policy_document(policy_id: str, version: str) -> Dict[str, Any]:
        """Invokes get_policy_document MCP tool."""
        raw_json = get_policy_document(policy_id, version)
        return json.loads(raw_json)

    @staticmethod
    def call_compute_affordability(
        income_amount: float,
        income_period: str,
        existing_obligations: List[Dict[str, Any]],
        dti_max_threshold: float = 0.40,
    ) -> Dict[str, Any]:
        """Invokes compute_affordability MCP tool."""
        raw_json = compute_affordability(
            income_amount=income_amount,
            income_period=income_period,
            existing_obligations=existing_obligations,
            dti_max_threshold=dti_max_threshold,
        )
        return json.loads(raw_json)
