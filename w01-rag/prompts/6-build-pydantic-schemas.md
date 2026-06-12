# Prompt 06 — Build Pydantic Schemas

## Context

Infrastructure is running and the Data Generator is populating all stores continuously. Before we build the LlamaIndex ingestion and query engines, we need to define the **contracts** — the Pydantic models that govern every input and output in the system.

These schemas serve three purposes:
1. **Domain models** — represent the business entities (customers, orders, events, pipelines)
2. **LLM structured output** — force the LLM to return validated JSON (used as `output_cls` in LlamaIndex)
3. **API contracts** — define what FastAPI accepts and returns

## Objective

Create the Pydantic v2 models that will be used across the entire application: ingestion metadata, query engine responses, and API request/response contracts.

## Files to Create

### 1. `src/schemas/__init__.py`

Export all models for easy importing:
```python
from src.schemas.domain import *
from src.schemas.query import *
from src.schemas.api import *
```

### 2. `src/schemas/domain.py`

Domain models representing the business entities. These are used for structured extraction during ingestion and as output schemas for query engines.

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class CustomerPlan(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class OrderStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PipelineStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    WARNING = "warning"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Customer(BaseModel):
    """A customer entity from the Ledger (PostgreSQL)."""
    id: int
    name: str
    email: str
    plan: CustomerPlan
    company: Optional[str] = None
    created_at: datetime


class Order(BaseModel):
    """An order entity from the Ledger (PostgreSQL)."""
    id: int
    customer_id: int
    product_id: int
    amount: float = Field(description="Order total in BRL")
    quantity: int
    status: OrderStatus
    created_at: datetime


class PipelineEvent(BaseModel):
    """A pipeline execution event from Memory (MongoDB)."""
    pipeline_name: str
    status: PipelineStatus
    error_message: Optional[str] = None
    severity: Severity
    duration_seconds: int
    records_processed: int
    timestamp: datetime


class PipelineNode(BaseModel):
    """A pipeline node from the Brain (Neo4j)."""
    name: str
    schedule: str
    owner: str
    sla_minutes: int


class TableNode(BaseModel):
    """A table node from the Brain (Neo4j)."""
    name: str
    schema_name: str = Field(alias="schema")
    database: str
    row_count: int


class DependencyChain(BaseModel):
    """Represents downstream dependencies of a pipeline or table."""
    source: str = Field(description="The originating pipeline or table name")
    downstream_pipelines: list[str] = Field(default_factory=list)
    downstream_tables: list[str] = Field(default_factory=list)
    downstream_dashboards: list[str] = Field(default_factory=list)
    impacted_teams: list[str] = Field(default_factory=list)
```

### 3. `src/schemas/query.py`

Models used as `output_cls` for LlamaIndex query engines — these force the LLM to return structured, validated responses.

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class LedgerQueryResult(BaseModel):
    """Structured result from a Ledger (Text-to-SQL) query."""
    sql_query_executed: str = Field(description="The SQL query that was generated and executed")
    summary: str = Field(description="Natural language summary of the SQL result")
    row_count: int = Field(description="Number of rows returned")
    data_points: list[dict] = Field(default_factory=list, description="Key data points extracted")


class MemoryQueryResult(BaseModel):
    """Structured result from a Memory (Vector Search) query."""
    summary: str = Field(description="Synthesized answer from retrieved documents")
    sources: list[str] = Field(default_factory=list, description="Source document names/paths")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score of the retrieval")
    relevant_facts: list[str] = Field(default_factory=list, description="Key facts extracted")


class BrainQueryResult(BaseModel):
    """Structured result from a Brain (Graph Traversal) query."""
    cypher_query_executed: str = Field(description="The Cypher query that was generated and executed")
    summary: str = Field(description="Natural language summary of the graph result")
    nodes_traversed: int = Field(description="Number of nodes visited")
    relationships_found: list[str] = Field(default_factory=list, description="Key relationships discovered")
    dependency_chain: Optional[DependencyChain] = None


class SynthesizedResponse(BaseModel):
    """The final synthesized response combining results from multiple engines."""
    answer: str = Field(description="Complete synthesized answer to the user's question")
    sub_questions: list[str] = Field(default_factory=list, description="Sub-questions that were generated")
    sources_consulted: list[str] = Field(description="Which engines were consulted: ledger, memory, brain")
    confidence: float = Field(ge=0.0, le=1.0, description="Overall confidence score")
    recommendation: Optional[str] = Field(None, description="Actionable recommendation if applicable")
```

Note: Import `DependencyChain` from `domain.py`.

### 4. `src/schemas/api.py`

Request and response models for the FastAPI layer.

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class QueryRequest(BaseModel):
    """Request body for POST /query."""
    question: str = Field(description="The natural language question to ask the Knowledge Hub")
    sources: Optional[list[str]] = Field(
        None,
        description="Optionally restrict to specific sources: 'ledger', 'memory', 'brain'. None = all."
    )
    include_metadata: bool = Field(
        default=True,
        description="Whether to include sub-questions, SQL/Cypher queries, and source details"
    )


class SourceDetail(BaseModel):
    """Details about a specific source that was consulted."""
    source: str = Field(description="Engine name: ledger, memory, or brain")
    data_store: str = Field(description="Underlying store: postgresql, qdrant, or neo4j")
    query_used: str = Field(description="The actual query executed (SQL, vector search, or Cypher)")
    result_summary: str = Field(description="Summary of what this source returned")
    confidence: float = Field(ge=0.0, le=1.0)


class QueryResponse(BaseModel):
    """Response body for POST /query."""
    question: str = Field(description="The original question")
    answer: str = Field(description="Synthesized answer combining all sources")
    sub_questions: list[str] = Field(default_factory=list, description="How the question was decomposed")
    sources_consulted: list[SourceDetail] = Field(description="Details per source")
    recommendation: Optional[str] = Field(None, description="Actionable recommendation")
    processing_time_ms: float = Field(description="Total processing time in milliseconds")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HealthResponse(BaseModel):
    """Response body for GET /health."""
    status: str = Field(default="healthy")
    services: dict[str, str] = Field(description="Health status per service: postgres, qdrant, neo4j, seaweedfs")
    uptime_seconds: float
    version: str
```

## Design Principles

1. **Every Field has a `description`** — This is critical because LlamaIndex passes these descriptions to the LLM when generating structured output. Better descriptions = better extraction.

2. **Enums for constrained values** — Plan types, statuses, severities. Prevents hallucinated values.

3. **`Field(ge=0.0, le=1.0)` for confidence** — Pydantic validates at runtime. If the LLM returns 1.5, it fails fast.

4. **Separation of concerns** — `domain.py` (business entities), `query.py` (LLM output contracts), `api.py` (HTTP contracts). Each has a clear owner.

5. **Composability** — `QueryResponse` contains `list[SourceDetail]`. `BrainQueryResult` contains `Optional[DependencyChain]`. Models compose naturally.

## Validation

After execution, verify:
- [ ] All files pass `python -c "from src.schemas import *"` without import errors
- [ ] All models have proper type hints and Field descriptions
- [ ] Enums are used for constrained values (no raw strings for status/plan/severity)
- [ ] `QueryResponse` includes all fields needed for the workshop's "WOW moment" (sub_questions, sources_consulted with query details, recommendation)
- [ ] No circular imports between domain.py, query.py, and api.py
