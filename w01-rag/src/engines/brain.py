"""BrainEngine — Cypher generation + execution over Neo4j.

Custom Cypher generation (Option B from the prompt): the LLM is given the
graph schema and a few worked examples, generates a Cypher query, we execute
it against Neo4j, and synthesize the result into a `BrainQueryResult`.

Why not `KnowledgeGraphQueryEngine`? It expects a LlamaIndex-managed graph
(via `KnowledgeGraphIndex` / `PropertyGraphStore`) — our graph was seeded by
hand with custom labels and constraints, so direct Cypher generation gives us
the right level of control without re-ingesting through LlamaIndex.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from llama_index.llms.openai import OpenAI
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from src.engines.config import EngineConfig
from src.schemas.domain import DependencyChain
from src.schemas.query import BrainQueryResult

log = logging.getLogger(__name__)

__all__ = ["BrainEngine"]


_SCHEMA = """\
Graph schema:
  Node labels and properties:
    Team(name, slack_channel)
    Pipeline(name, schedule, owner, sla_minutes)
    Table(name, schema, database, row_count)
    Dashboard(name, tool, owner, refresh_frequency)
  Relationships:
    (Team)-[:OWNS]->(Pipeline | Table)
    (Pipeline)-[:READS_FROM]->(Table)
    (Pipeline)-[:WRITES_TO]->(Table)
    (Pipeline)-[:FEEDS]->(Pipeline)
    (Table)-[:USED_BY]->(Dashboard)
"""

_FEW_SHOT = """\
Examples:

Q: What pipelines does team-billing own?
Cypher: MATCH (t:Team {name:'team-billing'})-[:OWNS]->(p:Pipeline) RETURN p.name AS pipeline

Q: What happens if the orders table goes down?
Cypher: MATCH (t:Table {name:'orders'})<-[:READS_FROM|WRITES_TO*1..3]-(downstream) RETURN DISTINCT labels(downstream)[0] AS kind, downstream.name AS name

Q: Show the lineage of fact_revenue.
Cypher: MATCH path=(source)-[:READS_FROM|WRITES_TO|FEEDS*]->(t:Table {name:'fact_revenue'}) RETURN [n IN nodes(path) | {kind: labels(n)[0], name: n.name}] AS chain
"""

_CYPHER_GEN_SYSTEM = (
    "You translate questions about a data platform into a single Cypher query "
    "for Neo4j 5. Use only the labels, properties, and relationships in the "
    "schema. Never invent labels. Return ONLY the Cypher query, no prose, no "
    "code fences, no trailing semicolon."
)

_SYNTH_SYSTEM = (
    "You summarize Neo4j query results into a clear, concise answer. "
    "Mention the specific entities returned. If the result is empty, say so."
)


_VAR_LEN_RE = re.compile(r"\*\s*\d*\s*\.\.\s*\d*", re.IGNORECASE)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text.rstrip(";").strip()


class BrainEngine:
    """Cypher-driven query engine over the Brain graph (Neo4j)."""

    def __init__(self, config: EngineConfig | None = None) -> None:
        self.config = config or EngineConfig()
        try:
            self._driver = GraphDatabase.driver(
                self.config.neo4j_uri,
                auth=(self.config.neo4j_user, self.config.neo4j_password),
            )
            self._driver.verify_connectivity()
        except (ServiceUnavailable, Neo4jError, OSError) as exc:
            raise RuntimeError(
                f"BrainEngine: could not connect to Neo4j at "
                f"{self.config.neo4j_uri}: {exc}"
            ) from exc
        self._llm = OpenAI(model=self.config.llm_model)

    # ---- Cypher generation & synthesis (LLM calls) ----

    async def _generate_cypher(self, question: str) -> str:
        prompt = (
            f"{_SCHEMA}\n{_FEW_SHOT}\n"
            f"Question: {question}\n"
            "Cypher:"
        )
        resp = await self._llm.acomplete(prompt, system_prompt=_CYPHER_GEN_SYSTEM)
        return _strip_fences(str(resp))

    async def _synthesize(self, question: str, cypher: str, rows: list[dict]) -> str:
        preview = rows[:25]
        prompt = (
            f"Question: {question}\n"
            f"Cypher executed:\n{cypher}\n"
            f"Result rows ({len(rows)} total, showing up to 25):\n{preview}\n"
            "Concise answer:"
        )
        resp = await self._llm.acomplete(prompt, system_prompt=_SYNTH_SYSTEM)
        return str(resp).strip()

    # ---- Neo4j execution (sync, wrapped in to_thread) ----

    def _run_cypher_sync(self, cypher: str) -> list[dict]:
        with self._driver.session() as session:
            result = session.run(cypher)
            return [r.data() for r in result]

    async def _run_cypher(self, cypher: str) -> list[dict]:
        return await asyncio.to_thread(self._run_cypher_sync, cypher)

    # ---- Result shaping ----

    @staticmethod
    def _extract_entities(rows: list[dict]) -> tuple[set[str], set[str]]:
        """Walk every value in every row and collect (entity_names, relationship_names).

        Heuristic: any value that's a non-empty string and looks like a name
        becomes a candidate. Relationships aren't returned literally by most of
        our Cypher templates — we'd need to RETURN type(r) for that — so this
        focuses on entities. The synthesis LLM call still gets full rows.
        """
        entities: set[str] = set()
        relationships: set[str] = set()

        def walk(v: Any) -> None:
            if isinstance(v, str):
                if v and v not in {"info", "warning", "critical"}:
                    entities.add(v)
            elif isinstance(v, dict):
                for vv in v.values():
                    walk(vv)
            elif isinstance(v, list):
                for vv in v:
                    walk(vv)

        for row in rows:
            for v in row.values():
                walk(v)
        return entities, relationships

    @staticmethod
    def _build_dependency_chain(cypher: str, rows: list[dict]) -> DependencyChain | None:
        """Populate dependency_chain when the executed Cypher is a variable-length
        traversal — i.e. the question is asking about downstream/upstream impact.
        """
        if not _VAR_LEN_RE.search(cypher) or not rows:
            return None

        downstream_pipelines: list[str] = []
        downstream_tables: list[str] = []
        downstream_dashboards: list[str] = []
        impacted_teams: list[str] = []
        seen: set[tuple[str, str]] = set()

        def remember(kind: str | None, name: str | None) -> None:
            if not kind or not name:
                return
            key = (kind, name)
            if key in seen:
                return
            seen.add(key)
            bucket = {
                "Pipeline": downstream_pipelines,
                "Table": downstream_tables,
                "Dashboard": downstream_dashboards,
                "Team": impacted_teams,
            }.get(kind)
            if bucket is not None:
                bucket.append(name)

        for row in rows:
            for v in row.values():
                if isinstance(v, dict) and "kind" in v and "name" in v:
                    remember(v.get("kind"), v.get("name"))
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict) and "kind" in item and "name" in item:
                            remember(item.get("kind"), item.get("name"))

        if not (downstream_pipelines or downstream_tables or downstream_dashboards or impacted_teams):
            return None

        # Best-effort: pull the source name out of the Cypher (the `name:'X'` literal).
        match = re.search(r"name\s*:\s*'([^']+)'", cypher)
        source = match.group(1) if match else "unknown"

        return DependencyChain(
            source=source,
            downstream_pipelines=downstream_pipelines,
            downstream_tables=downstream_tables,
            downstream_dashboards=downstream_dashboards,
            impacted_teams=impacted_teams,
        )

    # ---- Public API ----

    async def _query_once(self, question: str) -> BrainQueryResult:
        try:
            cypher = await self._generate_cypher(question)
        except Exception as exc:
            log.exception("Brain: Cypher generation failed")
            return BrainQueryResult(
                cypher_query_executed="",
                summary=f"Cypher generation failed: {exc}",
                nodes_traversed=0,
                relationships_found=[],
                dependency_chain=None,
            )

        try:
            rows = await self._run_cypher(cypher)
        except Neo4jError as exc:
            log.warning("Brain: Cypher execution failed: %s", exc)
            return BrainQueryResult(
                cypher_query_executed=cypher,
                summary=f"Cypher execution failed: {exc.message or exc}",
                nodes_traversed=0,
                relationships_found=[],
                dependency_chain=None,
            )

        entities, relationships = self._extract_entities(rows)
        summary = await self._synthesize(question, cypher, rows)
        dep_chain = self._build_dependency_chain(cypher, rows)

        return BrainQueryResult(
            cypher_query_executed=cypher,
            summary=summary,
            nodes_traversed=len(entities),
            relationships_found=sorted(relationships),
            dependency_chain=dep_chain,
        )

    async def query(self, question: str) -> BrainQueryResult:
        try:
            return await asyncio.wait_for(
                self._query_once(question),
                timeout=self.config.query_timeout_seconds,
            )
        except asyncio.TimeoutError:
            return BrainQueryResult(
                cypher_query_executed="",
                summary=f"Query timed out after {self.config.query_timeout_seconds}s",
                nodes_traversed=0,
                relationships_found=[],
                dependency_chain=None,
            )

    def close(self) -> None:
        try:
            self._driver.close()
        except Exception:
            pass
