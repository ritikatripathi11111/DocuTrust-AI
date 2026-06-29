"""Embedding service.

Generates dense vector embeddings for text chunks and queries. The service has a
pluggable provider model:

- `local` (default in the sandbox): a deterministic, dimension-stable hash
  embedding. It is NOT a semantic model, but it is fully deterministic, fast,
  has no external dependencies, and produces stable vectors that exercise the
  full vector-search + grading pipeline end to end. The interface is identical
  to a real embedding provider, so swapping in OpenAI / Cohere / a local
  sentence-transformers model later is a one-line config change.
- `openai`: placeholder provider that calls the OpenAI embeddings endpoint when
  `OPENAI_API_KEY` is configured. Implemented but not active by default.

The contract every provider must satisfy: `embed_text(text) -> list[float]`
returning a vector of length `settings.embedding_dim` with values normalized to
unit length (so cosine similarity is a simple dot product).
"""
from __future__ import annotations

import hashlib
import math
import os
from typing import Protocol

import numpy as np

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingProvider(Protocol):
    """Interface every embedding provider must implement."""

    def embed_text(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class LocalHashEmbedding:
    """Deterministic hash-based embedding used as a local fallback.

    The embedding is built by hashing each token into one of `dim` buckets and
    accumulating signed contributions, then L2-normalizing the result. This
    gives:
      * determinism (same text -> same vector),
      * stability across restarts (no random seed),
      * a meaningful cosine-similarity signal for overlapping tokens,
      * zero external dependencies.

    It is not a semantic model — chunks with shared vocabulary score higher
    than chunks with disjoint vocabulary, which is exactly what the retriever
    and grader need to demonstrate the full CRAG workflow.
    """

    def __init__(self, dim: int) -> None:
        self._dim = dim

    def _raw(self, text: str) -> np.ndarray:
        vec = np.zeros(self._dim, dtype=np.float32)
        tokens = self._tokenize(text)
        for token in tokens:
            if not token:
                continue
            h = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(h[:4], "little") % self._dim
            sign = 1.0 if (h[4] & 1) == 0 else -1.0
            magnitude = ((h[5] & 0x3F) + 1) / 64.0
            vec[bucket] += sign * magnitude
        return vec

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        normalized = "".join(c.lower() if c.isalnum() else " " for c in text)
        return [t for t in normalized.split() if len(t) > 1]

    def embed_text(self, text: str) -> list[float]:
        vec = self._raw(text)
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec = vec / norm
        return vec.astype(float).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]


class OpenAIEmbedding:
    """OpenAI text-embedding provider (active only when an API key is set).

    Implemented against the OpenAI embeddings REST endpoint via httpx so the
    backend does not need the openai SDK. Falls back to the local provider if
    the API key is missing or the call fails, and logs a warning.
    """

    def __init__(self, dim: int, model: str = "text-embedding-3-small") -> None:
        import httpx  # local import to avoid hard dependency at import time

        self._dim = dim
        self._model = model
        self._api_key = os.environ.get("OPENAI_API_KEY", "")
        self._httpx = httpx
        self._fallback = LocalHashEmbedding(dim)

    def embed_text(self, text: str) -> list[float]:
        if not self._api_key:
            logger.warning("OPENAI_API_KEY not set; falling back to local embedding")
            return self._fallback.embed_text(text)
        try:
            with self._httpx.Client(timeout=30.0) as client:
                response = client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"input": text, "model": self._model},
                )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
        except Exception as exc:  # noqa: BLE001 - fall back gracefully
            logger.warning("OpenAI embedding failed (%s); using local fallback", exc)
            return self._fallback.embed_text(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]


def get_embedding_provider() -> EmbeddingProvider:
    """Build the configured embedding provider."""
    provider = settings.embedding_provider.lower()
    if provider == "openai":
        return OpenAIEmbedding(dim=settings.embedding_dim)
    if provider == "local":
        return LocalHashEmbedding(dim=settings.embedding_dim)
    logger.warning("Unknown embedding provider '%s'; defaulting to local", provider)
    return LocalHashEmbedding(dim=settings.embedding_dim)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity for two equal-length vectors (a and b are assumed
    L2-normalized by the embedding providers, but we re-normalize defensively)."""
    arr_a = np.asarray(a, dtype=np.float32)
    arr_b = np.asarray(b, dtype=np.float32)
    if arr_a.shape != arr_b.shape:
        return 0.0
    na = float(np.linalg.norm(arr_a))
    nb = float(np.linalg.norm(arr_b))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(arr_a, arr_b) / (na * nb))
