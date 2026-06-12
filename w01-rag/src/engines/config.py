"""Shared configuration for the Ledger / Memory / Brain query engines.

Reads .env via pydantic-settings. Defaults match the local Docker Compose
stack so a developer can instantiate any engine without env setup beyond
OPENAI_API_KEY.
"""
from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["EngineConfig"]


class EngineConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # LLM / embeddings
    openai_api_key: str
    llm_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"

    # PostgreSQL (Ledger)
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "dataops"
    postgres_user: str = "dataops"
    postgres_password: str = "dataops123"

    # Qdrant (Memory)
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "dataops-memory"

    # Neo4j (Brain)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "dataops123"

    # Query budget
    query_timeout_seconds: float = 30.0

    def model_post_init(self, _ctx) -> None:
        # LlamaIndex's OpenAI client reads OPENAI_API_KEY from the process
        # env, not from this config object. Re-export it so downstream
        # constructors that don't take an explicit api_key can find it.
        if self.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = self.openai_api_key

    @property
    def postgres_connection_string(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
