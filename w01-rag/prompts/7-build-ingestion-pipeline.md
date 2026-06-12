# Prompt 07 — Build Ingestion Pipeline

## Context

Pydantic schemas are defined. Infrastructure is running with data flowing. Now we build the **ingestion layer** — the process that reads from our data sources, chunks, enriches with metadata, embeds, and indexes into Qdrant (Memory engine).

This is where LlamaIndex enters the project for the first time.

Important: The Ledger (PostgreSQL) and Brain (Neo4j) do NOT need ingestion into a vector store — they are queried directly via Text-to-SQL and Cypher respectively. The ingestion pipeline is specifically for the **Memory** layer: documents from SeaweedFS and event logs from MongoDB that need semantic search.

## Objective

Create the LlamaIndex ingestion pipeline that:
1. Reads documents from SeaweedFS (PDFs, Markdown, CSV)
2. Reads event logs from MongoDB (text-heavy fields)
3. Chunks using semantic splitting
4. Enriches with metadata extraction
5. Embeds and indexes into Qdrant

## Files to Create

### 1. `src/ingestion/__init__.py`

Export the main pipeline function.

### 2. `src/ingestion/config.py`

Configuration for the ingestion pipeline:

```python
from pydantic_settings import BaseSettings


class IngestionConfig(BaseSettings):
    # LLM
    openai_api_key: str
    llm_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "dataops-memory"

    # SeaweedFS
    seaweedfs_host: str = "localhost"
    seaweedfs_port: int = 8333
    seaweedfs_bucket: str = "dataops-lake"

    # MongoDB
    mongo_host: str = "localhost"
    mongo_port: int = 27017
    mongo_db: str = "dataops"

    # Pipeline settings
    chunk_size: int = 512
    chunk_overlap: int = 50

    class Config:
        env_file = ".env"
        extra = "ignore"
```

### 3. `src/ingestion/readers.py`

Custom readers that pull data from our sources:

**SeaweedFS Reader:**
- Connect to SeaweedFS via boto3 (S3-compatible)
- List all objects in the `dataops-lake` bucket
- Download each file and convert to LlamaIndex `Document`
- Add metadata: `source_type: "seaweedfs"`, `file_name`, `file_type`, `upload_date`

**MongoDB Reader:**
- Connect to MongoDB
- Read from `event_logs` collection (last 24 hours of logs)
- Convert each log entry to a LlamaIndex `Document` with text = formatted log string
- Add metadata: `source_type: "mongodb"`, `collection: "event_logs"`, `pipeline_name`, `status`, `severity`

- Read from `user_activity` collection (last 24 hours)
- Convert each activity to a LlamaIndex `Document`
- Add metadata: `source_type: "mongodb"`, `collection: "user_activity"`, `action`, `user_id`

**Implementation notes:**
- Use `llama_index.core.schema.Document` (not deprecated `llama_index.schema`)
- Each reader should be a class with a `load_data() -> list[Document]` method
- Handle connection errors gracefully (log warning, return empty list)

### 4. `src/ingestion/pipeline.py`

The main ingestion pipeline using LlamaIndex's `IngestionPipeline`:

```python
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter, SemanticSplitterNodeParser
from llama_index.core.extractors import (
    TitleExtractor,
    SummaryExtractor,
    QuestionsAnsweredExtractor,
    KeywordExtractor,
)
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
```

**Pipeline stages:**

1. **Splitting:** Use `SemanticSplitterNodeParser` as primary (splits by meaning, not fixed size). Fallback to `SentenceSplitter(chunk_size=512, chunk_overlap=50)` if semantic splitting fails or for very short documents.

2. **Metadata Enrichment** (use LLM-based extractors):
   - `TitleExtractor(nodes=3)` — extracts/infers title from first N nodes
   - `SummaryExtractor(summaries=["self"])` — generates a summary per chunk
   - `KeywordExtractor(keywords=5)` — extracts 5 keywords per chunk
   - `QuestionsAnsweredExtractor(questions=3)` — generates 3 questions this chunk can answer

3. **Embedding:** `OpenAIEmbedding(model="text-embedding-3-small")`

4. **Storage:** `QdrantVectorStore` connected to our Qdrant instance, collection name `dataops-memory`

**Pipeline construction:**

```python
pipeline = IngestionPipeline(
    transformations=[
        semantic_splitter,
        title_extractor,
        summary_extractor,
        keyword_extractor,
        questions_extractor,
        embed_model,
    ],
    vector_store=vector_store,
)
```

**Execution:**
- `pipeline.run(documents=all_documents)` — processes all documents and stores in Qdrant
- Log: number of documents loaded, number of nodes created, time elapsed

### 5. `src/ingestion/run.py`

Entry point for running the pipeline (called by `make ingest` or `python -m src.ingestion.run`):

```python
import asyncio
import logging
from src.ingestion.config import IngestionConfig
from src.ingestion.readers import SeaweedFSReader, MongoDBReader
from src.ingestion.pipeline import build_pipeline, run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def main():
    config = IngestionConfig()

    # Load documents from all sources
    logger.info("Loading documents from SeaweedFS...")
    seaweedfs_reader = SeaweedFSReader(config)
    seaweedfs_docs = seaweedfs_reader.load_data()
    logger.info(f"  → {len(seaweedfs_docs)} documents from SeaweedFS")

    logger.info("Loading documents from MongoDB...")
    mongo_reader = MongoDBReader(config)
    mongo_docs = mongo_reader.load_data()
    logger.info(f"  → {len(mongo_docs)} documents from MongoDB")

    all_documents = seaweedfs_docs + mongo_docs
    logger.info(f"Total documents to ingest: {len(all_documents)}")

    # Build and run pipeline
    pipeline = build_pipeline(config)
    nodes = await run_pipeline(pipeline, all_documents)
    logger.info(f"Ingestion complete. {len(nodes)} nodes indexed in Qdrant.")


if __name__ == "__main__":
    asyncio.run(main())
```

## Important Notes

- **Do NOT ingest PostgreSQL data into Qdrant.** The Ledger is queried directly via Text-to-SQL. Ingesting it would create redundancy and confusion.
- **Do NOT ingest Neo4j data into Qdrant.** The Brain is queried directly via Cypher. The graph structure would be lost in vector space.
- **The Memory engine (Qdrant) is specifically for:** unstructured docs (policies, runbooks, SLA definitions from SeaweedFS) + semi-structured logs (event_logs, user_activity from MongoDB).
- **Semantic splitting** is preferred over fixed-size because our documents vary wildly in structure (markdown with headers vs. flat log entries).
- **Metadata extractors** are key — they make retrieval much more precise by adding searchable metadata to each chunk.

## Validation

After execution, verify:
- [ ] `python -m src.ingestion.run` completes without errors
- [ ] Qdrant collection `dataops-memory` exists: `curl http://localhost:6333/collections/dataops-memory`
- [ ] Collection has points: the `points_count` field is > 0
- [ ] Each point has metadata (title, summary, keywords, questions_this_excerpt_can_answer)
- [ ] Documents from both SeaweedFS and MongoDB are represented in the collection
- [ ] `make ingest` works as a shortcut
