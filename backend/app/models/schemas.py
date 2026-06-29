"""Pydantic models (DTOs) for the DocuTrust API surface."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# --- Clients ---


class ClientCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    industry: Optional[str] = None
    region: Optional[str] = None


class ClientUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    industry: Optional[str] = None
    region: Optional[str] = None


class ClientOut(BaseModel):
    id: str
    name: str
    industry: Optional[str] = None
    region: Optional[str] = None
    created_at: datetime


# --- Documents ---


class DocumentOut(BaseModel):
    id: str
    client_id: str
    filename: str
    mime_type: str
    size_bytes: int
    page_count: int
    status: str
    section_index: list[Any]
    created_at: datetime


class DocumentChunkOut(BaseModel):
    id: str
    document_id: str
    chunk_index: int
    page_number: int
    section: Optional[str] = None
    content: str
    token_count: int


# --- CRAG pipeline ---


class Citation(BaseModel):
    """A single citation backing a claim in the final answer."""

    chunk_id: str
    document_id: str
    filename: str
    page_number: int
    section: Optional[str] = None
    snippet: str
    score: float


class AgentStep(BaseModel):
    """One step of the CRAG pipeline trace."""

    agent: str
    step: str
    status: Literal["running", "completed", "failed"]
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    input: Optional[Any] = None
    output: Optional[Any] = None
    decision: Optional[str] = None
    detail: Optional[str] = None


class QueryRequest(BaseModel):
    client_id: str
    query: str = Field(..., min_length=1, max_length=2000)
    document_ids: Optional[list[str]] = None


class QueryResponse(BaseModel):
    trace_id: str
    client_id: str
    query: str
    answer: str
    citations: list[Citation]
    steps: list[AgentStep]
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None


class TraceOut(BaseModel):
    id: str
    client_id: str
    query: str
    answer: Optional[str] = None
    citations: list[Any]
    steps: list[Any]
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None


# --- Health ---


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    services: dict[str, str]
