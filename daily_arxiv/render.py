from __future__ import annotations

import html
from datetime import date

from .arxiv_client import Paper


def build_subject(prefix: str, report_date: date, paper_count: int) -> str:
    suffix = "paper" if paper_count == 1 else "papers"
    return f"{prefix} - {report_date.isoformat()} - {paper_count} {suffix}"


def build_text_digest(summary: str, papers: list[Paper], report_date: date) -> str:
    lines = [
        f"Daily arXiv Digest - {report_date.isoformat()}",
        "",
        summary.strip(),
        "",
        "Paper links:",
    ]
    if not papers:
        lines.append("- No new papers matched the configured topics.")
    for paper in papers:
        lines.append(f"- [{', '.join(paper.topics)}] {paper.title} ({paper.link})")
    return "\n".join(lines).strip() + "\n"


def build_html_digest(summary: str, papers: list[Paper], report_date: date) -> str:
    paper_items = "\n".join(_paper_item(paper) for paper in papers)
    if not paper_items:
        paper_items = "<li>No new papers matched the configured topics.</li>"

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.55; color: #1f2933; }}
    main {{ max-width: 820px; margin: 0 auto; padding: 24px; }}
    h1 {{ font-size: 24px; margin: 0 0 18px; }}
    .summary {{ white-space: pre-wrap; background: #f6f8fa; border: 1px solid #d8dee4; padding: 16px; border-radius: 8px; }}
    ol {{ padding-left: 22px; }}
    li {{ margin: 0 0 12px; }}
    a {{ color: #0969da; }}
    .meta {{ color: #57606a; font-size: 13px; }}
  </style>
</head>
<body>
  <main>
    <h1>Daily arXiv Digest - {html.escape(report_date.isoformat())}</h1>
    <section class="summary">{html.escape(summary.strip())}</section>
    <h2>Paper links</h2>
    <ol>
      {paper_items}
    </ol>
  </main>
</body>
</html>"""


def _paper_item(paper: Paper) -> str:
    authors = ", ".join(paper.authors[:6])
    if len(paper.authors) > 6:
        authors += " et al."
    topics = ", ".join(paper.topics)
    pdf_link = f' | <a href="{html.escape(paper.pdf_url)}">PDF</a>' if paper.pdf_url else ""
    return (
        "<li>"
        f'<a href="{html.escape(paper.link)}"><strong>{html.escape(paper.title)}</strong></a>'
        f"{pdf_link}"
        f'<div class="meta">{html.escape(topics)} | arXiv:{html.escape(paper.arxiv_id)} | {html.escape(authors)}</div>'
        "</li>"
    )
