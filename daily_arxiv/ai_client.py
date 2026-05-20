from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import date

from .arxiv_client import Paper
from .config import AIConfig, ConfigError


def summarize_papers(papers: list[Paper], config: AIConfig, report_date: date) -> str:
    if not papers:
        return "No new papers matched the configured arXiv topics for this run."
    if not config.api_key:
        raise ConfigError("Missing AI_API_KEY or ai.api_key")

    payload = {
        "model": config.model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a careful research assistant. Write concise daily arXiv digests. "
                    "Do not invent claims that are not supported by the supplied metadata or abstract."
                ),
            },
            {
                "role": "user",
                "content": _build_prompt(papers, config.language, report_date),
            },
        ],
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }

    request = urllib.request.Request(
        _chat_completions_url(config.base_url),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AI service returned HTTP {exc.code}: {detail}") from exc

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected AI response shape: {data}") from exc


def build_fallback_summary(papers: list[Paper], report_date: date) -> str:
    if not papers:
        return "No new papers matched the configured arXiv topics for this run."

    lines = [
        f"# Daily arXiv Digest - {report_date.isoformat()}",
        "",
        "AI summarization was skipped. Below are the fetched papers and abstract snippets.",
        "",
    ]
    for index, paper in enumerate(papers, start=1):
        lines.extend(
            [
                f"## {index}. {paper.title}",
                f"- arXiv: {paper.arxiv_id}",
                f"- Topics: {', '.join(paper.topics)}",
                f"- Authors: {', '.join(paper.authors[:8])}{' et al.' if len(paper.authors) > 8 else ''}",
                f"- Link: {paper.link}",
                f"- Abstract: {paper.abstract[:700]}{'...' if len(paper.abstract) > 700 else ''}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def _build_prompt(papers: list[Paper], language: str, report_date: date) -> str:
    paper_items = [
        {
            "arxiv_id": paper.arxiv_id,
            "title": paper.title,
            "authors": paper.authors,
            "topics": paper.topics,
            "primary_category": paper.primary_category,
            "published": paper.published.isoformat(),
            "link": paper.link,
            "abstract": paper.abstract,
        }
        for paper in papers
    ]
    return (
        f"Report date: {report_date.isoformat()}\n"
        f"Output language: {language}\n\n"
        "Create a daily arXiv digest in Markdown with this structure:\n"
        "1. A short overall trend summary.\n"
        "2. A numbered list of papers. For each paper include: problem, method, main contribution, and why it may matter.\n"
        "3. A final 'worth reading first' shortlist of at most 5 papers with one-line reasons.\n\n"
        "Keep each paper concise. If the abstract does not support a point, say it is not specified.\n\n"
        "Papers JSON:\n"
        f"{json.dumps(paper_items, ensure_ascii=False, indent=2)}"
    )


def _chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"
