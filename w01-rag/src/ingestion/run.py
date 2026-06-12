"""Entry point for the Memory ingestion pipeline.

Usage: `python -m src.ingestion.run` (or `make ingest`).
"""
from __future__ import annotations

import asyncio
import logging

from src.ingestion.config import IngestionConfig
from src.ingestion.pipeline import build_pipeline, run_pipeline
from src.ingestion.readers import MongoDBReader, SeaweedFSReader

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ingestion")


async def main() -> int:
    config = IngestionConfig()

    log.info("Loading documents from SeaweedFS…")
    seaweedfs_docs = SeaweedFSReader(config).load_data()
    log.info("  → %d documents from SeaweedFS", len(seaweedfs_docs))

    log.info("Loading documents from MongoDB…")
    mongo_docs = MongoDBReader(config).load_data()
    log.info("  → %d documents from MongoDB", len(mongo_docs))

    all_documents = seaweedfs_docs + mongo_docs
    log.info("Total documents to ingest: %d", len(all_documents))

    if not all_documents:
        log.warning("No documents to ingest — exiting without contacting Qdrant.")
        return 0

    pipeline = build_pipeline(config)
    nodes = await run_pipeline(pipeline, all_documents)
    log.info("Ingestion complete. %d node(s) indexed in Qdrant.", len(nodes))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
