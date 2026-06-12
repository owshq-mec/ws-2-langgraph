"""Configuration for the Memory ingestion pipeline.

Reads from .env via pydantic-settings. All defaults match the local Docker
Compose stack so a developer can `python -m src.ingestion.run` with no env
setup beyond OPENAI_API_KEY.
"""
from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["IngestionConfig"]


class IngestionConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # LLM / embeddings
    openai_api_key: str
    llm_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"

    def model_post_init(self, _ctx) -> None:
        # LlamaIndex's OpenAI client reads OPENAI_API_KEY straight from the
        # process env, not from our config object. Re-export it here so that
        # downstream `OpenAI(...)` / `OpenAIEmbedding(...)` constructors that
        # don't take an explicit api_key argument can still find it.
        if self.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = self.openai_api_key

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "dataops-memory"

    # SeaweedFS (S3)
    seaweedfs_host: str = "localhost"
    seaweedfs_port: int = 8333
    seaweedfs_bucket: str = "dataops-lake"

    # MongoDB
    mongo_host: str = "localhost"
    mongo_port: int = 27017
    mongo_db: str = "dataops"

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 50

    @property
    def s3_endpoint_url(self) -> str:
        return f"http://{self.seaweedfs_host}:{self.seaweedfs_port}"

    @property
    def mongo_uri(self) -> str:
        return f"mongodb://{self.mongo_host}:{self.mongo_port}"
