"""Generate a sample corporate policy PDF for testing the CRAG pipeline.

Writes a minimal but valid multi-page PDF with real, extractable text content
so the retriever, grader, and citation validator can be exercised end to end.
No external dependencies — uses only the Python standard library.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _escape_text(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _make_page(content_lines: list[str]) -> bytes:
    """Build a single PDF page with the given text lines."""
    lines = "\n".join(
        f"BT /F1 11 Tf 72 {720 - 16 * (i + 1)} Td ({_escape_text(line)}) Tj ET"
        for i, line in enumerate(content_lines)
    )
    return lines.encode("utf-8")


def build_pdf(pages: list[list[str]]) -> bytes:
    """Build a multi-page PDF from a list of pages, each a list of text lines."""
    # We'll construct the PDF manually with xref table.
    objects: list[bytes] = []
    # Object 1: Catalog
    # Object 2: Pages
    # Object 3..n: Page + content stream pairs
    page_ids: list[int] = []
    # We'll assign object numbers as we go.
    # 1 = catalog, 2 = pages, then for each page: page obj + stream obj
    obj_num = 3
    page_obj_nums: list[int] = []
    content_stream_objs: list[bytes] = []
    for page_lines in pages:
        page_obj_nums.append(obj_num)
        obj_num += 1
        stream_obj_num = obj_num
        obj_num += 1
        content = _make_page(page_lines)
        content_stream_objs.append(
            b"%d 0 obj\n<< /Length %d >>\nstream\n%s\nendstream\nendobj\n"
            % (stream_obj_num, len(content), content)
        )
    # Build page objects
    page_objs: list[bytes] = []
    for i, page_num in enumerate(page_obj_nums):
        stream_num = page_num + 1
        page_objs.append(
            b"%d 0 obj\n<< /Type /Page /Parent 2 0 R "
            b"/MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> "
            b"/Contents %d 0 R >>\nendobj\n" % (page_num, stream_num)
        )
    kids = " ".join(f"{n} 0 R" for n in page_obj_nums)
    pages_obj = (
        "2 0 obj\n<< /Type /Pages /Kids [%s] /Count %d >>\nendobj\n" % (kids, len(page_obj_nums))
    ).encode("utf-8")
    catalog_obj = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    # Assemble
    header = b"%PDF-1.4\n"
    body = b""
    body += catalog_obj
    body += pages_obj
    for p in page_objs:
        body += p
    for s in content_stream_objs:
        body += s
    # Build xref
    # We need offsets; rebuild with offsets tracked
    objects_list = [catalog_obj, pages_obj] + page_objs + content_stream_objs
    offsets: list[int] = []
    pos = len(header)
    for obj in objects_list:
        offsets.append(pos)
        pos += len(obj)
    xref_pos = pos
    xref = b"xref\n0 %d\n" % (len(objects_list) + 1)
    xref += b"0000000000 65535 f \n"
    for off in offsets:
        xref += b"%010d 00000 n \n" % off
    trailer = (
        "trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objects_list) + 1, xref_pos)
    ).encode("utf-8")
    return header + body + xref + trailer


SAMPLE_PAGES = [
    [
        "Acme Corp - Corporate Policy Manual",
        "",
        "1. Remote Work Policy",
        "",
        "1.1 Eligibility",
        "Employees who have completed 90 days of service and whose role can",
        "be performed offsite are eligible for remote work. Remote employees",
        "must maintain a secure internet connection and use company-issued",
        "devices for all work activities.",
        "",
        "1.2 Available Hours",
        "Remote employees must be available during core hours of 10am to 3pm",
        "in their local time zone. Outside core hours, flexible scheduling is",
        "permitted with manager approval.",
    ],
    [
        "2. Paid Time Off (PTO) Policy",
        "",
        "2.1 Accrual",
        "Full-time employees accrue PTO at a rate of 0.05 hours per hour",
        "worked, equivalent to about 10 days per year. Unused PTO may be",
        "carried over up to a 40-hour cap; balances above the cap are forfeited",
        "at year end unless state law requires payout.",
        "",
        "2.2 PTO Requests",
        "PTO requests must be submitted at least 7 days in advance and",
        "approved by the direct manager. Requests of 3 or more consecutive",
        "days require a written coverage plan.",
    ],
    [
        "3. Information Security Policy",
        "",
        "3.1 Access Control",
        "Employees must use unique credentials and enable multi-factor",
        "authentication for sensitive systems. Access rights are reviewed",
        "quarterly and revoked upon termination of employment.",
        "",
        "3.2 Incident Reporting",
        "Suspected security incidents must be reported to the security team",
        "within 24 hours of discovery. Employees must not attempt to",
        "investigate or remediate incidents without authorization.",
    ],
    [
        "4. Workplace Conduct",
        "",
        "4.1 Harassment Prohibition",
        "Acme Corp prohibits harassment based on race, color, religion, sex,",
        "sexual orientation, gender identity, national origin, age, disability,",
        "or genetic information. Harassment should be reported to HR or via",
        "the anonymous ethics hotline.",
        "",
        "4.2 Dress Code",
        "Employees are expected to dress in business casual attire for",
        "in-office workdays. Client-facing meetings may require business",
        "formal attire at the manager's discretion.",
    ],
]


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/acme_policy.pdf")
    out.write_bytes(build_pdf(SAMPLE_PAGES))
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(SAMPLE_PAGES)} pages)")


if __name__ == "__main__":
    main()
