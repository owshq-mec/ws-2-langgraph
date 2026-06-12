# Prompt 11 — Build MCP Server

## Context

The FastAPI application is serving the Knowledge Hub at `http://localhost:8000`. Any HTTP client can query it. But we want something more powerful: we want **AI Agents** (like Claude Code) to consume this system as a **tool** — natively, without writing curl commands.

This is where the **Model Context Protocol (MCP)** enters. MCP is the standard protocol for exposing tools to AI agents. By wrapping our API as an MCP server, any MCP-compatible agent can discover and use our Knowledge Hub as a first-class tool.

## What is MCP?

MCP (Model Context Protocol) is a JSON-RPC 2.0 based protocol that allows AI agents to:
1. **Discover** available tools (list tools with descriptions and input schemas)
2. **Call** tools (send structured input, receive structured output)
3. **Use resources** (read data exposed by the server)

Transport options: `stdio` (for local agents like Claude Code) or `SSE/HTTP` (for remote agents).

## Objective

Create an MCP server that exposes the DataOps Knowledge Hub as tools that any MCP-compatible agent can consume. The server wraps the FastAPI endpoints as MCP tools.

## Files to Create

### 1. `src/mcp/server.py`

The MCP server implementation using the `mcp` Python SDK:

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import json
import httpx
```

**Tools to expose:**

#### Tool 1: `query_knowledge_hub`

```python
Tool(
    name="query_knowledge_hub",
    description=(
        "Query the DataOps Knowledge Hub — an enterprise RAG system that searches across "
        "3 data stores: PostgreSQL (factual/numerical data about customers, orders, products), "
        "Qdrant (policies, SLAs, runbooks, incident logs), and Neo4j (pipeline lineage, "
        "table dependencies, team ownership). "
        "The system automatically routes your question to the appropriate engine(s) and "
        "returns a synthesized answer with sources and recommendations."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Natural language question about the data platform"
            },
            "sources": {
                "type": "array",
                "items": {"type": "string", "enum": ["ledger", "memory", "brain"]},
                "description": "Optional: restrict search to specific engines. Omit to search all."
            }
        },
        "required": ["question"]
    }
)
```

#### Tool 2: `check_platform_health`

```python
Tool(
    name="check_platform_health",
    description=(
        "Check the health status of all services in the DataOps Knowledge Hub: "
        "PostgreSQL, Qdrant, Neo4j, MongoDB, and SeaweedFS. "
        "Returns the status of each service and overall platform health."
    ),
    inputSchema={
        "type": "object",
        "properties": {},
        "required": []
    }
)
```

#### Tool 3: `trigger_ingestion`

```python
Tool(
    name="trigger_ingestion",
    description=(
        "Trigger a re-ingestion of all data sources (SeaweedFS documents + MongoDB logs) "
        "into the Memory engine (Qdrant). Use this after new documents have been added "
        "or when you want to refresh the search index."
    ),
    inputSchema={
        "type": "object",
        "properties": {},
        "required": []
    }
)
```

**Implementation details:**

- The MCP server communicates via **stdio** (stdin/stdout) for local use with Claude Code
- Each tool handler makes an HTTP request to the FastAPI app (which must be running)
- The `API_BASE_URL` is configurable via environment variable (default: `http://localhost:8000`)
- Format responses as readable text (not raw JSON) for better agent consumption

**Tool handler example:**

```python
@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "query_knowledge_hub":
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{API_BASE_URL}/api/v1/query",
                json=arguments
            )
            data = response.json()

            # Format as readable text for the agent
            text = f"## Answer\n\n{data['answer']}\n\n"
            if data.get('recommendation'):
                text += f"## Recommendation\n\n{data['recommendation']}\n\n"
            text += "## Sources Consulted\n\n"
            for source in data['sources_consulted']:
                text += f"- **{source['source']}** ({source['data_store']}): {source['result_summary']}\n"
                text += f"  Query: `{source['query_used']}`\n"
            text += f"\n_Processing time: {data['processing_time_ms']:.0f}ms_"

            return [TextContent(type="text", text=text)]
```

### 2. `src/mcp/__init__.py`

Export the server.

### 3. `src/mcp/run.py`

Entry point for running the MCP server:

```python
import asyncio
from src.mcp.server import create_server, run_server

if __name__ == "__main__":
    asyncio.run(run_server())
```

### 4. Update `pyproject.toml`

Add the MCP SDK dependency:
```toml
"mcp>=1.0",
"httpx>=0.27",
```

Add a script entry point:
```toml
[project.scripts]
dataops-mcp = "src.mcp.run:main"
```

### 5. Claude Code MCP Configuration

Create a file showing how to configure Claude Code to use this MCP server:

`mcp-config.json` (at project root, for reference):

```json
{
  "mcpServers": {
    "dataops-knowledge-hub": {
      "command": "python",
      "args": ["-m", "src.mcp.run"],
      "cwd": "/path/to/dataops-knowledge-hub",
      "env": {
        "API_BASE_URL": "http://localhost:8000"
      }
    }
  }
}
```

For production (Railway deployed):
```json
{
  "mcpServers": {
    "dataops-knowledge-hub": {
      "command": "python",
      "args": ["-m", "src.mcp.run"],
      "cwd": "/path/to/dataops-knowledge-hub",
      "env": {
        "API_BASE_URL": "https://your-app.railway.app"
      }
    }
  }
}
```

## The Grand Finale Demo

After the MCP server is configured, the instructor opens Claude Code and demonstrates:

```
$ claude

> Use the dataops-knowledge-hub tool to find out which customers are on the enterprise plan,
  what the SLA is for the billing pipeline, and what would happen if the orders table went down.
```

Claude Code will:
1. Discover the `query_knowledge_hub` tool via MCP
2. Call it with the question
3. The MCP server hits the FastAPI → RouterEngine → 3 engines in parallel
4. Returns a synthesized answer with SQL, vector search results, and Cypher traversal
5. Claude Code presents it beautifully in the terminal

**This is the loop closing:** The agent that built the system is now consuming the system.

## Validation

- [ ] `python -m src.mcp.run` starts without errors (waits on stdio)
- [ ] MCP tool list returns 3 tools with correct schemas
- [ ] `query_knowledge_hub` tool returns formatted answer when called
- [ ] `check_platform_health` returns service statuses
- [ ] `trigger_ingestion` returns confirmation
- [ ] Claude Code can discover and use the tools after adding `mcp-config.json` to its settings
- [ ] The full demo works: question → MCP → FastAPI → Router → Engines → Response → Claude Code displays it
