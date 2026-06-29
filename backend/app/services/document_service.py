"""Document ingestion service.

Coordinates the full upload pipeline:
  1. Persist a `documents` row with status `pending`.
  2. Parse the PDF into structural chunks.
  3. Embed every chunk.
  4. Insert `document_chunks` rows with their embeddings.
  5. Update the `documents` row with page count, section index, and status `ready`.

The service is intentionally async-friendly: each step is a separate method so
the LangGraph pipeline and the upload router can reuse them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId
from pymongo.database import Database

from app.core.logging import get_logger
from app.core.mongodb_client import get_database
from app.services.embedding_service import (
    EmbeddingProvider,
    get_embedding_provider,
)
from app.services.pdf_service import parse_pdf_bytes

logger = get_logger(__name__)
print("******** Mongo DocumentService Loaded ********")

class DocumentIngestionError(RuntimeError):
    """Raised when document ingestion fails."""


class DocumentService:
    """High-level document ingestion and retrieval operations."""

    def __init__(
        self,
        db: Database | None = None,
        embedder: EmbeddingProvider | None = None,
    ) -> None:
        self._db = get_database() if db is None else db
        self._embedder = embedder or get_embedding_provider()

    # ------------------------------------------------------------------
    # Document Ingestion
    # ------------------------------------------------------------------

    def ingest(
        self,
        client_id: str,
        filename: str,
        content: bytes,
    ) -> dict[str, Any]:

        if not content:
            raise DocumentIngestionError("empty file")

        if not filename.lower().endswith(".pdf"):
            raise DocumentIngestionError(
                "only PDF files are supported"
            )

        document = {
            "client_id": client_id,
            "filename": filename,
            "mime_type": "application/pdf",
            "size_bytes": len(content),
            "page_count": 0,
            "status": "parsing",
            "section_index": [],
            "created_at": datetime.utcnow(),
        }

        result = self._db.documents.insert_one(document)

        document_id = str(result.inserted_id)

        try:
            parsed = parse_pdf_bytes(content)

        except Exception as exc:

            self._mark_failed(
                document_id,
                f"parse error: {exc}",
            )

            raise DocumentIngestionError(
                f"failed to parse pdf: {exc}"
            ) from exc

        if not parsed.chunks:

            self._db.documents.update_one(
                {
                    "_id": ObjectId(document_id)
                },
                {
                    "$set": {
                        "page_count": parsed.page_count,
                        "section_index": parsed.sections,
                        "status": "ready",
                    }
                },
            )

            return self.get_document(document_id)

        try:

            embeddings = self._embedder.embed_batch(
                [
                    chunk.content
                    for chunk in parsed.chunks
                ]
            )

        except Exception as exc:

            self._mark_failed(
                document_id,
                f"embedding error: {exc}",
            )

            raise DocumentIngestionError(
                f"failed to embed chunks: {exc}"
            ) from exc

        chunk_rows = [
            {
                "client_id": client_id,
                "document_id": document_id,
                "filename": filename,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
                "section": chunk.section,
                "content": chunk.content,
                "token_count": chunk.token_count,
                "embedding": embedding,
            }
            for chunk, embedding in zip(parsed.chunks, embeddings)
        ]

        batch_size = 25
        for start in range(0, len(chunk_rows), batch_size):

            batch = chunk_rows[start : start + batch_size]

            self._db.document_chunks.insert_many(batch)

        self._db.documents.update_one(
            {
                "_id": ObjectId(document_id)
            },
            {
                "$set": {
                    "page_count": parsed.page_count,
                    "section_index": parsed.sections,
                    "status": "ready",
                }
            },
        )

        return self.get_document(document_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _mark_failed(
        self,
        document_id: str,
        reason: str,
    ) -> None:

        logger.error("document %s failed: %s", document_id, reason)

        self._db.documents.update_one(
            {
                "_id": ObjectId(document_id)
            },
            {
                "$set": {
                    "status": f"failed: {reason[:200]}"
                }
            },
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_documents(
        self,
        client_id: str,
    ) -> list[dict[str, Any]]:

        rows = list(
            self._db.documents.find(
                {
                    "client_id": client_id
                }
            ).sort(
                "created_at",
                -1,
            )
        )

        documents = []

        for row in rows:

            row["id"] = str(row["_id"])

            row.pop("_id", None)

            documents.append(row)

        return documents

    def get_document(
        self,
        document_id: str,
    ) -> dict[str, Any]:

        row = self._db.documents.find_one(
            {
                "_id": ObjectId(document_id)
            }
        )

        if not row:

            raise DocumentIngestionError(
                f"document {document_id} not found"
            )

        row["id"] = str(row["_id"])

        row.pop("_id", None)

        return row

    def delete_document(
        self,
        document_id: str,
    ) -> None:

        self._db.documents.delete_one(
            {
                "_id": ObjectId(document_id)
            }
        )

        self._db.document_chunks.delete_many(
            {
                "document_id": document_id
            }
        )

    def list_chunks(
        self,
        document_id: str,
    ) -> list[dict[str, Any]]:

        rows = list(
            self._db.document_chunks.find(
                {
                    "document_id": document_id
                }
            ).sort(
                "chunk_index",
                1,
            )
        )

        chunks = []

        for row in rows:

            row["id"] = str(row["_id"])

            row.pop("_id", None)

            chunks.append(row)

        return chunks