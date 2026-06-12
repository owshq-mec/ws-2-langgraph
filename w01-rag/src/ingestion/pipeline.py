"""LlamaIndex IngestionPipeline assembly for the Memory layer.

Stages: semantic split → title/summary/keyword/Q&A extraction → embed → upsert
into Qdrant. Built and run as two separate functions so callers can introspect
the pipeline (`build_pipeline`) or execute it (`run_pipeline`).
"""
from __future__ import annotations

import logging
import time
from typing import Sequence

from llama_index.core.extractors import (
    KeywordExtractor,
    QuestionsAnsweredExtractor,
    SummaryExtractor,
    TitleExtractor,
)
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SemanticSplitterNodeParser, SentenceSplitter
from llama_index.core.schema import BaseNode, Document
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from src.ingestion.config import IngestionConfig

log = logging.getLogger(__name__)

__all__ = ["build_pipeline", "run_pipeline"]

# Documents shorter than this go through SentenceSplitter — SemanticSplitter
# needs enough text to meaningfully detect topic shifts.
_SEMANTIC_MIN_CHARS = 1500


def _build_vector_store(config: IngestionConfig) -> QdrantVectorStore:
    client = QdrantClient(host=config.qdrant_host, port=config.qdrant_port)
    return QdrantVectorStore(client=client, collection_name=config.qdrant_collection)


def _build_extractors(llm: OpenAI) -> list:
    return [
        TitleExtractor(nodes=3, llm=llm),
        SummaryExtractor(summaries=["self"], llm=llm),
        KeywordExtractor(keywords=5, llm=llm),
        QuestionsAnsweredExtractor(questions=3, llm=llm),
    ]


def build_pipeline(config: IngestionConfig) -> IngestionPipeline:
    """Assemble the LlamaIndex IngestionPipeline.

    Uses SemanticSplitterNodeParser as the primary splitter. Short documents
    are pre-split with SentenceSplitter before reaching the pipeline (see
    `run_pipeline`) so the LLM-driven semantic splitter doesn't waste calls
    on tiny payloads.
    """
    llm = OpenAI(model=config.llm_model)
    embed_model = OpenAIEmbedding(model=config.embedding_model)

    semantic_splitter = SemanticSplitterNodeParser(
        buffer_size=1,
        breakpoint_percentile_threshold=95,
        embed_model=embed_model,
    )

    transformations = [
        semantic_splitter,
        *_build_extractors(llm),
        embed_model,
    ]

    pipeline = IngestionPipeline(
        transformations=transformations,
        vector_store=_build_vector_store(config),
    )
    log.info(
        "Pipeline built: collection=%s embedding=%s llm=%s",
        config.qdrant_collection,
        config.embedding_model,
        config.llm_model,
    )
    return pipeline


def _presplit_short_docs(
    documents: Sequence[Document], config: IngestionConfig
) -> list[Document]:
    """Send short documents through SentenceSplitter up-front and emit their
    chunks as Documents. SemanticSplitter then no-ops on them (they're already
    small) but still routes them through the extractor/embedding stack.
    """
    sentence_splitter = SentenceSplitter(
        chunk_size=config.chunk_size, chunk_overlap=config.chunk_overlap
    )
    out: list[Document] = []
    for doc in documents:
        if len(doc.text) >= _SEMANTIC_MIN_CHARS:
            out.append(doc)
            continue
        nodes = sentence_splitter.get_nodes_from_documents([doc])
        for i, node in enumerate(nodes):
            out.append(
                Document(
                    doc_id=f"{doc.doc_id}::part-{i}",
                    text=node.get_content(),
                    metadata={**doc.metadata, "presplit": "sentence"},
                )
            )
    return out


async def run_pipeline(
    pipeline: IngestionPipeline, documents: Sequence[Document]
) -> list[BaseNode]:
    """Run the pipeline against the given documents and return the produced nodes."""
    if not documents:
        log.warning("run_pipeline called with 0 documents — nothing to ingest.")
        return []

    # Pull config off the first document's pipeline indirectly? No — config
    # parameters we need here are chunk_size/overlap which only affect the
    # presplit step. Use a fresh IngestionConfig() (same env_file).
    documents = _presplit_short_docs(list(documents), IngestionConfig())

    log.info("Running pipeline on %d document(s)…", len(documents))
    started = time.perf_counter()
    nodes = await pipeline.arun(documents=list(documents), show_progress=True)
    elapsed = time.perf_counter() - started
    log.info("Pipeline complete: %d node(s) in %.1fs", len(nodes), elapsed)
    return nodes
