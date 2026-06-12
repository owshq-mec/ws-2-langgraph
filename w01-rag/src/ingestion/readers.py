"""Source readers for the Memory ingestion pipeline.

SeaweedFS: pulls every object from the data lake bucket as a Document.
MongoDB: pulls the last 24h of event_logs and user_activity as Documents.

Each reader exposes `load_data() -> list[Document]`. Connection failures are
logged and yield an empty list — the pipeline can still run with what's
available from other sources.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from llama_index.core.schema import Document
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from src.ingestion.config import IngestionConfig

log = logging.getLogger(__name__)

__all__ = ["SeaweedFSReader", "MongoDBReader"]

# Object keys with these suffixes are decoded as UTF-8 text.
_TEXT_SUFFIXES = (".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".log")


class SeaweedFSReader:
    """Loads every object in the data lake bucket as a Document."""

    def __init__(self, config: IngestionConfig) -> None:
        self.config = config

    def _client(self):
        return boto3.client(
            "s3",
            endpoint_url=self.config.s3_endpoint_url,
            aws_access_key_id="any",
            aws_secret_access_key="any",
            region_name="us-east-1",
            config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def load_data(self) -> list[Document]:
        docs: list[Document] = []
        try:
            s3 = self._client()
            paginator = s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.config.seaweedfs_bucket):
                for obj in page.get("Contents", []) or []:
                    key = obj["Key"]
                    if not key.lower().endswith(_TEXT_SUFFIXES):
                        log.info("SeaweedFS: skipping non-text object %s", key)
                        continue
                    body = s3.get_object(Bucket=self.config.seaweedfs_bucket, Key=key)["Body"].read()
                    try:
                        text = body.decode("utf-8")
                    except UnicodeDecodeError:
                        log.warning("SeaweedFS: cannot decode %s as UTF-8, skipping", key)
                        continue

                    file_type = key.rsplit(".", 1)[-1].lower() if "." in key else "unknown"
                    last_modified: datetime = obj.get("LastModified") or datetime.now(timezone.utc)
                    docs.append(
                        Document(
                            doc_id=f"seaweedfs::{key}",
                            text=text,
                            metadata={
                                "source_type": "seaweedfs",
                                "file_name": key,
                                "file_type": file_type,
                                "upload_date": last_modified.isoformat(),
                            },
                        )
                    )
        except (BotoCoreError, ClientError, OSError) as exc:
            log.warning("SeaweedFS read failed: %s — returning %d documents loaded so far", exc, len(docs))
        log.info("SeaweedFS: loaded %d document(s)", len(docs))
        return docs


class MongoDBReader:
    """Loads the last 24h of event_logs and user_activity as Documents."""

    def __init__(self, config: IngestionConfig, window_hours: int = 24) -> None:
        self.config = config
        self.window_hours = window_hours

    def _client(self) -> MongoClient:
        return MongoClient(self.config.mongo_uri, serverSelectionTimeoutMS=5000)

    @staticmethod
    def _event_log_to_doc(row: dict[str, Any]) -> Document:
        ts = row.get("timestamp")
        ts_s = ts.isoformat() if isinstance(ts, datetime) else str(ts)
        text = (
            f"[{ts_s}] pipeline={row.get('pipeline_name')} "
            f"status={row.get('status')} severity={row.get('severity')} "
            f"duration_seconds={row.get('duration_seconds')} "
            f"records_processed={row.get('records_processed')}"
        )
        err = row.get("error_message")
        if err:
            text += f"\nerror: {err}"
        return Document(
            doc_id=f"mongo::event_logs::{row['_id']}",
            text=text,
            metadata={
                "source_type": "mongodb",
                "collection": "event_logs",
                "pipeline_name": row.get("pipeline_name"),
                "status": row.get("status"),
                "severity": row.get("severity"),
                "timestamp": ts_s,
            },
        )

    @staticmethod
    def _user_activity_to_doc(row: dict[str, Any]) -> Document:
        ts = row.get("timestamp")
        ts_s = ts.isoformat() if isinstance(ts, datetime) else str(ts)
        meta_str = ", ".join(f"{k}={v}" for k, v in (row.get("metadata") or {}).items())
        text = (
            f"[{ts_s}] user={row.get('user_id')} action={row.get('action')} "
            f"session={row.get('session_id')}"
        )
        if meta_str:
            text += f" | {meta_str}"
        return Document(
            doc_id=f"mongo::user_activity::{row['_id']}",
            text=text,
            metadata={
                "source_type": "mongodb",
                "collection": "user_activity",
                "action": row.get("action"),
                "user_id": row.get("user_id"),
                "timestamp": ts_s,
            },
        )

    def load_data(self) -> list[Document]:
        docs: list[Document] = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.window_hours)
        client = None
        try:
            client = self._client()
            client.admin.command("ping")
            db = client[self.config.mongo_db]

            for row in db["event_logs"].find({"timestamp": {"$gte": cutoff}}):
                docs.append(self._event_log_to_doc(row))
            for row in db["user_activity"].find({"timestamp": {"$gte": cutoff}}):
                docs.append(self._user_activity_to_doc(row))
        except (PyMongoError, OSError) as exc:
            log.warning("MongoDB read failed: %s — returning %d documents loaded so far", exc, len(docs))
        finally:
            if client is not None:
                client.close()
        log.info("MongoDB: loaded %d document(s) (window=%dh)", len(docs), self.window_hours)
        return docs
