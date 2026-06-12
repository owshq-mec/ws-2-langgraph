# Prompt 10 — Build FastAPI Serving Layer

## Context

The full RAG engine is operational:
- Ingestion pipeline indexes documents into Qdrant
- 3 query engines (Ledger, Memory, Brain) work independently
- RouterEngine orchestrates classification, parallel execution, and synthesis

Now we wrap everything in a **FastAPI application** — the production-grade HTTP interface that exposes the Knowledge Hub to the world.

## Objective

Create a FastAPI application with proper endpoints, middleware, error handling, and documentation that serves the RouterEngine as a REST API.

## Files to Create

### 1. `src/api/__init__.py`

Export the FastAPI app instance.

### 2. `src/api/app.py`

The main FastAPI application factory:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
```

**Requirements:**

- **Lifespan handler** (`@asynccontextmanager`): Initialize the `RouterEngine` once at startup (expensive — creates DB connections, loads vector store). Store it in `app.state.router`.
- **CORS middleware**: Allow all origins for development (restrict in production).
- **Metadata**: title="DataOps Knowledge Hub", version="1.0.0", description with the architecture summary.
- **Include routers** from `src/api/routes/`

### 3. `src/api/routes/__init__.py`

Export all route modules.

### 4. `src/api/routes/query.py`

The main query endpoint:

```python
from fastapi import APIRouter, HTTPException, Request
from src.schemas.api import QueryRequest, QueryResponse, SourceDetail
import time

router = APIRouter(prefix="/api/v1", tags=["query"])

@router.post("/query", response_model=QueryResponse)
async def query_knowledge_hub(request: QueryRequest, req: Request):
    """
    Query the DataOps Knowledge Hub.
    
    The system automatically routes your question to the appropriate engine(s):
    - **Ledger** (PostgreSQL): factual/numerical questions
    - **Memory** (Qdrant): policies, procedures, historical events
    - **Brain** (Neo4j): relationships, dependencies, lineage
    
    Complex questions are decomposed into sub-questions and executed in parallel.
    """
    start = time.perf_counter()
    
    router_engine = req.app.state.router
    
    synthesized, source_details = await router_engine.query(
        question=request.question,
        sources=request.sources
    )
    
    elapsed_ms = (time.perf_counter() - start) * 1000
    
    return QueryResponse(
        question=request.question,
        answer=synthesized.answer,
        sub_questions=synthesized.sub_questions,
        sources_consulted=source_details,
        recommendation=synthesized.recommendation,
        processing_time_ms=round(elapsed_ms, 2),
    )
```

### 5. `src/api/routes/health.py`

Health check endpoint that verifies all services:

```python
from fastapi import APIRouter
from src.schemas.api import HealthResponse
import time

router = APIRouter(tags=["health"])

@router.get("/health", response_model=HealthResponse)
async def health_check(req: Request):
    """Check the health of all connected services."""
    # Check each service connectivity:
    # - PostgreSQL: attempt a simple SELECT 1
    # - Qdrant: GET /healthz
    # - Neo4j: RETURN 1 via bolt
    # - MongoDB: ping
    # - SeaweedFS: GET /cluster/status
    ...
```

**Requirements:**
- Check each service with a 5-second timeout
- Return status per service: "healthy", "unhealthy", or "degraded"
- Overall status: "healthy" only if all critical services (postgres, qdrant, neo4j) are up
- Include `uptime_seconds` (time since app started)
- Include `version` from app metadata

### 6. `src/api/routes/ingest.py`

Trigger ingestion on demand:

```python
from fastapi import APIRouter, BackgroundTasks

router = APIRouter(prefix="/api/v1", tags=["ingestion"])

@router.post("/ingest")
async def trigger_ingestion(background_tasks: BackgroundTasks):
    """
    Trigger a re-ingestion of all data sources into the Memory engine.
    Runs in the background — returns immediately with a job ID.
    """
    # Run ingestion as a background task
    # Return: {"status": "ingestion_started", "message": "..."}
```

### 7. `src/api/main.py`

Entry point for running the server:

```python
import uvicorn
from src.api.app import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # dev mode
        log_level="info",
    )
```

## Additional Requirements

### Error Handling

Create a global exception handler:
- `HTTPException` → standard FastAPI handling
- `asyncio.TimeoutError` → 504 Gateway Timeout with message
- `Exception` (catch-all) → 500 with generic message (don't leak internals)

### Request Logging

Add a middleware that logs:
- Request method + path
- Response status code
- Processing time in ms
- Format: `INFO: POST /api/v1/query → 200 (1234.56ms)`

### OpenAPI Documentation

The auto-generated Swagger UI at `/docs` should be clean and usable:
- All endpoints have descriptions
- All request/response models have examples
- Tags group endpoints logically

Add example values to the schemas for better Swagger UX:

```python
class QueryRequest(BaseModel):
    question: str = Field(
        description="...",
        json_schema_extra={"examples": ["How many enterprise customers do we have?"]}
    )
```

### Docker Compose Update

Add the `app` service to `docker-compose.yml`:

```yaml
  app:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      mongo:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      neo4j:
        condition: service_healthy
    networks:
      - dataops-network
    restart: unless-stopped
```

### Dockerfile (project root)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system deps for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Makefile Update

```makefile
serve:
	uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

query:
	@read -p "Question: " q; \
	curl -s -X POST http://localhost:8000/api/v1/query \
		-H "Content-Type: application/json" \
		-d "{\"question\": \"$$q\"}" | python -m json.tool
```

## Validation

After execution, verify:
- [ ] `make serve` starts the server on port 8000
- [ ] `curl http://localhost:8000/health` returns healthy status for all services
- [ ] `curl http://localhost:8000/docs` shows Swagger UI with all endpoints
- [ ] POST to `/api/v1/query` with `{"question": "How many customers?"}` returns valid `QueryResponse`
- [ ] Response includes `processing_time_ms`, `sub_questions`, `sources_consulted`
- [ ] Each `SourceDetail` in the response shows the actual query used (SQL/Cypher/vector)
- [ ] `/api/v1/ingest` triggers background ingestion and returns immediately
- [ ] Error handling: invalid JSON body returns 422, timeout returns 504
- [ ] Request logging shows in console with timing
