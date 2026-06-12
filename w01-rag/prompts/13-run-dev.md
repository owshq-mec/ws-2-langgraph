# Prompt 13 — Run Dev: Full Local Validation

## Context

All code is written (prompts 1-12 complete). The system has never been run end-to-end. We need to:
1. Start the full stack
2. Verify all services are healthy
3. Run the data generator and confirm data is flowing
4. Run the ingestion pipeline
5. Test each engine individually
6. Test the router with cross-domain queries
7. Test the FastAPI endpoints
8. Run integration tests
9. Configure and test the MCP server locally
10. Fix any bugs discovered during this process

## Objective

Execute a **full local validation** — start everything, run everything, fix everything. The system must be 100% functional before we consider production deployment.

## Execution Steps

### Step 1: Start Infrastructure

```bash
# Ensure .env exists
cp .env.example .env
# Add your OPENAI_API_KEY to .env

# Start all services
make up

# Wait for health checks (all services must be healthy)
docker compose ps

# Expected: all services "healthy" status
# If any service is "starting" or "unhealthy", wait and check logs:
# docker compose logs <service-name>
```

**Validation:**
- [ ] `docker compose ps` shows all services as "healthy"
- [ ] Postgres: `docker compose exec postgres pg_isready` → "accepting connections"
- [ ] MongoDB: `docker compose exec mongo mongosh --eval "db.runCommand('ping')"` → `{ ok: 1 }`
- [ ] Qdrant: `curl http://localhost:6333/healthz` → "ok"
- [ ] Neo4j: `curl http://localhost:7474` → responds
- [ ] SeaweedFS: `curl http://localhost:9333/cluster/status` → JSON response

### Step 2: Verify Init Scripts Ran

```bash
# Check Postgres tables exist
docker compose exec postgres psql -U dataops -d dataops -c "\dt"
# Expected: customers, orders, products tables

# Check Neo4j nodes exist
docker compose exec neo4j cypher-shell -u neo4j -p dataops123 \
  "MATCH (n) RETURN labels(n) AS type, count(n) AS count"
# Expected: Team, Table, Pipeline, Dashboard nodes

# Check SeaweedFS bucket and seed docs
curl -s http://localhost:8333/dataops-docs/?list | head -20
# Expected: retention-policy.md, sla-definitions.md, runbook-billing.md, data-dictionary.csv
```

**Validation:**
- [ ] 3 Postgres tables with correct schema
- [ ] Neo4j has nodes (Teams, Tables, Pipelines, Dashboards) and relationships
- [ ] SeaweedFS bucket `dataops-docs` contains 4 seed documents

### Step 3: Verify Data Generator

```bash
# Check generator is running
docker compose logs data-generator --tail 20

# Verify data is flowing into Postgres
docker compose exec postgres psql -U dataops -d dataops -c \
  "SELECT 'customers' AS tbl, count(*) FROM customers UNION ALL
   SELECT 'orders', count(*) FROM orders UNION ALL
   SELECT 'products', count(*) FROM products;"

# Verify data is flowing into MongoDB
docker compose exec mongo mongosh dataops --eval \
  "print('event_logs:', db.event_logs.countDocuments()); print('user_activity:', db.user_activity.countDocuments());"

# Wait 60 seconds and check counts again — they should increase
sleep 60
docker compose exec postgres psql -U dataops -d dataops -c "SELECT count(*) FROM orders;"
```

**Validation:**
- [ ] Data generator logs show successful cycles (no errors)
- [ ] Postgres has customers, orders, and products with growing counts
- [ ] MongoDB has event_logs and user_activity documents
- [ ] Counts increase over time (generator is running continuously)

### Step 4: Run Ingestion Pipeline

```bash
# Run the ingestion pipeline
make ingest

# Expected output:
# - Loading documents from SeaweedFS...
# - Loading documents from MongoDB...
# - Running ingestion pipeline...
# - Indexed N nodes into Qdrant

# Verify Qdrant has vectors
curl -s http://localhost:6333/collections/dataops_memory/points/count | python3 -m json.tool
# Expected: count > 0
```

**Validation:**
- [ ] `make ingest` completes without errors
- [ ] Qdrant collection `dataops_memory` has indexed points (count > 0)
- [ ] No OpenAI API errors (check API key is valid)

### Step 5: Test Each Engine Individually

```bash
# Start a Python REPL or create a test script
python3 -c "
import asyncio
from src.engines.config import EngineConfig
from src.engines.ledger import LedgerEngine
from src.engines.memory import MemoryEngine
from src.engines.brain import BrainEngine

async def test():
    cfg = EngineConfig()
    
    # Test Ledger (Text-to-SQL)
    print('=== LEDGER ===')
    ledger = LedgerEngine(cfg)
    result = await ledger.query('How many enterprise customers do we have?')
    print(f'SQL: {result.sql_query_executed}')
    print(f'Summary: {result.summary}')
    print(f'Rows: {result.row_count}')
    print()
    
    # Test Memory (Vector Search)
    print('=== MEMORY ===')
    memory = MemoryEngine(cfg)
    result = await memory.query('What is the data retention policy for PII?')
    print(f'Summary: {result.summary}')
    print(f'Sources: {result.sources}')
    print(f'Confidence: {result.confidence}')
    print()
    
    # Test Brain (Graph Traversal)
    print('=== BRAIN ===')
    brain = BrainEngine(cfg)
    result = await brain.query('What pipelines does team-billing own?')
    print(f'Cypher: {result.cypher_query_executed}')
    print(f'Summary: {result.summary}')
    print(f'Nodes: {result.nodes_traversed}')
    brain.close()

asyncio.run(test())
"
```

**Validation:**
- [ ] Ledger returns valid SQL + results from Postgres
- [ ] Memory returns relevant chunks with confidence > 0
- [ ] Brain returns valid Cypher + graph traversal results
- [ ] All outputs are Pydantic-validated (no raw strings)

### Step 6: Test Router (Cross-Domain)

```bash
python3 -c "
import asyncio
from src.engines.config import EngineConfig
from src.engines.router import RouterEngine

async def test():
    cfg = EngineConfig()
    router = RouterEngine(cfg)
    
    # Simple query (single engine)
    print('=== SINGLE ENGINE ===')
    response, sources = await router.query('How many customers do we have?')
    print(f'Answer: {response.answer}')
    print(f'Sources: {[s.source for s in sources]}')
    print()
    
    # Complex query (multiple engines)
    print('=== CROSS-DOMAIN ===')
    response, sources = await router.query(
        'What are the top customers by revenue, what is the SLA for the billing pipeline, '
        'and what would be impacted if the orders table goes down?'
    )
    print(f'Sub-questions: {response.sub_questions}')
    print(f'Sources: {[s.source for s in sources]}')
    print(f'Answer: {response.answer[:200]}...')
    print(f'Confidence: {response.confidence}')
    print(f'Recommendation: {response.recommendation}')
    print()
    
    # Forced routing
    print('=== FORCED ROUTING ===')
    response, sources = await router.query(
        'Tell me about billing',
        sources=['ledger', 'brain']
    )
    print(f'Sources used: {[s.source for s in sources]}')
    
    router.brain.close()

asyncio.run(test())
"
```

**Validation:**
- [ ] Single engine query routes correctly (e.g., count → ledger)
- [ ] Cross-domain query decomposes into 3 sub-questions
- [ ] All 3 engines respond (ledger + memory + brain)
- [ ] Synthesized answer combines all sources coherently
- [ ] Forced routing respects the `sources` filter
- [ ] Response time < 30 seconds for cross-domain

### Step 7: Test FastAPI

```bash
# Start the API server
make serve &
# Wait for startup
sleep 5

# Test health endpoint
echo "=== HEALTH ==="
curl -s http://localhost:8000/health | python3 -m json.tool

# Test query endpoint (simple)
echo "=== SIMPLE QUERY ==="
curl -s -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How many enterprise customers do we have?"}' | python3 -m json.tool

# Test query endpoint (cross-domain)
echo "=== CROSS-DOMAIN QUERY ==="
curl -s -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the top customers by revenue, what is the data retention policy, and what depends on the orders table?"}' | python3 -m json.tool

# Test query with source filter
echo "=== FILTERED QUERY ==="
curl -s -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Who owns the billing pipeline?", "sources": ["brain"]}' | python3 -m json.tool

# Test Swagger UI
echo "=== SWAGGER ==="
echo "Open http://localhost:8000/docs in browser"

# Test ingest endpoint
echo "=== INGEST ==="
curl -s -X POST http://localhost:8000/api/v1/ingest | python3 -m json.tool

# Kill background server
kill %1
```

**Validation:**
- [ ] `/health` returns all services healthy
- [ ] `/api/v1/query` returns structured JSON with answer, sources, processing_time_ms
- [ ] Cross-domain query shows multiple sources_consulted
- [ ] Source filter works (only brain sources in filtered query)
- [ ] `/docs` shows Swagger UI with all endpoints documented
- [ ] `/api/v1/ingest` returns 202 with job_id
- [ ] No 500 errors

### Step 8: Run Integration Tests

```bash
# Run full test suite (unit + integration)
make test-all

# Expected: all tests pass
# If integration tests fail, check:
# 1. Is the stack running? (docker compose ps)
# 2. Is .env configured? (OPENAI_API_KEY)
# 3. Was ingestion run? (make ingest)
```

**Validation:**
- [ ] `make test` → all unit tests pass
- [ ] `make test-integration` → all integration tests pass
- [ ] `make test-all` → everything green

### Step 9: Test MCP Server Locally

```bash
# Option A: Test via Claude Code
# Add to your Claude Code MCP config (~/.claude/mcp.json or project .mcp.json):
# {
#   "mcpServers": {
#     "dataops-knowledge-hub": {
#       "command": "python",
#       "args": ["-m", "src.mcp.run"],
#       "cwd": "/path/to/dataops-knowledge-hub",
#       "env": {
#         "API_BASE_URL": "http://localhost:8000"
#       }
#     }
#   }
# }

# Option B: Test MCP server directly via stdio
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 -m src.mcp.run

# Option C: Start API + test MCP tool call
make serve &
sleep 5
echo '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"query_knowledge_hub","arguments":{"question":"How many customers?"}}}' | python3 -m src.mcp.run
kill %1
```

**Validation:**
- [ ] MCP server starts without errors
- [ ] `tools/list` returns 3 tools (query_knowledge_hub, check_platform_health, trigger_ingestion)
- [ ] `tools/call` with a query returns a valid response
- [ ] Claude Code can discover and use the MCP tools (if testing via Claude Code)

### Step 10: Fix Any Issues

If any step above fails:
1. Read the error message carefully
2. Check logs: `docker compose logs <service>`
3. Fix the issue in the relevant source file
4. Re-run the failing validation step
5. Continue from where you left off

Common issues:
- **OpenAI rate limit:** Wait and retry, or switch to `gpt-4.1-nano` in .env
- **Neo4j slow start:** Increase `start_period` in docker-compose.yml
- **Qdrant empty:** Re-run `make ingest`
- **Import errors:** Check `pyproject.toml` dependencies are installed
- **Port conflicts:** Check nothing else is using 5432, 27017, 6333, 7687, 9333, 8000

## Success Criteria

The system is ready for production deployment when ALL of the following are true:

- [ ] All 5 infrastructure services healthy
- [ ] Data generator producing data continuously
- [ ] Ingestion pipeline indexes documents into Qdrant
- [ ] All 3 engines respond correctly to queries
- [ ] Router decomposes and routes cross-domain queries
- [ ] FastAPI serves all endpoints without errors
- [ ] MCP server exposes tools correctly
- [ ] All tests pass (unit + integration)
- [ ] No unhandled exceptions in any logs
- [ ] Cross-domain query completes in < 30 seconds
