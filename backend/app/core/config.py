"""Application configuration loaded from environment variables.

All settings have sensible defaults so the service runs out of the box in the
sandboxed build environment, while still allowing overrides via environment
variables or a local .env file.
"""
from __future__ import annotations

import os
from dotenv import load_dotenv
from dataclasses import dataclass, field
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parents[3]
load_dotenv(ROOT_DIR / ".env")


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


@dataclass
class Settings:
    """Runtime configuration for the DocuTrust backend."""

    # --- Server ---
    host: str = field(default_factory=lambda: _env("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(_env("PORT", "8001")))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            origin.strip()
            for origin in _env("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(
                ","
            )
            if origin.strip()
        )
    )

    # --- MongoDB ---
    mongodb_uri: str = field(default_factory=lambda: _env("MONGODB_URI", ""))
    mongodb_database: str = field(default_factory=lambda: _env("MONGODB_DATABASE", "docutrust"))

    # --- CRAG pipeline tuning ---
    # Number of structural chunks the retriever pulls per query.
    retrieval_top_k: int = field(default_factory=lambda: int(_env("RETRIEVAL_TOP_K", "6")))
    # Cosine similarity threshold below which a chunk is considered "not relevant"
    # by the lightweight grader when no cross-encoder is available.
    grading_similarity_threshold: float = field(
        default_factory=lambda: float(_env("GRADING_SIMILARITY_THRESHOLD", "0.30"))
    )
    # Minimum number of chunks that must be graded relevant to skip the web fallback.
    min_relevant_chunks: int = field(default_factory=lambda: int(_env("MIN_RELEVANT_CHUNKS", "1")))
    # Maximum chunks to keep in the final context after grading + optional web results.
    max_context_chunks: int = field(default_factory=lambda: int(_env("MAX_CONTEXT_CHUNKS", "5")))
    # Token budget for the final synthesized answer.
    max_answer_tokens: int = field(default_factory=lambda: int(_env("MAX_ANSWER_TOKENS", "512")))

    # --- Embeddings ---
    # Embedding dimension must match the vector(N) column in Supabase.
    embedding_dim: int = field(default_factory=lambda: int(_env("EMBEDDING_DIM", "1536")))
    # When no external embedding provider is configured, the service falls back to
    # a deterministic hash-based embedding so the pipeline remains fully functional.
    embedding_provider: str = field(default_factory=lambda: _env("EMBEDDING_PROVIDER", "local"))

    # --- Web search fallback ---
    web_search_provider: str = field(default_factory=lambda: _env("WEB_SEARCH_PROVIDER", "local"))
    web_search_max_results: int = field(default_factory=lambda: int(_env("WEB_SEARCH_MAX_RESULTS", "3")))

    # --- Storage ---
    # Directory for transient PDF processing. Files are removed after parsing.
    upload_dir: Path = field(
        default_factory=lambda: Path(_env("UPLOAD_DIR", "/tmp/docutrust_uploads"))
    )

    # --- LLM generation ---
    # When no LLM provider is configured, a deterministic extractive generator
    # assembles the answer from the graded chunks with strict citations.
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "local"))

    def ensure_upload_dir(self) -> Path:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        return self.upload_dir


settings = Settings()
print("=" * 50)
print("MONGODB_URI:", "SET" if settings.mongodb_uri else "NOT SET")
print("DATABASE:", settings.mongodb_database)
print("=" * 50)