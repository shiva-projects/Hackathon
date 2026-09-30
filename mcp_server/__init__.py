"""MCP Server and Client module."""
from mcp_server.client import MCPClient, MCPUnavailableError

__all__ = ["MCPClient", "MCPUnavailableError"]
