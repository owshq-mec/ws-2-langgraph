# CLAUDE.md — DataOps Knowledge Hub

> This file is the **contract** between the developer and Claude Code.
> It defines how the agent behaves, what it knows, and which rules it must follow when working on this project.

---

## 1. Project Overview

The **DataOps Knowledge Hub** is a production-grade **Enterprise RAG system** that answers complex cross-domain questions by querying three heterogeneous data stores through intelligent routing. It is built on the **Ledger + Memory + Brain** cognitive architecture:

- **Ledger** — factual truth (numbers, transactions, metrics) stored in **PostgreSQL**, queried via text-to-SQL.
- **Memory** — historical context (documents, logs, policies) stored in **Qdrant**, queried via semantic vector search.
- **Brain** — connections (relationships, lineage, dependencies) stored in **Neo4j**, queried via Cypher graph traversal.

A `SubQuestionQueryEngine` decomposes natural-language questions and routes sub-queries to the right engine. The end goal is a **FastAPI + MCP-served RAG system** that any agent (Claude Code included) can consume as a tool, deployed on Railway.

---

## 2. Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Orchestration | LlamaIndex | 0.12+ |
| Contracts / Structured Output | Pydantic | v2.x |
| API Layer | FastAPI | 0.115+ |
| Relational DB (Ledger) | PostgreSQL | 16 |
| Vector DB (Memory) | Qdrant | latest |
| Graph DB (Brain) | Neo4j | 5.x |
| Object Storage / Data Lake | SeaweedFS | latest |
| Local Infra | Docker Compose | — |
| Production Deploy | Railway | — |
| Agent Protocol | MCP (Model Context Protocol) | — |
| Language Runtime | Python | 3.11+ |

---

## 3. Architecture Rules

These rules are non-negotiable. Every change must respect them.

- All LLM outputs **MUST** be validated through Pydantic models.
- **Never** use raw string responses from LLMs — always coerce into a typed schema.
- Every query engine **must** return a typed (Pydantic) response.
- Use `SubQuestionQueryEngine` (or `RouterQueryEngine`) for cross-domain queries — do not hand-roll routing.
- Use LlamaIndex `IngestionPipeline` for data ingestion — do not manually index documents.
- Prefer **semantic chunking** (`SemanticSplitterNodeParser`) over fixed-size chunking.
- All API endpoints must declare **request and response Pydantic models**.

---

## 4. Code Standards

- Python **3.11+**.
- Use **`async`/`await`** throughout — FastAPI routes and LlamaIndex async methods.
- **Type hints** on all functions (parameters and return).
- **Docstrings** on all public functions and classes.
- Dependency management via **`pyproject.toml`** — do not use `requirements.txt`.
- Follow the **`src/` layout** pattern.
- Environment variables via **`.env`** (loaded by `pydantic-settings`) — **never hardcode secrets, API keys, connection strings, or model names**.

---

## 5. Project Structure

Refer to [sketch/plan.md](sketch/plan.md) for the canonical architecture and build sequence. The expected layout follows the `src/` pattern:

```
ws-1-llama-index-rag/
├── src/
│   ├── api/              # FastAPI routes and dependency injection
│   ├── engines/          # Ledger / Memory / Brain query engines
│   ├── ingestion/        # IngestionPipeline definitions
│   ├── models/           # Pydantic schemas (Request/Response/Config)
│   ├── routing/          # SubQuestionQueryEngine wiring
│   ├── mcp/              # MCP server exposing the RAG as a tool
│   └── settings.py       # pydantic-settings config
├── tests/                # pytest + pytest-asyncio
├── docker/               # docker-compose.yml + init scripts
├── data_generator/       # Faker-based continuous data producer
├── docs/                 # Reference documentation
├── sketch/               # Architecture plan
├── prompts/              # Sequential task prompts (the workflow)
├── pyproject.toml
├── .env.example
└── CLAUDE.md
```

---

## 6. Naming Conventions

- Files / modules: `snake_case.py`
- Classes: `PascalCase`
- Pydantic models: descriptive names ending in `Request`, `Response`, `Config`, or the domain name (e.g., `LedgerQueryRequest`, `BrainTraversalResponse`, `QdrantConfig`).
- API routes: `/kebab-case` (e.g., `/query-hub`, `/ingest-documents`).
- Docker services: `kebab-case` (e.g., `vector-db`, `graph-db`, `data-generator`).
- Environment variables: `UPPER_SNAKE_CASE`.

---

## 7. Testing

- Framework: **`pytest`** with **`pytest-asyncio`**.
- **Test each engine independently** before composing them — Ledger, Memory, and Brain each get their own test module.
- **End-to-end test**: a cross-domain query through the `SubQuestionQueryEngine` must return a valid, Pydantic-validated response.
- In-memory vector stores (e.g., `SimpleVectorStore`) are allowed **only in tests** — production paths use Qdrant.
- Tests live under `tests/` mirroring the `src/` tree.

---

## 8. Key References

- [sketch/plan.md](sketch/plan.md) — canonical architecture, build sequence, success criteria, design decisions.
- [docs/](docs/) — reference documentation (workshop content, RAG fundamentals).
- **LlamaIndex docs** — https://docs.llamaindex.ai/ for API reference (engines, ingestion, structured output).
- **Pydantic v2 docs** — https://docs.pydantic.dev/latest/ for validation and `model_validate`.

When in doubt about a library API, consult Context7 / Ref MCP for current documentation rather than relying on memory.

---

## 9. Workflow

This project is built **prompt-by-prompt** in a deterministic sequence.

1. Read the current task from the [prompts/](prompts/) folder — files are numbered sequentially (`1-...`, `2-...`).
2. Execute **one task at a time**. Do not skip ahead.
3. After completing a task, **summarize what was done** (files created/edited, decisions made, verification performed).
4. **Do NOT proceed to the next task without explicit confirmation** from the developer.
5. If the task is ambiguous, ask before guessing.

---

## 10. Constraints

Hard prohibitions. Violating any of these is a regression.

- ❌ **Do NOT use LangChain** — this project uses **LlamaIndex exclusively**.
- ❌ **Do NOT use ChromaDB** — the vector store is **Qdrant**.
- ❌ **Do NOT use in-memory vector stores in production code** — only in tests.
- ❌ **Do NOT hardcode model names** (OpenAI, Anthropic, embedding models) — read from environment variables.
- ❌ **Do NOT build a frontend / UI** — this project is **API-only** (FastAPI + MCP). Visualization belongs to downstream workshops (W06, W07).
- ❌ **Do NOT commit secrets** — `.env` is git-ignored; only `.env.example` is committed.
