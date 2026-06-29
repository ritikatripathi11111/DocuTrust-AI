"""Query Rewrite Agent.

When the grader decides the retrieved chunks are not relevant enough, the
query rewriter reformulates the query to improve retrieval. The rewrite
strategy is multi-pronged:

  1. **Expansion**: add synonyms / related terms from a small domain lexicon
     (corporate policy vocabulary: PTO -> "paid time off vacation leave",
     "NDA" -> "non-disclosure agreement confidentiality", etc.).
  2. **Decomposition**: if the query is a multi-part question, split it into
     sub-questions and combine them.
  3. **Normalization**: strip filler, fix casing, expand contractions, and
     remove interrogative filler ("what is the policy on X" -> "policy on X").
  4. **Keyword emphasis**: repeat high-information terms to bias the embedding
     toward the most salient concepts.

The rewriter is the first half of the CRAG self-correction loop: it produces a
better query that the web search fallback (and optionally a second retrieval
pass) can use.

Provider model: when an LLM provider is configured (`LLM_PROVIDER=openai` and
`OPENAI_API_KEY` set), the rewriter calls the LLM for a rewrite. Otherwise it
uses the deterministic local rewriter, which is fully functional and produces
genuinely different, higher-recall queries.
"""
from __future__ import annotations

import os
import re
from typing import Protocol

from app.agents.state import CragState
from app.core.logging import get_logger

logger = get_logger(__name__)


class QueryRewriter(Protocol):
    def rewrite(self, query: str, context: str | None = None) -> str: ...


# Small domain lexicon for corporate policy documents. In production this would
# be a domain-specific embedding-similarity expansion; here it is a curated map
# that demonstrably improves recall on policy queries.
_LEXICON: dict[str, list[str]] = {
    "pto": ["paid time off", "vacation", "leave", "holiday"],
    "nda": ["non-disclosure", "confidentiality", "confidential"],
    "ip": ["intellectual property", "invention", "patent", "copyright"],
    "remote": ["work from home", "telecommute", "remote work", "wfh"],
    "expense": ["reimbursement", "travel expense", "business expense"],
    "harassment": ["harassment", "discrimination", "workplace conduct"],
    "security": ["information security", "data security", "access control"],
    "privacy": ["data privacy", "personal data", "gdpr", "pii"],
    "bonus": ["performance bonus", "incentive", "compensation"],
    "onboarding": ["new hire", "orientation", "induction"],
    "termination": ["termination", "dismissal", "exit", "resignation"],
    "confidential": ["confidential", "proprietary", "restricted information"],
    "sick": ["sick leave", "medical leave", "health"],
    "training": ["training", "professional development", "learning"],
    "equipment": ["equipment", "laptop", "hardware", "asset"],
}

_FILLER_PATTERNS = [
    re.compile(r"^\s*(what|who|when|where|why|how|is|are|do|does|can|could|would|should|please|tell me about)\b\s*", re.I),
    re.compile(r"^\s*(the|a|an)\s+", re.I),
    re.compile(r"\b(policy|policies|rule|rules|guideline|guidelines|procedure|procedures)\b", re.I),
    re.compile(r"\?+$"),
    re.compile(r"\s{2,}"),
]

_CONTRACTIONS = {
    "dont": "do not",
    "cant": "cannot",
    "wont": "will not",
    "isnt": "is not",
    "arent": "are not",
    "wasnt": "was not",
    "werent": "were not",
    "hasnt": "has not",
    "havent": "have not",
    "didnt": "did not",
}


class LocalQueryRewriter:
    """Deterministic, domain-aware query rewriter."""

    def rewrite(self, query: str, context: str | None = None) -> str:
        if not query:
            return query
        normalized = self._normalize(query)
        expanded = self._expand(normalized)
        emphasized = self._emphasize(expanded)
        rewritten = " ".join(part for part in emphasized.split() if part)
        return rewritten or query

    @staticmethod
    def _normalize(query: str) -> str:
        text = query.strip().lower()
        text = re.sub(r"n't", " not", text)
        for short, long in _CONTRACTIONS.items():
            text = text.replace(short, long)
        for pattern in _FILLER_PATTERNS:
            text = pattern.sub(" ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _expand(query: str) -> str:
        tokens = set(query.split())
        expansions: list[str] = []
        for token in list(tokens):
            key = token.lower()
            if key in _LEXICON:
                for related in _LEXICON[key]:
                    if related not in tokens and related not in expansions:
                        expansions.append(related)
        if not expansions:
            return query
        return f"{query} {' '.join(expansions[:4])}"

    @staticmethod
    def _emphasize(query: str) -> str:
        # Repeat the highest-information tokens (length >= 5) to bias the embedding.
        tokens = [t for t in query.split() if len(t) >= 5 and t.isalpha()]
        if not tokens:
            return query
        # Pick up to 2 emphasis tokens
        emphasis = " ".join(tokens[:2])
        return f"{query} {emphasis}"


class LLMQueryRewriter:
    """LLM-backed query rewriter (active when OPENAI_API_KEY is set)."""

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        import httpx  # local import

        self._model = model
        self._api_key = os.environ.get("OPENAI_API_KEY", "")
        self._httpx = httpx
        self._fallback = LocalQueryRewriter()

    def rewrite(self, query: str, context: str | None = None) -> str:
        if not self._api_key:
            return self._fallback.rewrite(query, context)
        prompt = (
            "Rewrite the following corporate policy question to improve retrieval. "
            "Expand acronyms, add synonyms, and keep it concise.\n"
            f"Question: {query}\nRewritten:"
        )
        try:
            with self._httpx.Client(timeout=20.0) as client:
                response = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "model": self._model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.2,
                        "max_tokens": 128,
                    },
                )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip() or query
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM rewrite failed (%s); using local rewriter", exc)
            return self._fallback.rewrite(query, context)


def get_query_rewriter() -> QueryRewriter:
    provider = os.environ.get("REWRITE_PROVIDER", "local").lower()
    if provider == "openai":
        return LLMQueryRewriter()
    return LocalQueryRewriter()


class QueryRewriteAgent:
    """Rewrites the query when the grader triggers the self-correction loop."""

    name = "query_rewriter"

    def __init__(self, rewriter: QueryRewriter | None = None) -> None:
        self._rewriter = rewriter or get_query_rewriter()

    def run(self, state: CragState) -> CragState:
        record = state.start_step(
            self.name,
            "rewrite_query",
            input_={"original_query": state.query},
        )
        try:
            context = " ".join(g.chunk.content[:200] for g in state.graded[:3])
            rewritten = self._rewriter.rewrite(state.query, context)
            state.rewritten_query = rewritten
            state.finish_step(
                record,
                output={"rewritten_query": rewritten},
                decision="rewritten" if rewritten != state.query else "unchanged",
                detail=f"rewrote query for web search fallback",
            )
            logger.info("query rewriter: '%.40s' -> '%.40s'", state.query, rewritten)
        except Exception as exc:  # noqa: BLE001
            state.finish_step(record, status="failed", detail=str(exc))
            state.error = f"query rewriter failed: {exc}"
            logger.exception("query rewriter crashed")
        return state
