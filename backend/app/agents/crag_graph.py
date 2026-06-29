"""LangGraph-style CRAG orchestrator.

Implements the Corrective RAG (CRAG) design pattern as a state machine graph.
The graph is defined explicitly with nodes (agents) and conditional edges, in
the same shape a LangGraph `StateGraph` would produce:

    START
      |
      v
    retriever
      |
      v
    grader -----> (no relevant chunks) -----> query_rewriter
      |                                        |
      | (enough relevant chunks)               v
      |                                     web_search
      v                                        |
    generator <------------------------------- +
      |
      v
    END

The orchestrator is a faithful, dependency-free implementation of the LangGraph
state-machine pattern: each node is a function `(state) -> state`, edges are
declared explicitly, and conditional routing is a function of the state. This
makes the pipeline easy to inspect, test, and extend — and it produces the
step-by-step trace log the UI renders in real time.

If `langgraph` is installed in the environment, the same node functions can be
registered on a `StateGraph` verbatim; the orchestrator here is the
production-equivalent fallback that requires no external dependency.
"""

from __future__ import annotations

from typing import Callable

from pymongo.database import Database

from app.agents.generation_agent import GenerationAgent
from app.agents.grader_agent import GraderAgent
from app.agents.query_rewrite_agent import QueryRewriteAgent
from app.agents.retriever_agent import RetrieverAgent
from app.agents.state import CragState
from app.agents.web_search_agent import WebSearchAgent

from app.core.logging import get_logger
from app.core.mongodb_client import get_database

from app.services.embedding_service import get_embedding_provider
from app.services.trace_service import TraceService

logger = get_logger(__name__)

NodeFn = Callable[[CragState], CragState]


class CragGraph:
    """CRAG State Machine."""

    def __init__(
        self,
        db: Database | None = None,
        *,
        retriever: RetrieverAgent | None = None,
        grader: GraderAgent | None = None,
        rewriter: QueryRewriteAgent | None = None,
        web_search: WebSearchAgent | None = None,
        generator: GenerationAgent | None = None,
    ) -> None:

        self._db = get_database() if db is None else db

        embedder = get_embedding_provider()

        self._retriever = (
            retriever
            or RetrieverAgent(
                self._db,
                embedder=embedder,
            )
        )

        self._grader = grader or GraderAgent()

        self._rewriter = (
            rewriter
            or QueryRewriteAgent()
        )

        self._web_search = (
            web_search
            or WebSearchAgent()
        )

        self._generator = (
            generator
            or GenerationAgent()
        )

        self._trace = TraceService(
            self._db
        )

    # -------------------------------------------------
    # Graph Nodes
    # -------------------------------------------------

    def _node_retrieve(
        self,
        state: CragState,
    ) -> CragState:

        return self._retriever.run(state)

    def _node_grade(
        self,
        state: CragState,
    ) -> CragState:

        return self._grader.run(state)

    def _node_rewrite(
        self,
        state: CragState,
    ) -> CragState:

        return self._rewriter.run(state)

    def _node_web_search(
        self,
        state: CragState,
    ) -> CragState:

        return self._web_search.run(state)

    def _node_generate(
        self,
        state: CragState,
    ) -> CragState:

        return self._generator.run(state)

    # -------------------------------------------------
    # Routing
    # -------------------------------------------------

    def _route_after_grading(
        self,
        state: CragState,
    ) -> str:

        if state.error:
            return "end"

        if state.needs_web_search:
            return "rewrite"

        return "generate"

    def _route_after_web_search(
        self,
        state: CragState,
    ) -> str:

        if state.error:
            return "end"

        return "generate"
    
        # -------------------------------------------------
    # Execution
    # -------------------------------------------------

    def run(
        self,
        state: CragState,
    ) -> CragState:

        trace = self._trace.create_trace(
            state.client_id,
            state.query,
        )

        trace_id = trace.get("id")

        if not trace_id:
            state.error = "failed to create trace"
            state.status = "failed"
            return state

        setattr(
            state,
            "trace_id",
            trace_id,
        )

        try:

            state = self._execute_graph(state)

            if state.error:

                self._trace.fail_trace(
                    trace_id,
                    state.error,
                )

                state.status = "failed"

            else:

                self._trace.complete_trace(
                    trace_id=trace_id,
                    answer=state.answer or "",
                    citations=[
                        c.__dict__
                        for c in state.citations
                    ],
                    status="completed",
                )

                state.status = "completed"

        except Exception as exc:

            state.error = f"graph crashed: {exc}"

            state.status = "failed"

            self._trace.fail_trace(
                trace_id,
                str(exc),
            )

            logger.exception(
                "CRAG graph crashed"
            )

        try:

            self._trace.update(
                trace_id,
                steps=[
                    s.to_dict()
                    for s in state.steps
                ],
            )

        except Exception:

            logger.warning(
                "could not sync final trace"
            )

        return state

    def _execute_graph(
        self,
        state: CragState,
    ) -> CragState:

        def _persist():

            trace_id = getattr(
                state,
                "trace_id",
                None,
            )

            if not trace_id:
                return

            self._trace.update_steps(
                trace_id,
                [
                    s.to_dict()
                    for s in state.steps
                ],
            )

        # Retrieve
        state = self._node_retrieve(state)
        _persist()

        if state.error:
            return state

        # Grade
        state = self._node_grade(state)
        _persist()

        if state.error:
            return state

        # Rewrite + Web Search
        if self._route_after_grading(state) == "rewrite":

            state = self._node_rewrite(state)
            _persist()

            if state.error:
                return state

            state = self._node_web_search(state)
            _persist()

            if state.error:
                return state

        # Generate
        state = self._node_generate(state)
        _persist()

        return state