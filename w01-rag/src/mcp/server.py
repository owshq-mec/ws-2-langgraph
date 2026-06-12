"""MCP server that exposes the DataOps Knowledge Hub as agent-callable tools.

Transport: stdio (stdin/stdout JSON-RPC). Logging is forced to stderr so the
JSON-RPC channel on stdout stays clean — any stray write to stdout would
desynchronize the protocol.

Tools:
  - query_knowledge_hub  → POST /api/v1/query
  - check_platform_health → GET  /health
  - trigger_ingestion    → POST /api/v1/ingest
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

log = logging.getLogger("dataops-mcp")

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
API_TIMEOUT_SECONDS = float(os.getenv("API_TIMEOUT_SECONDS", "60"))

SERVER_NAME = "dataops-knowledge-hub"
SERVER_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_TOOLS: list[Tool] = [
    Tool(
        name="query_knowledge_hub",
        description=(
            "Query the DataOps Knowledge Hub — an enterprise RAG system that searches "
            "across 3 data stores: PostgreSQL (factual/numerical data about customers, "
            "orders, products), Qdrant (policies, SLAs, runbooks, incident logs), and "
            "Neo4j (pipeline lineage, table dependencies, team ownership). The system "
            "automatically routes your question to the appropriate engine(s) and returns "
            "a synthesized answer with sources and recommendations."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Natural language question about the data platform.",
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["ledger", "memory", "brain"]},
                    "description": (
                        "Optional: restrict search to specific engines. Omit to search all."
                    ),
                },
            },
            "required": ["question"],
        },
    ),
    Tool(
        name="check_platform_health",
        description=(
            "Check the health status of all services in the DataOps Knowledge Hub: "
            "PostgreSQL, Qdrant, Neo4j, MongoDB, and SeaweedFS. Returns the status of "
            "each service and overall platform health."
        ),
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="trigger_ingestion",
        description=(
            "Trigger a re-ingestion of all data sources (SeaweedFS documents + MongoDB "
            "logs) into the Memory engine (Qdrant). Use this after new documents have "
            "been added or when you want to refresh the search index."
        ),
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
]


# ---------------------------------------------------------------------------
# Response formatters — produce human-readable text for agents
# ---------------------------------------------------------------------------

def _format_query_response(data: dict[str, Any]) -> str:
    parts: list[str] = []
    parts.append(f"## Answer\n\n{data.get('answer', '(no answer)')}\n")

    rec = data.get("recommendation")
    if rec:
        parts.append(f"## Recommendation\n\n{rec}\n")

    sub_qs = data.get("sub_questions") or []
    if sub_qs:
        parts.append("## Sub-questions decomposed\n")
        for sq in sub_qs:
            parts.append(f"- {sq}")
        parts.append("")

    parts.append("## Sources consulted\n")
    for src in data.get("sources_consulted", []) or []:
        name = src.get("source", "?")
        store = src.get("data_store", "?")
        summary = src.get("result_summary", "")
        query_used = src.get("query_used", "")
        confidence = src.get("confidence")
        conf_s = f" (confidence: {confidence:.2f})" if isinstance(confidence, (int, float)) else ""
        parts.append(f"- **{name}** ({store}){conf_s}: {summary}")
        if query_used:
            parts.append(f"  - Query: `{query_used}`")
    parts.append("")

    elapsed = data.get("processing_time_ms")
    if isinstance(elapsed, (int, float)):
        parts.append(f"_Processing time: {elapsed:.0f}ms_")

    return "\n".join(parts).rstrip() + "\n"


def _format_health_response(data: dict[str, Any]) -> str:
    parts = [f"## Platform health: {data.get('status', 'unknown').upper()}\n"]
    parts.append("| Service | Status |")
    parts.append("|---|---|")
    for name, status in (data.get("services") or {}).items():
        emoji = {"healthy": "✓", "degraded": "~", "unhealthy": "✗"}.get(status, "?")
        parts.append(f"| {name} | {emoji} {status} |")
    parts.append("")
    uptime = data.get("uptime_seconds")
    if isinstance(uptime, (int, float)):
        parts.append(f"_Uptime: {uptime:.1f}s — version {data.get('version', '?')}_")
    return "\n".join(parts).rstrip() + "\n"


def _format_ingest_response(data: dict[str, Any]) -> str:
    parts = ["## Ingestion triggered\n"]
    parts.append(f"- Status: **{data.get('status', 'unknown')}**")
    if "job_id" in data:
        parts.append(f"- Job ID: `{data['job_id']}`")
    if data.get("message"):
        parts.append(f"- {data['message']}")
    parts.append("")
    parts.append("_Poll GET /api/v1/ingest/status for progress._")
    return "\n".join(parts).rstrip() + "\n"


def _format_http_error(label: str, exc: Exception) -> str:
    return (
        f"## {label} failed\n\n"
        f"The Knowledge Hub API at `{API_BASE_URL}` did not respond as expected.\n\n"
        f"Error: `{type(exc).__name__}: {exc}`\n\n"
        "Check that the FastAPI server is running (`make serve`) and reachable.\n"
    )


# ---------------------------------------------------------------------------
# Tool dispatchers
# ---------------------------------------------------------------------------

async def _call_query(client: httpx.AsyncClient, arguments: dict[str, Any]) -> str:
    if not arguments.get("question", "").strip():
        return "## Error\n\n`question` is required and must not be empty.\n"
    payload = {"question": arguments["question"]}
    if arguments.get("sources"):
        payload["sources"] = arguments["sources"]
    try:
        response = await client.post(f"{API_BASE_URL}/api/v1/query", json=payload)
        response.raise_for_status()
        return _format_query_response(response.json())
    except httpx.HTTPError as exc:
        return _format_http_error("Knowledge Hub query", exc)


async def _call_health(client: httpx.AsyncClient) -> str:
    try:
        response = await client.get(f"{API_BASE_URL}/health")
        response.raise_for_status()
        return _format_health_response(response.json())
    except httpx.HTTPError as exc:
        return _format_http_error("Health check", exc)


async def _call_ingest(client: httpx.AsyncClient) -> str:
    try:
        response = await client.post(f"{API_BASE_URL}/api/v1/ingest")
        response.raise_for_status()
        return _format_ingest_response(response.json())
    except httpx.HTTPError as exc:
        return _format_http_error("Ingestion trigger", exc)


# ---------------------------------------------------------------------------
# Server wiring
# ---------------------------------------------------------------------------

def create_server() -> Server:
    """Construct the MCP Server with handlers registered."""
    server = Server(SERVER_NAME)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return _TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        log.info("tool call: %s args=%s", name, arguments)
        async with httpx.AsyncClient(timeout=API_TIMEOUT_SECONDS) as client:
            if name == "query_knowledge_hub":
                text = await _call_query(client, arguments or {})
            elif name == "check_platform_health":
                text = await _call_health(client)
            elif name == "trigger_ingestion":
                text = await _call_ingest(client)
            else:
                text = f"## Unknown tool\n\nNo such tool: `{name}`.\n"
        return [TextContent(type="text", text=text)]

    return server


async def run_server() -> None:
    """Run the MCP server over stdio until the peer disconnects."""
    log.info(
        "Starting %s v%s — API base URL: %s (timeout %.1fs)",
        SERVER_NAME,
        SERVER_VERSION,
        API_BASE_URL,
        API_TIMEOUT_SECONDS,
    )
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
