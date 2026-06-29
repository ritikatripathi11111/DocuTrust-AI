"""Shared state object passed between CRAG agents.

The state is a typed dict-like object that flows through the LangGraph-style
orchestrator. Each agent reads from it, performs its work, and writes results
back. Keeping the state explicit makes the pipeline easy to reason about and
test, and makes the step-by-step trace logs trivially correct.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class RetrievedChunk:
    """A chunk returned by the retriever, with its similarity score."""

    chunk_id: str
    document_id: str
    filename: str
    page_number: int
    section: Optional[str]
    content: str
    token_count: int
    score: float


@dataclass
class GradedChunk:
    """A chunk after relevance grading."""

    chunk: RetrievedChunk
    relevance: float  # 0..1, from the grader
    label: str  # "relevant" | "not_relevant" | "ambiguous"
    grader: str  # which grader produced the score


@dataclass
class WebResult:
    """A web search fallback result."""

    title: str
    url: str
    snippet: str
    score: float


@dataclass
class Citation:
    """A validated citation backing the final answer."""

    chunk_id: str
    document_id: str
    filename: str
    page_number: int
    section: Optional[str]
    snippet: str
    score: float


@dataclass
class AgentStepRecord:
    """One step in the trace log."""

    agent: str
    step: str
    status: str  # "running" | "completed" | "failed"
    started_at: str
    finished_at: Optional[str] = None
    duration_ms: Optional[int] = None
    input: Optional[Any] = None
    output: Optional[Any] = None
    decision: Optional[str] = None
    detail: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "step": self.step,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "input": self.input,
            "output": self.output,
            "decision": self.decision,
            "detail": self.detail,
        }


@dataclass
class CragState:
    """Mutable state that flows through the CRAG pipeline."""

    query: str
    client_id: str
    document_ids: Optional[list[str]] = None

    # Retriever outputs
    retrieved: list[RetrievedChunk] = field(default_factory=list)

    # Grader outputs
    graded: list[GradedChunk] = field(default_factory=list)
    relevant_count: int = 0
    needs_web_search: bool = False

    # Query rewrite output
    rewritten_query: Optional[str] = None

    # Web search outputs
    web_results: list[WebResult] = field(default_factory=list)

    # Generation
    answer: str = ""
    citations: list[Citation] = field(default_factory=list)

    # Trace
    steps: list[AgentStepRecord] = field(default_factory=list)
    status: str = "running"
    error: Optional[str] = None

    def record_step(self, step: AgentStepRecord) -> None:
        self.steps.append(step)

    def start_step(self, agent: str, step: str, *, input_: Any = None) -> AgentStepRecord:
        record = AgentStepRecord(
            agent=agent,
            step=step,
            status="running",
            started_at=datetime.now(timezone.utc).isoformat(),
            input=input_,
        )
        self.steps.append(record)
        return record

    def finish_step(
        self,
        record: AgentStepRecord,
        *,
        status: str = "completed",
        output: Any = None,
        decision: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> None:
        record.status = status
        record.finished_at = datetime.now(timezone.utc).isoformat()
        started = datetime.fromisoformat(record.started_at)
        finished = datetime.fromisoformat(record.finished_at)
        record.duration_ms = int((finished - started).total_seconds() * 1000)
        record.output = output
        record.decision = decision
        record.detail = detail

    def to_trace_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "answer": self.answer,
            "citations": [c.__dict__ for c in self.citations],
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status,
        }
