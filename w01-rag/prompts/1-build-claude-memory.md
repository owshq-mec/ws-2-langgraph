# Prompt 01 — Create CLAUDE.md

## Context

We are building an **Enterprise DataOps Knowledge Hub** — a production-grade RAG system that queries 3 different data stores (PostgreSQL, Qdrant, Neo4j) through intelligent routing using LlamaIndex and Pydantic.

The project plan is available at `sketch/plan.md`. Reference documentation is in the `docs/` folder.

## Objective

Create a `CLAUDE.md` file at the project root. This file is the **contract** between the developer and Claude Code. It defines how the agent should behave, what it knows, and what rules it must follow when working on this project.

## Requirements

The CLAUDE.md must include the following sections:

### 1. Project Overview

- One paragraph describing what the DataOps Knowledge Hub is

- The Ledger + Memory + Brain architecture concept

- The end goal: a FastAPI + MCP-served RAG system

### 2. Tech Stack

- LlamaIndex (0.12+) for orchestration

- Pydantic v2 for contracts and structured output

- FastAPI for serving

- PostgreSQL 16 (Ledger)

- Qdrant (Memory)

- Neo4j 5.x (Brain)

- SeaweedFS (Object Storage / Data Lake)

- Docker Compose for local infra

- Railway for production deploy

### 3. Architecture Rules

- All LLM outputs MUST be validated through Pydantic models

- Never use raw string responses from LLMs

- Every query engine must return a typed response

- Use `SubQuestionQueryEngine` for cross-domain queries

- Use `IngestionPipeline` (not manual indexing) for data ingestion

- Semantic chunking over fixed-size chunking

- All API endpoints must have request/response Pydantic models

### 4. Code Standards

- Python 3.11+

- Use `async/await` throughout (FastAPI + LlamaIndex async methods)

- Type hints on all functions

- Docstrings on all public functions

- Use `pyproject.toml` (not requirements.txt) for dependency management

- Follow src/ layout pattern

- Environment variables via `.env` file (never hardcode secrets)

### 5. Project Structure

Reference the directory layout from `sketch/plan.md`

### 6. Naming Conventions

- Files: `snake_case.py`

- Classes: `PascalCase`

- Pydantic models: descriptive names ending in `Request`, `Response`, `Config`, or domain name

- API routes: `/kebab-case`

- Docker services: `kebab-case`

### 7. Testing

- Use `pytest` with `pytest-asyncio`

- Test each engine independently before integration

- End-to-end test: a cross-domain query must return valid Pydantic output

### 8. Key References

- Point to `sketch/plan.md` for architecture decisions

- Point to `docs/` for reference documentation

- Point to LlamaIndex docs for API reference

### 9. Workflow

- Read the current task from `prompts/` folder (numbered sequentially)

- Execute one task at a time

- After completing a task, summarize what was done

- Do NOT proceed to the next task without confirmation

### 10. Constraints

- Do NOT use LangChain (this project uses LlamaIndex exclusively)

- Do NOT use ChromaDB (use Qdrant)

- Do NOT use in-memory vector stores in production code (only in tests)

- Do NOT hardcode model names — use environment variables

- Do NOT create a frontend/UI (API-only for now)

## Output

A single file: `CLAUDE.md` at the project root, well-formatted in Markdown, concise but complete.

## Validation

After creating the CLAUDE.md, verify:

- [ ] All 10 sections are present

- [ ] Tech stack versions are specified

- [ ] Architecture rules are clear and actionable

- [ ] The file references `sketch/plan.md` and `docs/`

- [ ] Workflow section mentions the `prompts/` folder

