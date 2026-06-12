# Prompt 12 — Build Tests

## Context

The full system is operational:
- Infrastructure running (Postgres, Mongo, Qdrant, Neo4j, SeaweedFS)
- Data Generator populating continuously
- Ingestion Pipeline indexing into Qdrant
- 3 Query Engines (Ledger, Memory, Brain) + Router
- FastAPI serving at port 8000
- MCP Server exposing tools

Now we need **tests** — both unit tests (isolated, no infra needed) and integration tests (require the full stack running).

## Objective

Create a test suite that validates the system works end-to-end and catches regressions.

## Files to Create

### 1. `tests/__init__.py`

Empty init.

### 2. `tests/conftest.py`

Shared fixtures for all tests:

```python
import pytest
import asyncio
from src.engines.config import EngineConfig


@pytest.fixture(scope="session")
def event_loop():
    """Use a single event loop for all async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def config():
    """Load config from .env (must exist with valid values)."""
    return EngineConfig()
```

### 3. `tests/unit/test_schemas.py`

Unit tests for Pydantic models (no infra needed):

**Test cases:**
- Valid `QueryRequest` creation with all fields
- Valid `QueryRequest` with only required fields (question)
- Invalid `QueryRequest` (missing question) raises ValidationError
- Valid `QueryResponse` with all source details
- `SourceDetail.confidence` rejects values > 1.0 and < 0.0
- All Enum values are valid (CustomerPlan, OrderStatus, PipelineStatus, Severity)
- `DependencyChain` with empty lists is valid
- `HealthResponse` accepts arbitrary service names in dict

### 4. `tests/unit/test_router_classification.py`

Unit tests for the router's classification logic (mock the LLM):

**Test cases:**
- Question about customers → routes to "ledger"
- Question about SLA → routes to "memory"
- Question about ownership → routes to "brain"
- Complex question → decomposes into 2-3 sub-questions
- Malformed LLM response → falls back to all engines
- `sources` filter bypasses classification entirely

### 5. `tests/integration/test_engines.py`

Integration tests that require the full stack running:

**Test cases:**

```python
@pytest.mark.integration
class TestLedgerEngine:
    async def test_count_query(self, config):
        """Test a simple count query against PostgreSQL."""
        engine = LedgerEngine(config)
        result = await engine.query("How many customers are there?")
        assert isinstance(result, LedgerQueryResult)
        assert "SELECT" in result.sql_query_executed.upper()
        assert result.row_count >= 0

    async def test_aggregation_query(self, config):
        """Test an aggregation query."""
        engine = LedgerEngine(config)
        result = await engine.query("What is the total revenue from completed orders?")
        assert isinstance(result, LedgerQueryResult)
        assert "completed" in result.sql_query_executed.lower()


@pytest.mark.integration
class TestMemoryEngine:
    async def test_policy_query(self, config):
        """Test retrieval of policy documents."""
        engine = MemoryEngine(config)
        result = await engine.query("What is the data retention policy for PII?")
        assert isinstance(result, MemoryQueryResult)
        assert result.confidence > 0.0
        assert len(result.sources) > 0

    async def test_event_query(self, config):
        """Test retrieval of event logs."""
        engine = MemoryEngine(config)
        result = await engine.query("What pipeline failures happened recently?")
        assert isinstance(result, MemoryQueryResult)


@pytest.mark.integration
class TestBrainEngine:
    async def test_ownership_query(self, config):
        """Test graph traversal for ownership."""
        engine = BrainEngine(config)
        result = await engine.query("What pipelines does team-billing own?")
        assert isinstance(result, BrainQueryResult)
        assert "MATCH" in result.cypher_query_executed.upper()

    async def test_dependency_query(self, config):
        """Test dependency chain population."""
        engine = BrainEngine(config)
        result = await engine.query("What would be impacted if the orders table goes down?")
        assert isinstance(result, BrainQueryResult)
        assert result.dependency_chain is not None
```

### 6. `tests/integration/test_router.py`

Integration test for the full router flow:

```python
@pytest.mark.integration
class TestRouterEngine:
    async def test_single_engine_routing(self, config):
        """Simple question routes to one engine."""
        router = RouterEngine(config)
        response, sources = await router.query("How many enterprise customers?")
        assert isinstance(response, SynthesizedResponse)
        assert len(sources) == 1
        assert sources[0].source == "ledger"

    async def test_multi_engine_routing(self, config):
        """Complex question decomposes and routes to multiple engines."""
        router = RouterEngine(config)
        response, sources = await router.query(
            "What are the top customers by revenue, what's the SLA for billing, "
            "and what depends on the orders table?"
        )
        assert isinstance(response, SynthesizedResponse)
        assert len(sources) >= 2
        assert len(response.sub_questions) >= 2

    async def test_forced_routing(self, config):
        """Sources filter bypasses classification."""
        router = RouterEngine(config)
        response, sources = await router.query(
            "Tell me everything about billing",
            sources=["ledger", "brain"]
        )
        assert all(s.source in ["ledger", "brain"] for s in sources)
```

### 7. `tests/integration/test_api.py`

Integration test for the FastAPI endpoints:

```python
import httpx
import pytest

BASE_URL = "http://localhost:8000"


@pytest.mark.integration
class TestAPI:
    async def test_health_endpoint(self):
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{BASE_URL}/health")
            assert r.status_code == 200
            data = r.json()
            assert data["status"] in ["healthy", "degraded"]

    async def test_query_endpoint(self):
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{BASE_URL}/api/v1/query",
                json={"question": "How many customers do we have?"}
            )
            assert r.status_code == 200
            data = r.json()
            assert "answer" in data
            assert "sources_consulted" in data
            assert data["processing_time_ms"] > 0

    async def test_query_with_sources_filter(self):
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{BASE_URL}/api/v1/query",
                json={
                    "question": "Who owns the billing pipeline?",
                    "sources": ["brain"]
                }
            )
            assert r.status_code == 200
            data = r.json()
            assert all(s["source"] == "brain" for s in data["sources_consulted"])

    async def test_invalid_request(self):
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{BASE_URL}/api/v1/query",
                json={"wrong_field": "test"}
            )
            assert r.status_code == 422

    async def test_ingest_endpoint(self):
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{BASE_URL}/api/v1/ingest")
            assert r.status_code == 202
```

### 8. `pytest.ini` (or in `pyproject.toml`)

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "integration: requires full infrastructure stack running",
]
testpaths = ["tests"]
```

### 9. Makefile update

```makefile
test:
	pytest tests/unit -v

test-integration:
	pytest tests/integration -v --timeout=120

test-all:
	pytest tests/ -v --timeout=120
```

## Validation

- [ ] `make test` runs unit tests without any infrastructure (all pass)
- [ ] `make test-integration` runs with full stack up (all pass)
- [ ] No test takes longer than 60 seconds individually
- [ ] Unit tests mock external dependencies (LLM, databases)
- [ ] Integration tests use real connections and validate real responses
- [ ] All assertions check Pydantic model types (not just dict shapes)
