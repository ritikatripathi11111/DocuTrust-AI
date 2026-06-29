"""DocuTrust FastAPI application entry point."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.models.schemas import HealthOut
from app.routers import clients, documents, query

configure_logging()
logger = get_logger(__name__)

app = FastAPI(
    title="DocuTrust CRAG Platform",
    description=(
        "Enterprise Corrective RAG platform with self-correction: retriever, "
        "relevance grader, query rewriter, web search fallback, and citation "
        "validation agents orchestrated as a LangGraph-style state machine."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(clients.router)
app.include_router(documents.router)
app.include_router(query.router)


@app.get("/api/health", response_model=HealthOut)
def health() -> HealthOut:
    services = {
    "mongodb": "ok" if settings.mongodb_uri else "missing",
    "embedder": settings.embedding_provider,
    "grader": "local" if settings.embedding_provider == "local" else "configured",
    "web_search": settings.web_search_provider,
    "llm": settings.llm_provider,
}
    status = "ok" if services["mongodb"] == "ok" else "degraded"
    return HealthOut(status=status, version="1.0.0", services=services)


@app.on_event("startup")
def on_startup() -> None:
    settings.ensure_upload_dir()
    logger.info("DocuTrust backend started on %s:%s", settings.host, settings.port)
    logger.info(
        "providers: embedder=%s grader=%s web=%s llm=%s",
        settings.embedding_provider,
        "cross_encoder" if settings.embedding_provider != "local" else "local",
        settings.web_search_provider,
        settings.llm_provider,
    )

@app.get("/test")
def test():
    print("TEST ROUTE HIT")
    return {"ok": True}