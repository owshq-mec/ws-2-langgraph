"""Memory ingestion pipeline — reads SeaweedFS + MongoDB, indexes into Qdrant.

Submodules are NOT eagerly imported here so that callers needing only `config`
or `readers` don't pay the cost of importing the full LlamaIndex stack.
"""
__all__ = [
    "IngestionConfig",
    "SeaweedFSReader",
    "MongoDBReader",
    "build_pipeline",
    "run_pipeline",
]
