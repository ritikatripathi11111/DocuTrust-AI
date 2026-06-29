"""Query router: run the CRAG pipeline and return validated answers."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.agents.crag_graph import CragGraph
from app.agents.state import CragState
from app.core.logging import get_logger
from app.models.schemas import QueryRequest, QueryResponse, TraceOut
from app.services.trace_service import TraceService

router = APIRouter(prefix="/api/query", tags=["query"])
logger = get_logger(__name__)


@router.post("", response_model=QueryResponse)
def run_query(payload: QueryRequest) -> QueryResponse:

    state = CragState(
        query=payload.query,
        client_id=payload.client_id,
        document_ids=payload.document_ids,
    )

    graph = CragGraph()

    state = graph.run(state)

    trace_id = getattr(state, "trace_id", "")

    if not trace_id:
        raise HTTPException(
            status_code=500,
            detail="trace was not created",
        )

    trace = TraceService().get_trace(trace_id) or {}

    return QueryResponse(
        trace_id=trace_id,
        client_id=payload.client_id,
        query=state.query,
        answer=state.answer or "",
        citations=[c.__dict__ for c in state.citations],
        steps=[s.to_dict() for s in state.steps],
        status=state.status,
        created_at=trace.get("created_at"),
        completed_at=trace.get("completed_at"),
    )


@router.get("/traces/{client_id}", response_model=list[TraceOut])
def list_traces(
    client_id: str,
    limit: int = 50,
) -> list[TraceOut]:

    rows = TraceService().list_traces(
        client_id,
        limit=limit,
    )

    return [
        TraceOut(
            id=row["id"],
            client_id=row["client_id"],
            query=row["query"],
            answer=row.get("answer"),
            citations=row.get("citations") or [],
            steps=row.get("steps") or [],
            status=row["status"],
            created_at=row["created_at"],
            completed_at=row.get("completed_at"),
        )
        for row in rows
    ]


@router.get("/trace/{trace_id}", response_model=TraceOut)
def get_trace(trace_id: str) -> TraceOut:

    row = TraceService().get_trace(trace_id)

    if not row:
        raise HTTPException(
            status_code=404,
            detail="trace not found",
        )

    return TraceOut(
        id=row["id"],
        client_id=row["client_id"],
        query=row["query"],
        answer=row.get("answer"),
        citations=row.get("citations") or [],
        steps=row.get("steps") or [],
        status=row["status"],
        created_at=row["created_at"],
        completed_at=row.get("completed_at"),
    )