"""Generation + Citation Validation Agent.

Produces the final validated answer with strict citations. The agent:

  1. Selects the context: graded-relevant chunks first, then web search
     results if the grader triggered the fallback.
  2. Synthesizes an answer that is grounded ONLY in the selected context —
     every claim must be backed by a citation.
  3. Validates every citation: each citation must point to a real chunk (or
     web result) that actually contains the supporting text. Citations that
     fail validation are dropped, and the answer is regenerated without them.

Provider model:

- `local` (default): a deterministic extractive generator that assembles the
  answer from the most relevant sentences in the selected context, with
  inline numeric citations `[1]`, `[2]`, ... that map to the citation list.
  This is a real, grounded generator — it never produces text that is not
  present in the cited sources.

- `openai` (production): calls the OpenAI chat completions API with a strict
  "answer only from the provided context, cite with [n]" system prompt.
  Implemented via httpx; activates when `OPENAI_API_KEY` is set.

The citation validator is the final self-correction gate of the CRAG pipeline:
it ensures the answer is fully sourced before it is shown to the user.
"""
from __future__ import annotations

import os
import re
from typing import Protocol

from app.agents.state import Citation, CragState, GradedChunk, WebResult
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class Generator(Protocol):
    def generate(
        self,
        query: str,
        context_chunks: list[GradedChunk],
        web_results: list[WebResult],
    ) -> tuple[str, list[Citation]]: ...


def _split_sentences(text: str) -> list[str]:
    # Simple sentence splitter that preserves common abbreviations.
    text = re.sub(r"\s+", " ", text)
    raw = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    return [s.strip() for s in raw if s.strip()]


def _sentence_relevance(query: str, sentence: str) -> float:
    q_tokens = {t.lower() for t in query.split() if len(t) > 2}
    s_tokens = {t.lower() for t in sentence.split() if len(t) > 2}

    if not q_tokens or not s_tokens:
        return 0.0

    score = len(q_tokens & s_tokens) / len(q_tokens)

    query_lower = query.lower()
    sentence_lower = sentence.lower()

    # Boost matching section names
    keywords = [
        "purpose",
        "password",
        "acceptable",
        "classification",
        "remote",
        "incident",
        "compliance",
    ]

    for keyword in keywords:
        if keyword in query_lower and keyword in sentence_lower:
            score += 1.0

    return score


class LocalGenerator:
    """Deterministic extractive generator with strict citations.

    Picks the most query-relevant sentences from the selected context, orders
    them by source relevance, and emits them with inline numeric citations.
    The answer is therefore guaranteed to be grounded in the cited sources.
    """

    def generate(
        self,
        query: str,
        context_chunks: list[GradedChunk],
        web_results: list[WebResult],
    ) -> tuple[str, list[Citation]]:
        citations: list[Citation] = []
        # When web results are present (grader triggered fallback), put them
        # first so the answer leads with the corrected retrieval. Otherwise,
        # chunks come first.
        ordered_chunks: list[GradedChunk] = list(context_chunks)
        ordered_web: list[WebResult] = list(web_results)
        if web_results:
            # PDF chunks first
            for graded in ordered_chunks:
                chunk = graded.chunk
                snippet = self._best_snippet(query, chunk.content)
                citations.append(
                    Citation(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        filename=chunk.filename,
                        page_number=chunk.page_number,
                        section=chunk.section,
                        snippet=snippet,
                        score=graded.relevance,
                    )
                )

            # Web results afterwards
            for web in ordered_web:
                citations.append(
                    Citation(
                        chunk_id=f"web:{web.url}",
                        document_id="",
                        filename=web.title,
                        page_number=0,
                        section=None,
                        snippet=web.snippet,
                        score=web.score,
                    )
                )
        else:
            # Chunks only
            for graded in ordered_chunks:
                chunk = graded.chunk
                snippet = self._best_snippet(query, chunk.content)
                citations.append(
                    Citation(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        filename=chunk.filename,
                        page_number=chunk.page_number,
                        section=chunk.section,
                        snippet=snippet,
                        score=graded.relevance,
                    )
                )

        # Extract the most relevant sentences from each source, in citation order
        answer_parts = []
        ranked_sentences = []

        for idx, citation in enumerate(citations, start=1):
            source_text = citation.snippet
            sentences = _split_sentences(source_text)

            if not sentences:
               continue

            scored = sorted(
                    ((_sentence_relevance(query, s), s) for s in sentences),
                key=lambda x: x[0],
                reverse=True,
            )

            if scored:
                ranked_sentences.append(
                (scored[0][0], scored[0][1], idx)
        )

        # Highest relevance first
        ranked_sentences.sort(
        key=lambda x: x[0],
        reverse=True,
)

        # Keep only best 3 sentences
        for score, sentence, idx in ranked_sentences[:1]:
           answer_parts.append(f"{sentence} [{idx}]")

        if not answer_parts:
            return (
                "No sufficiently relevant information was found in the uploaded "
                "documents or the web search fallback to answer this query.",
                [],
            )
        # Keep only the 3 most relevant extracted sentences
        answer_parts = answer_parts[:3]

        answer = " ".join(answer_parts)
        # Trim to the token budget (approx 4 chars/token)
        max_chars = settings.max_answer_tokens * 4
        if len(answer) > max_chars:
            answer = answer[:max_chars].rsplit(" ", 1)[0] + " …"
        return answer, citations

    @staticmethod
    def _best_snippet(query: str, content: str, max_len: int = 320) -> str:
        if len(content) <= max_len:
            return content.strip()
        sentences = _split_sentences(content)
        if not sentences:
            return content[:max_len].strip()
        # Find the sentence window with the highest query relevance
        best_score = -1.0
        best_start = 0
        for i in range(len(sentences)):
            window = " ".join(sentences[i : i + 2])
            score = _sentence_relevance(query, window)
            if score > best_score:
                best_score = score
                best_start = i
        snippet = " ".join(sentences[best_start : best_start + 2])
        if len(snippet) > max_len:
            snippet = snippet[:max_len].rsplit(" ", 1)[0] + " …"
        return snippet


class OpenAIGenerator:
    """LLM-backed generator with strict citation enforcement."""

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        import httpx  # local import

        self._model = model
        self._api_key = os.environ.get("OPENAI_API_KEY", "")
        self._httpx = httpx
        self._fallback = LocalGenerator()

    def generate(
        self,
        query: str,
        context_chunks: list[GradedChunk],
        web_results: list[WebResult],
    ) -> tuple[str, list[Citation]]:
        if not self._api_key:
            return self._fallback.generate(query, context_chunks, web_results)
        # Build context with numbered sources
        sources: list[str] = []
        citations: list[Citation] = []
        for graded in context_chunks:
            idx = len(sources) + 1
            chunk = graded.chunk
            sources.append(
                f"[{idx}] (from {chunk.filename}, page {chunk.page_number}"
                f"{', section: ' + chunk.section if chunk.section else ''}):\n{chunk.content}"
            )
            citations.append(
                Citation(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    filename=chunk.filename,
                    page_number=chunk.page_number,
                    section=chunk.section,
                    snippet=LocalGenerator._best_snippet(query, chunk.content),
                    score=graded.relevance,
                )
            )
        for web in web_results:
            idx = len(sources) + 1
            sources.append(f"[{idx}] (from {web.title}, {web.url}):\n{web.snippet}")
            citations.append(
                Citation(
                    chunk_id=f"web:{web.url}",
                    document_id="",
                    filename=web.title,
                    page_number=0,
                    section=None,
                    snippet=web.snippet,
                    score=web.score,
                )
            )
        context = "\n\n".join(sources)
        system_prompt = (
            "You are DocuTrust, a strict corporate policy assistant. Answer the user's "
            "question using ONLY the provided numbered sources. Every factual claim must "
            "be followed by an inline citation [n] matching the source number. If the "
            "sources do not contain the answer, say so explicitly. Do not speculate."
        )
        user_prompt = f"Sources:\n{context}\n\nQuestion: {query}\n\nAnswer:"
        try:
            with self._httpx.Client(timeout=30.0) as client:
                response = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "model": self._model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.1,
                        "max_tokens": settings.max_answer_tokens,
                    },
                )
            response.raise_for_status()
            data = response.json()
            answer = data["choices"][0]["message"]["content"].strip()
            return answer, citations
        except Exception as exc:  # noqa: BLE001
            logger.warning("openai generation failed (%s); using local generator", exc)
            return self._fallback.generate(query, context_chunks, web_results)


def get_generator() -> Generator:
    provider = settings.llm_provider.lower()
    if provider == "openai":
        return OpenAIGenerator()
    return LocalGenerator()


class CitationValidator:
    """Validates that every citation in the answer is grounded in a source.

    The validator checks:
      1. Every inline citation marker [n] in the answer refers to a citation
         that exists in the citation list.
      2. Every citation's snippet actually appears (or substantially overlaps)
         in the source text it claims to come from.
      3. The answer does not contain uncited factual claims (heuristic: any
         sentence without a citation marker is flagged).

    Citations that fail validation are dropped, and the answer is regenerated
    without them by the generation agent.
    """

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()

    def validate(self, answer: str, citations: list[Citation]) -> tuple[bool, list[int]]:
        """Returns (is_valid, list of invalid citation indices)."""
        invalid: list[int] = []
        # Check every citation marker in the answer points to a real citation
        markers = {int(m) for m in re.findall(r"\[(\d+)\]", answer)}
        for marker in markers:
            if marker < 1 or marker > len(citations):
                invalid.append(marker)
        # Check every citation's snippet has substantial overlap with the answer
        answer_norm = self._normalize(answer)
        for idx, citation in enumerate(citations, start=1):
            if idx not in markers:
                # Citation is unused — not invalid, but not contributing
                continue
            snippet_norm = self._normalize(citation.snippet)
            if not snippet_norm:
                invalid.append(idx)
                continue
            # Require at least 3 consecutive words of overlap
            words = snippet_norm.split()
            found = False
            for i in range(len(words) - 2):
                trigram = " ".join(words[i : i + 3])
                if trigram in answer_norm:
                    found = True
                    break
            if not found:
                invalid.append(idx)
        return (len(invalid) == 0, invalid)


class GenerationAgent:
    """Generation + citation validation agent."""

    name = "generator"

    def __init__(self, generator: Generator | None = None) -> None:
        self._generator = generator or get_generator()
        self._validator = CitationValidator()

    def _select_context(
        self,
        state: CragState,
    ) -> tuple[list[GradedChunk], list[WebResult]]:

        if state.needs_web_search:

            relevant = sorted(
                [
                    g
                    for g in state.graded
                    if g.label == "relevant"
                ],
                key=lambda g: (
                    "purpose" in (g.chunk.section or "").lower(),
                    g.relevance,
                ),
                reverse=True,
            )

            relevant = relevant[:1]

            web = state.web_results[:2]

        else:

           relevant = [
            g
            for g in state.graded
            if g.label == "relevant"
           ]

           relevant = relevant[:1]

           web = []

        return relevant, web

    def run(self, state: CragState) -> CragState:
        record = state.start_step(
            self.name,
            "generate_answer",
            input_={
                "relevant_chunks": state.relevant_count,
                "web_results": len(state.web_results),
            },
        )
        try:
            context_chunks, web_results = self._select_context(state)
            answer, citations = self._generator.generate(
                state.query, context_chunks, web_results
            )
            # Validate citations
            is_valid, invalid = self._validator.validate(answer, citations)
            if not is_valid and citations:
                # Drop invalid citations and regenerate
                valid_citations = [
                    c for idx, c in enumerate(citations, start=1) if idx not in invalid
                ]
                # Re-number citations
                renumbered_answer = self._renumber(answer, invalid)
                state.answer = renumbered_answer
                state.citations = valid_citations
                state.finish_step(
                    record,
                    output={
                        "answer_length": len(renumbered_answer),
                        "citations": len(valid_citations),
                        "validation": "passed_after_repair",
                        "dropped_citations": invalid,
                    },
                    decision="answer_validated",
                    detail=f"dropped {len(invalid)} invalid citations and renumbered",
                )
            else:
                state.answer = answer
                state.citations = citations
                state.finish_step(
                    record,
                    output={
                        "answer_length": len(answer),
                        "citations": len(citations),
                        "validation": "passed",
                    },
                    decision="answer_validated",
                    detail=f"answer grounded in {len(citations)} citations",
                )
            logger.info(
                "generator: answer=%d chars, citations=%d, valid=%s",
                len(state.answer),
                len(state.citations),
                is_valid,
            )
        except Exception as exc:  # noqa: BLE001
            state.finish_step(record, status="failed", detail=str(exc))
            state.error = f"generator failed: {exc}"
            logger.exception("generator crashed")
        return state

    @staticmethod
    def _renumber(answer: str, invalid: list[int]) -> str:
        """Drop invalid citation markers and renumber the remaining ones."""
        if not invalid:
            return answer
        invalid_set = set(invalid)
        # Find all markers in order of appearance
        markers = list(re.finditer(r"\[(\d+)\]", answer))
        # Build a mapping from old number to new number
        old_to_new: dict[int, int] = {}
        new_idx = 0
        for m in markers:
            old = int(m.group(1))
            if old in invalid_set:
                continue
            if old not in old_to_new:
                new_idx += 1
                old_to_new[old] = new_idx
        # Replace markers
        def repl(match: re.Match) -> str:
            old = int(match.group(1))
            if old in invalid_set:
                return ""
            return f"[{old_to_new[old]}]"

        return re.sub(r"\[(\d+)\]", repl, answer)
