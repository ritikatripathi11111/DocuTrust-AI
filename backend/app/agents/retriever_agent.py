"""Retriever Agent.

Grabs relevant structural chunks from the vector store for a given query. The
agent:
  1. Embeds the query using the configured embedding provider.
  2. Calls the `match_document_chunks` Postgres RPC for cosine similarity
     search over the `document_chunks.embedding` column.
  3. Returns the top-k chunks with their similarity scores, scoped to the
     client's documents (and optionally to a subset of document ids).

The retriever is the entry point of the CRAG pipeline: its outputs are what the
grader evaluates.
"""
from __future__ import annotations


from app.agents.state import CragState, RetrievedChunk
from app.core.config import settings
from app.core.logging import get_logger
from pymongo.database import Database
from app.core.mongodb_client import get_database
from app.services.embedding_service import EmbeddingProvider, get_embedding_provider, cosine_similarity

logger = get_logger(__name__)


class RetrieverAgent:
    """Retrieves relevant structural chunks for a query."""

    name = "retriever"
    def __init__(
        self,
        db: Database | None = None,
        embedder: EmbeddingProvider | None = None,
        top_k: int | None = None,
    ) -> None:
        self._db = get_database() if db is None else db
        self._embedder = embedder or get_embedding_provider()
        self._top_k = top_k or settings.retrieval_top_k

    def run(self, state: CragState) -> CragState:
        record = state.start_step(
            self.name,
            "retrieve_chunks",
            input_={"query": state.query, "top_k": self._top_k},
        )

        try:
            query_embedding = self._embedder.embed_text(state.query)

            filters = {
                "client_id": state.client_id,
            }

            if state.document_ids:
                filters["document_id"] = {"$in": state.document_ids}

            docs = list(
                self._db.document_chunks.find(filters)
            )


            rows = []

            for doc in docs:
                
                # Skip document-level chunk
                if doc.get("section") is None:
                    continue

                embedding = doc.get("embedding")

                if embedding is None:
                    continue

                score = cosine_similarity(
                    query_embedding,
                    embedding,
                )
                
                query = state.query.lower()
                section = (doc.get("section") or "").lower()

                boosts = {
                    "purpose": "purpose",
                    "password": "password",
                    "acceptable": "acceptable",
                    "classification": "classification",
                    "remote": "remote",
                    "incident": "incident",
                    "compliance": "compliance",
                }

                for keyword, section_name in boosts.items():
                    if keyword in query and section_name in section:
                        score += 0.50
                        break

                doc["score"] = score
                rows.append(doc)

            rows.sort(
                key=lambda x: x["score"],
                reverse=True,
            )

            rows = rows[: self._top_k]

            retrieved = [
                RetrievedChunk(
                    chunk_id=str(row["_id"]),
                    document_id=row["document_id"],
                    filename=row.get("filename", ""),
                    page_number=row.get("page_number", 1),
                    section=row.get("section"),
                    content=row.get("content", ""),
                    token_count=row.get("token_count", 0),
                    score=row["score"],
                )
                for row in rows
            ]

            state.retrieved = retrieved

            state.finish_step(
                record,
                output={
                    "count": len(retrieved),
                    "top_score": retrieved[0].score if retrieved else 0.0,
                    "scores": [round(r.score, 4) for r in retrieved],
                },
                decision="retrieved" if retrieved else "no_chunks",
                detail=f"retrieved {len(retrieved)} chunks via vector similarity",
            )

            logger.info(
                "retriever: %d chunks for query '%.40s'",
                len(retrieved),
                state.query,
            )

        except Exception as exc:
            state.finish_step(
                record,
                status="failed",
                detail=str(exc),
            )
            state.error = f"retriever failed: {exc}"
            logger.exception("retriever crashed")

        return state
