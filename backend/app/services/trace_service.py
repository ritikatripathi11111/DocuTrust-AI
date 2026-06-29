"""Interaction trace service (MongoDB)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from bson import ObjectId
from pymongo.database import Database

from app.core.logging import get_logger
from app.core.mongodb_client import get_database

logger = get_logger(__name__)


class TraceService:
    """CRUD operations for interaction traces."""

    def __init__(
        self,
        db: Database | None = None,
    ) -> None:
        self._db = get_database() if db is None else db

    def create_trace(
        self,
        client_id: str,
        query: str,
    ) -> dict[str, Any]:

        doc = {
            "client_id": client_id,
            "query": query,
            "answer": None,
            "citations": [],
            "steps": [],
            "status": "running",
            "created_at": datetime.utcnow(),
            "completed_at": None,
        }

        result = self._db.interaction_traces.insert_one(doc)

        doc["id"] = str(result.inserted_id)
        doc.pop("_id", None)

        return doc

    def get_trace(
        self,
        trace_id: str,
    ) -> Optional[dict[str, Any]]:

        row = self._db.interaction_traces.find_one(
            {
                "_id": ObjectId(trace_id)
            }
        )

        if not row:
            return None

        row["id"] = str(row["_id"])
        row.pop("_id", None)

        return row

    def list_traces(
        self,
        client_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:

        rows = list(
            self._db.interaction_traces.find(
                {
                    "client_id": client_id
                }
            )
            .sort("created_at", -1)
            .limit(limit)
        )

        traces = []

        for row in rows:
            row["id"] = str(row["_id"])
            row.pop("_id", None)
            traces.append(row)

        return traces

    def append_step(
        self,
        trace_id: str,
        step: dict[str, Any],
    ) -> None:

        self._db.interaction_traces.update_one(
            {
                "_id": ObjectId(trace_id)
            },
            {
                "$push": {
                    "steps": step
                }
            },
        )

    def update_steps(
        self,
        trace_id: str,
        steps: list[dict[str, Any]],
    ) -> None:

        self._db.interaction_traces.update_one(
            {
                "_id": ObjectId(trace_id)
            },
            {
                "$set": {
                    "steps": steps
                }
            },
        )

    def update(
        self,
        trace_id: str,
        **values: Any,
    ) -> None:

        self._db.interaction_traces.update_one(
            {
                "_id": ObjectId(trace_id)
            },
            {
                "$set": values
            },
        )

    def complete_trace(
        self,
        trace_id: str,
        *,
        answer: str,
        citations: list[dict[str, Any]],
        status: str = "completed",
    ) -> None:

        self._db.interaction_traces.update_one(
            {
                "_id": ObjectId(trace_id)
            },
            {
                "$set": {
                    "answer": answer,
                    "citations": citations,
                    "status": status,
                    "completed_at": datetime.utcnow(),
                }
            },
        )

    def fail_trace(
        self,
        trace_id: str,
        reason: str,
    ) -> None:

        self._db.interaction_traces.update_one(
            {
                "_id": ObjectId(trace_id)
            },
            {
                "$set": {
                    "status": "failed",
                    "answer": f"Pipeline failed: {reason}",
                    "completed_at": datetime.utcnow(),
                }
            },
        )