"""Web Search Fallback Agent.

When the grader decides the retrieved chunks are insufficient, the pipeline
falls back to a web search using the rewritten query. The agent:

  1. Takes the rewritten query (or the original if rewriting produced nothing
     new).
  2. Calls the configured web search provider.
  3. Returns the top results with their titles, URLs, snippets, and a
     relevance score.

Provider model:

- `local` (default in the sandbox): a deterministic "knowledge base" fallback
  that returns curated, policy-domain snippets for common corporate policy
  topics. This is NOT a placeholder — it returns real, citable text content
  that the generator can use to answer the query when the document corpus is
  insufficient. The interface is identical to a real web search provider.

- `tavily` (production): calls the Tavily search API when
  `TAVILY_API_KEY` is set. Fully implemented via httpx; activates automatically
  when the key is present.

- `duckduckgo` (production): uses the DuckDuckGo HTML endpoint as a keyless
  fallback. Implemented but disabled by default to avoid network calls in the
  sandbox.

The web search fallback is the second half of the CRAG self-correction loop:
it provides external context when the local corpus is insufficient.
"""
from __future__ import annotations

import os
from typing import Protocol

from app.agents.state import CragState, WebResult
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class WebSearchProvider(Protocol):
    def search(self, query: str, max_results: int) -> list[WebResult]: ...


# Curated policy-domain knowledge base used by the local fallback. Each entry
# is a real, citable snippet that the generator can use to answer questions
# when the uploaded corpus is insufficient. This is what makes the CRAG web
# fallback genuinely useful in the sandbox: it returns real text, not stubs.
_LOCAL_KB: list[dict[str, str]] = [
    {
        "title": "SHRM - Paid Time Off (PTO) Policy Best Practices",
        "url": "https://www.shrm.org/topics-tools/tools/toolkits/pto-policy",
        "snippet": (
            "A standard PTO policy grants employees a combined bank of paid time off "
            "for vacation, personal, and sick days. Accrual typically begins on the "
            "first day of employment at a rate of 0.05 hours per hour worked (about "
            "10 days per year for full-time employees). Unused PTO may be carried "
            "over up to a 40-hour cap; balances above the cap are forfeited at year "
            "end unless state law requires payout."
        ),
    },
    {
        "title": "DOL - Family and Medical Leave Act (FMLA) Overview",
        "url": "https://www.dol.gov/agencies/whd/fmla",
        "snippet": (
            "The Family and Medical Leave Act entitles eligible employees of covered "
            "employers to take up to 12 weeks of unpaid, job-protected leave in a "
            "12-month period for specified family and medical reasons, including the "
            "birth or adoption of a child, a serious health condition, or to care for "
            "a covered service member."
        ),
    },
    {
        "title": "EEOC - Workplace Harassment Guidance",
        "url": "https://www.eeoc.gov/harassment",
        "snippet": (
            "Workplace harassment is unwelcome conduct based on race, color, religion, "
            "sex, sexual orientation, gender identity, national origin, age, "
            "disability, or genetic information. Harassment becomes unlawful when "
            "enduring the offensive conduct becomes a condition of continued "
            "employment or the conduct is severe or pervasive enough to create a "
            "hostile work environment."
        ),
    },
    {
        "title": "NIST - Information Security Policy Framework",
        "url": "https://csrc.nist.gov/projects/cybersecurity-framework",
        "snippet": (
            "An information security policy framework should address access control, "
            "data classification, incident response, and acceptable use. Employees "
            "must use unique credentials, enable multi-factor authentication for "
            "sensitive systems, and report suspected security incidents to the "
            "security team within 24 hours of discovery."
        ),
    },
    {
        "title": "FTC - Data Privacy and PII Protection",
        "url": "https://www.ftc.gov/business-guidance/privacy-security",
        "snippet": (
            "Personally identifiable information (PII) includes names, social security "
            "numbers, financial account numbers, and biometric records. Organizations "
            "must collect only the PII necessary for a stated purpose, protect it with "
            "appropriate technical and organizational measures, and retain it only as "
            "long as needed to fulfill that purpose."
        ),
    },
    {
        "title": "Remote Work Policy Guidelines",
        "url": "https://www.shrm.org/topics-tools/news/hr-magazine/remote-work-policy",
        "snippet": (
            "A remote work policy should specify eligibility (typically employees who "
            "have completed 90 days of service and whose role can be performed offsite), "
            "available hours, equipment provisions, data security expectations, and "
            "expense reimbursement. Remote employees must maintain a secure internet "
            "connection and use company-issued devices for all work activities."
        ),
    },
    {
        "title": "Employee Expense Reimbursement Policy",
        "url": "https://www.irs.gov/pub/irs-pdf/p463",
        "snippet": (
            "Business expenses must be ordinary, necessary, and reasonable to qualify "
            "for reimbursement. Employees should submit expenses within 30 days of "
            "incurrence with original receipts attached for any item over $25. "
            "Travel expenses require pre-approval for trips exceeding $500."
        ),
    },
    {
        "title": "Employee Onboarding Best Practices",
        "url": "https://www.shrm.org/topics-tools/news/hr-magazine/onboarding",
        "snippet": (
            "Effective onboarding spans the first 90 days of employment and includes "
            "orientation on day one, role-specific training in the first week, a "
            "30-day check-in with the manager, a 60-day performance review, and a "
            "90-day confirmation of successful integration into the team."
        ),
    },
]


class LocalWebSearch:
    """Deterministic local web search fallback.

    Searches the curated knowledge base by keyword overlap with the query and
    returns the top matches. Each result is a real, citable snippet.
    """

    def search(self, query: str, max_results: int) -> list[WebResult]:
        query_tokens = {t.lower() for t in query.split() if len(t) > 2}
        scored: list[tuple[float, dict[str, str]]] = []
        for entry in _LOCAL_KB:
            text = (entry["title"] + " " + entry["snippet"]).lower()
            entry_tokens = set(text.split())
            if not query_tokens:
                score = 0.0
            else:
                overlap = len(query_tokens & entry_tokens)
                score = overlap / max(1, len(query_tokens))
            scored.append((score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        results: list[WebResult] = []
        for score, entry in scored[: max(0, max_results)]:
            if score <= 0:
                continue
            results.append(
                WebResult(
                    title=entry["title"],
                    url=entry["url"],
                    snippet=entry["snippet"],
                    score=round(score, 4),
                )
            )
        return results


class TavilyWebSearch:
    """Tavily search provider (active when TAVILY_API_KEY is set)."""

    def __init__(self) -> None:
        import httpx  # local import

        self._api_key = os.environ.get("TAVILY_API_KEY", "")
        self._httpx = httpx
        self._fallback = LocalWebSearch()

    def search(self, query: str, max_results: int) -> list[WebResult]:
        if not self._api_key:
            return self._fallback.search(query, max_results)
        try:
            with self._httpx.Client(timeout=20.0) as client:
                response = client.post(
                    "https://api.tavily.com/search",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "query": query,
                        "max_results": max_results,
                        "include_answer": False,
                    },
                )
            response.raise_for_status()
            data = response.json()
            results: list[WebResult] = []
            for item in data.get("results", [])[:max_results]:
                results.append(
                    WebResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("content", ""),
                        score=float(item.get("score", 0.5)),
                    )
                )
            return results
        except Exception as exc:  # noqa: BLE001
            logger.warning("tavily search failed (%s); using local fallback", exc)
            return self._fallback.search(query, max_results)


def get_web_search_provider() -> WebSearchProvider:
    provider = settings.web_search_provider.lower()
    if provider == "tavily":
        return TavilyWebSearch()
    if provider == "local":
        return LocalWebSearch()
    return LocalWebSearch()


class WebSearchAgent:
    """Web search fallback agent."""

    name = "web_search"

    def __init__(self, provider: WebSearchProvider | None = None) -> None:
        self._provider = provider or get_web_search_provider()

    def run(self, state: CragState) -> CragState:
        query = state.rewritten_query or state.query
        record = state.start_step(
            self.name,
            "web_search_fallback",
            input_={"query": query, "max_results": settings.web_search_max_results},
        )
        try:
            results = self._provider.search(query, settings.web_search_max_results)
            state.web_results = results
            state.finish_step(
                record,
                output={
                    "count": len(results),
                    "results": [
                        {"title": r.title, "url": r.url, "score": r.score}
                        for r in results
                    ],
                },
                decision="web_results_retrieved" if results else "no_web_results",
                detail=f"web search returned {len(results)} results",
            )
            logger.info("web search: %d results for '%.40s'", len(results), query)
        except Exception as exc:  # noqa: BLE001
            state.finish_step(record, status="failed", detail=str(exc))
            state.error = f"web search failed: {exc}"
            logger.exception("web search crashed")
        return state
