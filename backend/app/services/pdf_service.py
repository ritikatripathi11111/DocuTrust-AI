"""PDF parsing and structural chunking service.

Extracts text from uploaded PDFs, detects section headings to build a structural
index, and splits the text into semantically meaningful chunks suitable for
embedding and retrieval.

The chunker is intentionally section-aware: it tries to keep chunks within a
single section so the retriever returns coherent passages, and it records the
page number and section heading on every chunk so the citation validator can
produce precise, verifiable citations.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Iterable

from pypdf import PdfReader

from app.core.logging import get_logger

logger = get_logger(__name__)


# Roughly target ~500 characters per chunk. Small enough for precise citations,
# large enough to carry a complete policy paragraph.
DEFAULT_CHUNK_CHAR_TARGET = 500
DEFAULT_CHUNK_CHAR_OVERLAP = 80

# Heuristics for detecting section headings in corporate policy documents.
_HEADING_PATTERNS = [
    # "1. Remote Work Policy" or "1.1 Eligibility" or "1.1.2 Foo Bar"
    re.compile(r"^\s*(\d+(\.\d+){0,3}\.?)\s+([A-Z][A-Za-z0-9 \-:&'/()]{2,})\s*$"),
    # "Article 3", "Section 4", "Clause 2.1", "Chapter 1", "Part II", "Appendix A"
    re.compile(r"^\s*(Article|Section|Clause|Chapter|Part|Appendix)\s+\d+[A-Za-z]?\b.*$", re.I),
    # All-caps section keywords
    re.compile(r"^\s*(POLICY|PURPOSE|SCOPE|DEFINITIONS|RESPONSIBILITIES|PROCEDURES|ENFORCEMENT|REVIEW|REFERENCES|INTRODUCTION|OVERVIEW)\s*$"),
]


@dataclass
class ParsedChunk:
    chunk_index: int
    page_number: int
    section: str | None
    content: str
    token_count: int


@dataclass
class ParsedDocument:
    page_count: int
    sections: list[str]
    chunks: list[ParsedChunk]


def _is_heading(line: str) -> tuple[bool, str | None]:
    for pattern in _HEADING_PATTERNS:
        match = pattern.match(line)
        if match:
            return True, line.strip()
    return False, None


def _estimate_tokens(text: str) -> int:
    # Cheap, model-agnostic token estimate: ~4 chars per token for English text.
    return max(1, len(text) // 4)


def _split_page_text(
    text: str,
    page_number: int,
    current_section: str | None,
    char_target: int,
    overlap: int,
) -> list[tuple[str, str | None]]:
    """Split a single page's text into overlapping chunks, preserving the
    current section label. Returns (chunk_text, section) tuples.

    The chunker walks the page line by line. When a line is detected as a
    section heading, the current buffer is flushed and the heading becomes
    the section label for subsequent lines. This handles both single-newline
    and double-newline separated text from PDF extractors.
    """
    text = text.strip()
    if not text:
        return []
    lines = text.splitlines()
    chunks: list[tuple[str, str | None]] = []
    buffer = ""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        is_heading, heading = _is_heading(stripped)
        if is_heading and heading:
            if buffer:
                chunks.append((buffer.strip(), current_section))
                buffer = ""
            current_section = heading
            continue
        if len(buffer) + len(stripped) + 1 > char_target and buffer:
            chunks.append((buffer.strip(), current_section))
            # carry a small overlap for context continuity
            buffer = buffer[-overlap:] + " " + stripped if overlap else stripped
        else:
            buffer = (buffer + " " + stripped).strip() if buffer else stripped
    if buffer:
        chunks.append((buffer.strip(), current_section))
    return chunks


def parse_pdf_bytes(
    data: bytes,
    *,
    char_target: int = DEFAULT_CHUNK_CHAR_TARGET,
    overlap: int = DEFAULT_CHUNK_CHAR_OVERLAP,
) -> ParsedDocument:
    """Parse PDF bytes into a structured document with sections and chunks."""
    reader = PdfReader(io.BytesIO(data))
    page_count = len(reader.pages)
    sections: list[str] = []
    raw_chunks: list[tuple[str, int, str | None]] = []
    current_section: str | None = None

    for page_idx in range(page_count):
        try:
            page_text = reader.pages[page_idx].extract_text() or ""
        except Exception as exc:  # noqa: BLE001 - pypdf can raise on corrupt pages
            logger.warning("failed to extract page %s: %s", page_idx + 1, exc)
            page_text = ""
        page_number = page_idx + 1
        # Walk lines to detect headings and record them in the section index,
        # even when a heading has no direct content under it (e.g. a top-level
        # heading immediately followed by a sub-heading).
        for line in page_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            is_heading, heading = _is_heading(stripped)
            if is_heading and heading and heading not in sections:
                sections.append(heading)
        page_chunks = _split_page_text(
            page_text, page_number, current_section, char_target, overlap
        )
        for chunk_text, section in page_chunks:
            if not chunk_text:
                continue
            current_section = section or current_section
            raw_chunks.append((chunk_text, page_number, section or current_section))

    chunks: list[ParsedChunk] = []
    for idx, (content, page_number, section) in enumerate(raw_chunks):
        chunks.append(
            ParsedChunk(
                chunk_index=idx,
                page_number=page_number,
                section=section,
                content=content,
                token_count=_estimate_tokens(content),
            )
        )

    return ParsedDocument(page_count=page_count, sections=sections, chunks=chunks)


def iter_chunks(parsed: ParsedDocument) -> Iterable[ParsedChunk]:
    return iter(parsed.chunks)
