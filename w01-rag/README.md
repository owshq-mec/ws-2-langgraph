# DataOps Knowledge Hub

Enterprise RAG system demonstrating multi-source retrieval across structured, semi-structured, and unstructured data stores.

## Architecture

- **Ledger** (PostgreSQL) — Text-to-SQL for factual/transactional queries
- **Memory** (Qdrant) — Semantic vector search for documents and logs
- **Brain** (Neo4j) — Graph traversal for relationships and lineage

## Quick Start

```bash
cp .env.example .env
# Add your OPENAI_API_KEY to .env
make up
```

## Stack

LlamaIndex | Pydantic | FastAPI | PostgreSQL | Qdrant | Neo4j | SeaweedFS | Docker

---

*Part of the Intelligent DataOps Platform — AIDE Brasil Formation (W01)*
