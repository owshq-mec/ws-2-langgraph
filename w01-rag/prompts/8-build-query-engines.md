# Prompt 08 — Build Query Engines

## Context

The ingestion pipeline is complete — Qdrant has indexed documents from SeaweedFS and MongoDB. PostgreSQL has structured data (customers, orders, products). Neo4j has the graph (pipelines, tables, dashboards, teams, relationships).

Now we build the **3 query engines** — each specialized for its data store and retrieval pattern:

| Engine | Data Store | Retrieval Method | LlamaIndex Component |
|--------|-----------|-----------------|---------------------|
| **Ledger** | PostgreSQL | Text-to-SQL | `NLSQLTableQueryEngine` |
| **Memory** | Qdrant | Vector Similarity Search | `VectorStoreIndex` + `as_query_engine()` |
| **Brain** | Neo4j | Graph Traversal (Cypher) | `KnowledgeGraphQueryEngine` or `PropertyGraphIndex` |

Each engine must return a **Pydantic-validated response** using the schemas from `src/schemas/query.py`.

## Objective

Create 3 independent query engines, each in its own file, that can be tested in isolation before being composed by the Router (next prompt).

## Files to Create

### 1. `src/engines/__init__.py`

Export all engines:
```python
from src.engines.ledger import LedgerEngine
from src.engines.memory import MemoryEngine
from src.engines.brain import BrainEngine
```

### 2. `src/engines/config.py`

Shared configuration for all engines:

```python
from pydantic_settings import BaseSettings


class EngineConfig(BaseSettings):
    # LLM
    openai_api_key: str
    llm_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"

    # PostgreSQL (Ledger)
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "dataops"
    postgres_user: str = "dataops"
    postgres_password: str = "dataops123"

    # Qdrant (Memory)
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "dataops-memory"

    # Neo4j (Brain)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "dataops123"

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def postgres_connection_string(self) -> str:
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
```

### 3. `src/engines/ledger.py` — Text-to-SQL Engine

**Purpose:** Answers factual/numerical questions by generating SQL and executing it against PostgreSQL.

**Implementation:**

```python
from llama_index.core import SQLDatabase
from llama_index.core.query_engine import NLSQLTableQueryEngine
from llama_index.llms.openai import OpenAI
from sqlalchemy import create_engine
```

**Requirements:**
- Connect to PostgreSQL via SQLAlchemy
- Create `SQLDatabase` with explicit `include_tables=["customers", "orders", "products"]`
- Build `NLSQLTableQueryEngine` with:
  - `sql_database`: the SQLDatabase instance
  - `tables`: ["customers", "orders", "products"]
  - `llm`: OpenAI(model=config.llm_model)
  - `synthesize_response`: True (generate natural language from SQL results)
- Wrap in a class `LedgerEngine` with method:
  ```python
  async def query(self, question: str) -> LedgerQueryResult:
  ```
- The method should:
  1. Execute the query engine
  2. Extract the SQL that was generated (from `response.metadata["sql_query"]`)
  3. Build and return a `LedgerQueryResult` (from schemas/query.py)
- Add table descriptions to help the LLM generate better SQL:
  - `customers`: "Customer records with name, email, subscription plan (free/pro/enterprise), and company. Use for questions about customer counts, segments, plans."
  - `orders`: "Order transactions with amount in BRL, quantity, status (pending/completed/failed/refunded), and timestamps. Use for revenue, sales volume, order status questions."
  - `products`: "Product catalog with name, category, price, and SKU. Use for product-related questions."

### 4. `src/engines/memory.py` — Vector Search Engine

**Purpose:** Answers questions about policies, procedures, incidents, and historical events by searching the Qdrant vector index.

**Implementation:**

```python
from llama_index.core import VectorStoreIndex
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from qdrant_client import QdrantClient
```

**Requirements:**
- Connect to Qdrant, load existing collection `dataops-memory`
- Build `VectorStoreIndex.from_vector_store(vector_store)` — do NOT re-ingest, just connect to existing data
- Create query engine with:
  - `similarity_top_k=5` (retrieve top 5 most relevant chunks)
  - `response_mode="tree_summarize"` (synthesize across multiple chunks)
  - `llm`: OpenAI(model=config.llm_model)
- Wrap in a class `MemoryEngine` with method:
  ```python
  async def query(self, question: str) -> MemoryQueryResult:
  ```
- The method should:
  1. Execute the query engine
  2. Extract source nodes (document names, scores)
  3. Build and return a `MemoryQueryResult` with sources, confidence (average score), and relevant_facts

### 5. `src/engines/brain.py` — Graph Traversal Engine

**Purpose:** Answers questions about relationships, dependencies, lineage, and ownership by traversing the Neo4j graph.

**Implementation:**

Use LlamaIndex's graph query capabilities. Two approaches (pick the one that works best with current LlamaIndex version):

**Option A — `KnowledgeGraphQueryEngine` (if available):**
```python
from llama_index.core.query_engine import KnowledgeGraphQueryEngine
```

**Option B — Custom Cypher generation (more control):**
- Use the LLM to generate a Cypher query from the natural language question
- Execute the Cypher against Neo4j via the `neo4j` Python driver
- Use the LLM to synthesize the results into natural language

**Requirements regardless of approach:**
- Provide the graph schema to the LLM as context:
  ```
  Nodes: Team, Pipeline, Table, Dashboard
  Relationships: OWNS, READS_FROM, WRITES_TO, FEEDS, USED_BY
  ```
- Include example Cypher queries in the prompt:
  ```
  "What pipelines does team-billing own?" → MATCH (t:Team {name:'team-billing'})-[:OWNS]->(p:Pipeline) RETURN p.name
  "What happens if orders table goes down?" → MATCH (t:Table {name:'orders'})<-[:READS_FROM|WRITES_TO*1..3]-(downstream) RETURN downstream
  "Show lineage of fact_revenue" → MATCH path=(source)-[:READS_FROM|WRITES_TO|FEEDS*]->(t:Table {name:'fact_revenue'}) RETURN path
  ```
- Wrap in a class `BrainEngine` with method:
  ```python
  async def query(self, question: str) -> BrainQueryResult:
  ```
- The method should:
  1. Generate Cypher from the question (using LLM with schema context)
  2. Execute Cypher against Neo4j
  3. Synthesize results into natural language
  4. Build and return a `BrainQueryResult` with cypher_query_executed, nodes_traversed, relationships_found
  5. If the query involves dependencies, populate the `dependency_chain` field

### Error Handling (all engines):
- If the underlying store is unreachable, raise a descriptive exception (don't silently fail)
- If the LLM generates invalid SQL/Cypher, catch the execution error, log it, and return a result with a helpful error message in the summary field
- Timeout: 30 seconds per query maximum

## Validation

After execution, verify each engine independently:

**Ledger:**
- [ ] `LedgerEngine.query("How many enterprise customers do we have?")` → returns LedgerQueryResult with valid SQL
- [ ] `LedgerEngine.query("Top 5 customers by total order amount")` → returns data_points with names and amounts

**Memory:**
- [ ] `MemoryEngine.query("What is the data retention policy for PII?")` → returns MemoryQueryResult referencing the retention policy doc
- [ ] `MemoryEngine.query("What happened in the last pipeline failure?")` → returns info from event_logs

**Brain:**
- [ ] `BrainEngine.query("What pipelines does team-billing own?")` → returns BrainQueryResult with Cypher and pipeline names
- [ ] `BrainEngine.query("What would be impacted if the orders table goes down?")` → returns dependency_chain populated

Each test should:
- Return the correct Pydantic model (not raw strings)
- Include the actual query executed (SQL/Cypher/vector search)
- Complete within 30 seconds
