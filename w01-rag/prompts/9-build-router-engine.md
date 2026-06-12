# Prompt 09 — Build Router Engine

## Context

The 3 individual engines are built and tested:
- **LedgerEngine** → Text-to-SQL on PostgreSQL (factual/numerical)
- **MemoryEngine** → Vector Search on Qdrant (policies, logs, docs)
- **BrainEngine** → Cypher on Neo4j (relationships, lineage, ownership)

Now we need the **Router** — the orchestrator that receives a user question, decides which engine(s) to consult, decomposes complex questions into sub-questions, and synthesizes a unified response.

This is the "Maestro" of the system.

## Objective

Create a Router Engine that:
1. Analyzes the incoming question
2. Determines which engine(s) are relevant
3. For complex questions, decomposes into sub-questions (one per engine)
4. Executes sub-questions in parallel against the appropriate engines
5. Synthesizes all results into a single `SynthesizedResponse` (Pydantic)

## Files to Create

### 1. `src/engines/router.py`

**Approach: Custom Router using LLM-based classification + parallel execution**

The LlamaIndex `SubQuestionQueryEngine` is one option, but for maximum control and transparency (showing which engine was chosen and why), we'll build a custom router that:

1. Uses the LLM to classify and decompose the question
2. Routes sub-questions to the appropriate engines
3. Synthesizes the final answer

**Implementation:**

```python
import asyncio
import time
from llama_index.llms.openai import OpenAI
from src.engines.ledger import LedgerEngine
from src.engines.memory import MemoryEngine
from src.engines.brain import BrainEngine
from src.schemas.query import SynthesizedResponse, LedgerQueryResult, MemoryQueryResult, BrainQueryResult
from src.schemas.api import SourceDetail
```

**Step 1 — Classification Prompt:**

Create a system prompt that instructs the LLM to classify the question and decompose it:

```
You are a query router for a DataOps Knowledge Hub with 3 data stores:

1. LEDGER (PostgreSQL) — Contains: customers, orders, products tables.
   Use for: numerical questions, counts, aggregations, revenue, top-N, filtering by status/plan/date.
   Examples: "How many enterprise customers?", "Total revenue this month?", "Top 5 customers by spend"

2. MEMORY (Qdrant Vector Store) — Contains: data retention policies, SLA definitions, incident runbooks, data dictionaries, pipeline event logs, user activity logs.
   Use for: policy questions, procedure questions, "what happened" questions, historical events, definitions.
   Examples: "What is the retention policy for PII?", "What's the SLA for etl_billing_daily?", "What happened in the last failure?"

3. BRAIN (Neo4j Graph) — Contains: pipelines, tables, dashboards, teams, and their relationships (OWNS, READS_FROM, WRITES_TO, FEEDS, USED_BY).
   Use for: relationship questions, dependency/lineage questions, ownership, impact analysis, "what connects to what".
   Examples: "Who owns the billing pipeline?", "What's impacted if orders table goes down?", "Show lineage of fact_revenue"

Given a user question, respond with a JSON object:
{
  "sub_questions": [
    {"engine": "ledger|memory|brain", "question": "the sub-question for this engine"}
  ]
}

Rules:
- Simple questions that clearly belong to one engine: return 1 sub-question.
- Complex questions that span multiple domains: decompose into 2-3 sub-questions, one per relevant engine.
- Never route to more than 3 sub-questions.
- Rephrase each sub-question to be self-contained and specific to that engine's data.
```

**Step 2 — Parallel Execution:**

After classification, execute all sub-questions in parallel using `asyncio.gather`:

```python
async def _execute_sub_questions(self, sub_questions: list[dict]) -> list[tuple[str, any]]:
    tasks = []
    for sq in sub_questions:
        engine_name = sq["engine"]
        question = sq["question"]
        if engine_name == "ledger":
            tasks.append(self._run_engine(self.ledger, question, "ledger"))
        elif engine_name == "memory":
            tasks.append(self._run_engine(self.memory, question, "memory"))
        elif engine_name == "brain":
            tasks.append(self._run_engine(self.brain, question, "brain"))
    return await asyncio.gather(*tasks)
```

**Step 3 — Synthesis:**

After all engines return, use the LLM one final time to synthesize:

```
Given the following sub-question results, synthesize a comprehensive answer to the original question.

Original question: {original_question}

Results:
{formatted_results}

Provide a clear, actionable answer that combines insights from all sources.
If there's a recommendation, include it.
```

**Step 4 — Build `SynthesizedResponse`:**

Combine everything into the Pydantic model:
- `answer`: the synthesized text
- `sub_questions`: the list of sub-questions that were generated
- `sources_consulted`: list of engine names used
- `confidence`: weighted average of individual engine confidences
- `recommendation`: extracted from synthesis if present

**Class interface:**

```python
class RouterEngine:
    def __init__(self, config: EngineConfig):
        self.llm = OpenAI(model=config.llm_model)
        self.ledger = LedgerEngine(config)
        self.memory = MemoryEngine(config)
        self.brain = BrainEngine(config)

    async def query(self, question: str, sources: list[str] | None = None) -> tuple[SynthesizedResponse, list[SourceDetail]]:
        """
        Route and execute a question across engines.

        Args:
            question: Natural language question
            sources: Optional filter — only use these engines (e.g., ["ledger", "brain"])

        Returns:
            Tuple of (SynthesizedResponse, list[SourceDetail]) for the API layer to consume
        """
```

**Source filtering:**
- If `sources` is provided (e.g., `["ledger", "brain"]`), skip the classification step and route directly to those engines with the original question.
- If `sources` is None, use the LLM classification to decide.

**Error handling:**
- If an engine fails (timeout, connection error), include it in the response with a note that the source was unavailable.
- Never fail the entire query because one engine is down. Return partial results with a note.

### 2. `src/engines/router.py` — Helper: `SourceDetail` builder

After each engine returns, build a `SourceDetail` object:

```python
def _build_source_detail(self, engine_name: str, result) -> SourceDetail:
    if engine_name == "ledger":
        return SourceDetail(
            source="ledger",
            data_store="postgresql",
            query_used=result.sql_query_executed,
            result_summary=result.summary,
            confidence=0.9  # SQL is deterministic
        )
    elif engine_name == "memory":
        return SourceDetail(
            source="memory",
            data_store="qdrant",
            query_used=f"Vector search (top_k=5)",
            result_summary=result.summary,
            confidence=result.confidence
        )
    elif engine_name == "brain":
        return SourceDetail(
            source="brain",
            data_store="neo4j",
            query_used=result.cypher_query_executed,
            result_summary=result.summary,
            confidence=0.85  # Cypher is deterministic but synthesis isn't
        )
```

## Validation

Test with 3 types of questions:

**Single-engine (should route to exactly 1):**
- [ ] "How many customers are on the enterprise plan?" → Ledger only
- [ ] "What is the SLA for etl_billing_daily?" → Memory only
- [ ] "Who owns the orders table?" → Brain only

**Multi-engine (should decompose into 2-3 sub-questions):**
- [ ] "How much revenue do our enterprise customers generate, and what pipelines process their data?" → Ledger + Brain
- [ ] "What's the incident response procedure for a P1 on the billing pipeline, and who owns it?" → Memory + Brain
- [ ] "Summarize the top customers by spend, their data retention requirements, and what systems would be impacted if the orders table went down" → Ledger + Memory + Brain (the WOW moment)

**Forced routing (sources filter):**
- [ ] `query("Tell me about customers", sources=["ledger"])` → Only hits Ledger, no classification step

All results must be:
- [ ] Valid `SynthesizedResponse` Pydantic model
- [ ] Include `sub_questions` showing the decomposition
- [ ] Include `sources_consulted` with `SourceDetail` per engine used
- [ ] Complete within 60 seconds (parallel execution should keep it under 30s typically)
