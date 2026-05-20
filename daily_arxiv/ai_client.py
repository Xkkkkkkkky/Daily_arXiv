from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date

from .arxiv_client import Paper
from .config import AIConfig, ConfigError


@dataclass(frozen=True)
class PaperSummary:
    arxiv_id: str
    chinese_title: str
    summary: str
    importance: int
    importance_reason: str


@dataclass(frozen=True)
class DailySummary:
    overview: str
    paper_summaries: tuple[PaperSummary, ...] = ()
    shortlist: tuple[str, ...] = ()
    raw_text: str = ""


def summarize_papers(papers: list[Paper], config: AIConfig, report_date: date) -> DailySummary:
    if not papers:
        return DailySummary(overview="No new papers matched the configured arXiv topics for this run.")
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
        "response_format": {"type": "json_object"},
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
        content = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected AI response shape: {data}") from exc

    return _parse_digest(content, papers)


def build_fallback_summary(papers: list[Paper], report_date: date) -> DailySummary:
    if not papers:
        return DailySummary(overview="No new papers matched the configured arXiv topics for this run.")

    return DailySummary(
        overview=f"AI summarization was skipped for {report_date.isoformat()}. Below are abstract-based previews.",
        paper_summaries=tuple(_fallback_paper_summary(paper) for paper in papers),
    )


def _build_prompt(papers: list[Paper], language: str, report_date: date) -> str:
    paper_items = [
        {
            "arxiv_id": paper.arxiv_id,
            "title": paper.title,
            "authors": paper.authors,
            "comments": paper.comment,
            "subjects": paper.categories,
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
        "Return ONLY valid JSON. Do not wrap it in Markdown fences. Use this exact shape:\n"
        "{\n"
        '  "overview": "2-4 concise Chinese sentences summarizing the overall research trend.",\n'
        '  "papers": [\n'
        "    {\n"
        '      "arxiv_id": "same arxiv_id from the input, preserving the version suffix such as v1",\n'
        '      "chinese_title": "accurate Chinese translation of the title",\n'
        '      "summary": "Chinese summary in 80-140 Chinese characters: problem, method, key result/contribution.",\n'
        '      "importance": 1,\n'
        '      "importance_reason": "One Chinese sentence explaining the importance rating."\n'
        "    }\n"
        "  ],\n"
        '  "shortlist": ["At most 5 Chinese bullet-style recommendations with arxiv_id and reason"]\n'
        "}\n\n"
        "Importance is an integer from 1 to 5: 5 means likely field-shaping or broadly useful; "
        "4 means strong contribution worth prioritizing; 3 means solid but specialized; "
        "2 means incremental or narrow; 1 means low confidence or mostly routine. "
        "Include every input paper exactly once. Put per-paper summaries only in papers[], not in overview or shortlist. "
        "If the abstract does not support a claim, say it is not specified.\n\n"
        "Papers JSON:\n"
        f"{json.dumps(paper_items, ensure_ascii=False, indent=2)}"
    )


def _parse_digest(content: str, papers: list[Paper]) -> DailySummary:
    try:
        data = json.loads(_extract_json_object(content))
    except json.JSONDecodeError:
        return DailySummary(
            overview="AI returned an unstructured response, so the email is showing abstract-based fallback cards.",
            paper_summaries=tuple(_fallback_paper_summary(paper) for paper in papers),
            raw_text=content,
        )
    if not isinstance(data, dict):
        return DailySummary(
            overview="AI returned an unexpected response shape, so the email is showing abstract-based fallback cards.",
            paper_summaries=tuple(_fallback_paper_summary(paper) for paper in papers),
            raw_text=content,
        )

    summaries_by_id: dict[str, PaperSummary] = {}
    for item in data.get("papers", []):
        if not isinstance(item, dict):
            continue
        arxiv_id = str(item.get("arxiv_id", "")).strip()
        if not arxiv_id:
            continue
        paper_summary = PaperSummary(
            arxiv_id=arxiv_id,
            chinese_title=str(item.get("chinese_title", "")).strip(),
            summary=str(item.get("summary", "")).strip(),
            importance=_coerce_importance(item.get("importance", 3)),
            importance_reason=str(item.get("importance_reason", "")).strip(),
        )
        summaries_by_id[_normalize_arxiv_id(arxiv_id)] = paper_summary

    shortlist = []
    for item in data.get("shortlist", []):
        text = str(item).strip()
        if text:
            shortlist.append(text)

    return DailySummary(
        overview=str(data.get("overview", "")).strip() or "AI did not provide an overview.",
        paper_summaries=tuple(
            summaries_by_id.get(_normalize_arxiv_id(paper.arxiv_id), _fallback_paper_summary(paper))
            for paper in papers
        ),
        shortlist=tuple(shortlist[:5]),
        raw_text=content,
    )


def _extract_json_object(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    if stripped.startswith("{"):
        return stripped

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    return stripped


def _normalize_arxiv_id(value: str) -> str:
    arxiv_id = value.strip().rsplit("/", 1)[-1]
    return re.sub(r"v\d+$", "", arxiv_id)


def _coerce_importance(value: object) -> int:
    try:
        importance = int(value)
    except (TypeError, ValueError):
        return 3
    return min(5, max(1, importance))


def _fallback_paper_summary(paper: Paper) -> PaperSummary:
    abstract = paper.abstract[:260] + ("..." if len(paper.abstract) > 260 else "")
    return PaperSummary(
        arxiv_id=paper.arxiv_id,
        chinese_title="",
        summary=abstract,
        importance=3,
        importance_reason="AI 未提供结构化评级，暂按中等重要性展示。",
    )


def _chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"
