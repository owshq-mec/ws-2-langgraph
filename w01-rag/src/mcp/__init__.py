"""MCP server exposing the DataOps Knowledge Hub as agent-callable tools.

Submodules are NOT eagerly imported — the `mcp` SDK dependency is only
required when the server is actually run (`python -m src.mcp.run`).
"""
__all__ = ["create_server", "run_server", "main"]
