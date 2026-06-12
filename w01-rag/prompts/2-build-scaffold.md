# Prompt 02 — Build Project Scaffold

## Context

The CLAUDE.md contract is in place. The project plan lives at `sketch/plan.md`. Now we need the physical structure — the skeleton of the project before any logic is written.

## Objective

Create the complete directory structure for the DataOps Knowledge Hub project. Every folder must exist with a placeholder or `__init__.py` so the architecture is visible and navigable from the start.

## Directory Structure to Create

```
dataops-knowledge-hub/
│
├── docs/
│   └── (reference docs already placed here)
│
├── sketch/
│   └── plan.md (already exists)
│
├── prompts/
│   └── (prompt files already here)
│
├── infra/
│   ├── scripts/
│   │   └── .gitkeep
│   └── .gitkeep
│
├── generator/
│   └── .gitkeep
│
├── src/
│   ├── __init__.py
│   ├── schemas/
│   │   └── __init__.py
│   ├── ingestion/
│   │   └── __init__.py
│   ├── engines/
│   │   └── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes/
│   │       └── __init__.py
│   └── mcp/
│       └── __init__.py
│
├── tests/
│   └── __init__.py
│
├── .env.example
├── .gitignore
├── pyproject.toml
├── Makefile
└── README.md
```

## File Contents

### `.env.example`

```env
# LLM
OPENAI_API_KEY=sk-your-key-here
LLM_MODEL=gpt-4.1-mini

# PostgreSQL (Ledger)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=dataops
POSTGRES_USER=dataops
POSTGRES_PASSWORD=dataops123

# MongoDB (Events)
MONGO_HOST=localhost
MONGO_PORT=27017
MONGO_DB=dataops

# Qdrant (Memory)
QDRANT_HOST=localhost
QDRANT_PORT=6333

# Neo4j (Brain)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=dataops123

# SeaweedFS (Data Lake)
SEAWEEDFS_HOST=localhost
SEAWEEDFS_PORT=8333
SEAWEEDFS_BUCKET=dataops-lake
```

### `.gitignore`

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
.venv/
venv/

# Environment
.env

# IDE
.vscode/
.idea/

# Docker
docker-compose.override.yml

# Data
*.parquet
*.csv
!docs/**/*.csv
```

### `pyproject.toml`

```toml
[project]
name = "dataops-knowledge-hub"
version = "0.1.0"
description = "Enterprise RAG system with LlamaIndex + Pydantic — Ledger, Memory & Brain architecture"
requires-python = ">=3.11"
dependencies = [
    "llama-index>=0.12.0",
    "llama-index-readers-database>=0.3.0",
    "llama-index-vector-stores-qdrant>=0.4.0",
    "llama-index-graph-stores-neo4j>=0.4.0",
    "llama-index-embeddings-openai>=0.3.0",
    "llama-index-llms-openai>=0.3.0",
    "pydantic>=2.0",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "sqlalchemy>=2.0",
    "psycopg2-binary>=2.9",
    "pymongo>=4.8",
    "qdrant-client>=1.12",
    "neo4j>=5.25",
    "boto3>=1.35",
    "faker>=30.0",
    "python-dotenv>=1.0",
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=5.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### `Makefile`

```makefile
.PHONY: up down logs restart ingest query test

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

restart:
	docker compose down && docker compose up -d

status:
	docker compose ps

ingest:
	python -m src.ingestion.pipeline

query:
	@read -p "Question: " q; \
	curl -s -X POST http://localhost:8000/query \
		-H "Content-Type: application/json" \
		-d "{\"question\": \"$$q\"}" | python -m json.tool

test:
	pytest tests/ -v
```

### `README.md`

```markdown
# DataOps Knowledge Hub

Enterprise RAG system demonstrating multi-source retrieval across structured, semi-structured, and unstructured data stores.

## Architecture

- **Ledger** (PostgreSQL) — Text-to-SQL for factual/transactional queries
- **Memory** (Qdrant) — Semantic vector search for documents and logs
- **Brain** (Neo4j) — Graph traversal for relationships and lineage

## Quick Start

\```bash
cp .env.example .env
# Add your OPENAI_API_KEY to .env
make up
\```

## Stack

LlamaIndex | Pydantic | FastAPI | PostgreSQL | Qdrant | Neo4j | SeaweedFS | Docker

---

*Part of the Intelligent DataOps Platform — AIDE Brasil Formation (W01)*
```

## Validation

After execution, verify:
- [ ] All directories exist with `__init__.py` or `.gitkeep`
- [ ] `.env.example` has all required variables
- [ ] `pyproject.toml` lists all dependencies with versions
- [ ] `Makefile` commands are functional (syntax correct)
- [ ] `.gitignore` covers Python, env, IDE, and data files
- [ ] `README.md` gives a clear overview
