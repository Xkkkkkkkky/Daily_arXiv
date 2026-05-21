from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import date

from .arxiv_client import Paper, normalize_arxiv_id
from .config import AIConfig, ConfigError


StatusLogger = Callable[[str], None]
AI_RESPONSE_RETRY_COUNT = 2
AI_RESPONSE_RETRY_BACKOFF_SECONDS = 2.0


@dataclass(frozen=True)
class PaperSummary:
    arxiv_id: str
    chinese_title: str
    summary: str
    importance: int
    importance_reason: str
    raw_response: str = ""


@dataclass(frozen=True)
class DailySummary:
    overview: str
    paper_summaries: tuple[PaperSummary, ...] = ()
    shortlist: tuple[str, ...] = ()
    raw_text: str = ""


@dataclass(frozen=True)
class _PaperSummaryResult:
    index: int
    summary: PaperSummary
    raw_response: str
    used_fallback: bool
    message: str


def summarize_papers(
    papers: list[Paper],
    config: AIConfig,
    report_date: date,
    status: StatusLogger | None = None,
) -> DailySummary:
    if not papers:
        return DailySummary(overview="No new papers matched the configured arXiv topics for this run.")
    if not config.api_key:
        raise ConfigError("Missing AI_API_KEY or ai.api_key")

    total_count = len(papers)
    summaries: list[PaperSummary | None] = [None] * total_count
    raw_responses: list[str] = [""] * total_count
    fallback_count = 0
    worker_count = min(config.concurrency, total_count)
    _log(
        status,
        f"AI: starting per-paper summarization for {total_count} paper(s) "
        f"with concurrency window {worker_count}",
    )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        pending: dict[Future[_PaperSummaryResult], tuple[int, Paper]] = {}
        paper_items = iter(enumerate(papers, start=1))

        def submit_next() -> None:
            try:
                index, paper = next(paper_items)
            except StopIteration:
                return
            _log(status, f"AI: scheduling summary {index}/{total_count} for {paper.arxiv_id}")
            future = executor.submit(_summarize_one_paper, paper, config, report_date, index, total_count, status)
            pending[future] = (index, paper)

        for _ in range(worker_count):
            submit_next()

        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                index, paper = pending.pop(future)
                result = _resolve_summary_future(future, paper, index)
                _store_summary_result(result, summaries, raw_responses)
                if result.used_fallback:
                    fallback_count += 1
                    _log(
                        status,
                        f"AI: summary {result.index}/{total_count} for {paper.arxiv_id} "
                        f"used fallback: {result.message}",
                    )
                else:
                    _log(
                        status,
                        f"AI: parsed summary {result.index}/{total_count} for {paper.arxiv_id} "
                        f"with importance {result.summary.importance}/5",
                    )
                submit_next()

    final_summaries = tuple(summary for summary in summaries if summary is not None)

    return DailySummary(
        overview=_build_overview(list(final_summaries), report_date, fallback_count),
        paper_summaries=final_summaries,
        shortlist=_build_shortlist(list(final_summaries)),
        raw_text="\n\n".join(item for item in raw_responses if item),
    )


def _resolve_summary_future(future: Future[_PaperSummaryResult], paper: Paper, index: int) -> _PaperSummaryResult:
    try:
        return future.result()
    except Exception as exc:
        return _fallback_result(
            paper,
            index,
            f"AI 请求失败（{_short_error(exc)}），暂按摘要内容与中等重要性展示。",
            f"request failed: {_short_error(exc)}",
        )


def _store_summary_result(
    result: _PaperSummaryResult,
    summaries: list[PaperSummary | None],
    raw_responses: list[str],
) -> None:
    summaries[result.index - 1] = result.summary
    raw_responses[result.index - 1] = result.raw_response


def build_fallback_summary(papers: list[Paper], report_date: date) -> DailySummary:
    if not papers:
        return DailySummary(overview="No new papers matched the configured arXiv topics for this run.")

    return DailySummary(
        overview=_build_fallback_overview(papers, report_date),
        paper_summaries=tuple(_fallback_paper_summary(paper) for paper in papers),
    )


def _summarize_one_paper(
    paper: Paper,
    config: AIConfig,
    report_date: date,
    index: int,
    total_count: int,
    status: StatusLogger | None,
) -> _PaperSummaryResult:
    last_raw_response = ""
    for attempt in range(1, AI_RESPONSE_RETRY_COUNT + 2):
        _log(
            status,
            f"AI: running request {index}/{total_count} for {paper.arxiv_id} "
            f"(attempt {attempt}/{AI_RESPONSE_RETRY_COUNT + 1})",
        )
        try:
            content = _request_paper_summary(paper, config, report_date, index, total_count)
        except Exception as exc:
            if attempt > AI_RESPONSE_RETRY_COUNT:
                return _fallback_result(
                    paper,
                    index,
                    f"AI 请求失败（{_short_error(exc)}），暂按摘要内容与中等重要性展示。",
                    f"request failed after retries: {_short_error(exc)}",
                )
            _wait_before_ai_retry(status, paper, index, total_count, attempt, _short_error(exc))
            continue

        last_raw_response = f"{paper.arxiv_id}\n{content}"
        paper_summary = _parse_paper_summary(content, paper)
        if paper_summary is not None:
            return _PaperSummaryResult(
                index=index,
                summary=paper_summary,
                raw_response=last_raw_response,
                used_fallback=False,
                message="",
            )

        if attempt > AI_RESPONSE_RETRY_COUNT:
            return _fallback_result(
                paper,
                index,
                "AI 多次未返回可解析的结构化结果，暂按摘要内容与中等重要性展示。",
                "response was not valid structured JSON after retries",
                last_raw_response,
            )
        _wait_before_ai_retry(status, paper, index, total_count, attempt, "response was not valid structured JSON")

    return _fallback_result(
        paper,
        index,
        "AI 未返回可解析的结构化结果，暂按摘要内容与中等重要性展示。",
        "response was not valid structured JSON",
        last_raw_response,
    )


def _wait_before_ai_retry(
    status: StatusLogger | None,
    paper: Paper,
    index: int,
    total_count: int,
    attempt: int,
    reason: str,
) -> None:
    delay = AI_RESPONSE_RETRY_BACKOFF_SECONDS * attempt
    _log(
        status,
        f"AI: retrying request {index}/{total_count} for {paper.arxiv_id} "
        f"in {delay:.1f}s after {reason}",
    )
    time.sleep(delay)


def _fallback_result(
    paper: Paper,
    index: int,
    reason: str,
    message: str,
    raw_response: str = "",
) -> _PaperSummaryResult:
    return _PaperSummaryResult(
        index=index,
        summary=_fallback_paper_summary(paper, reason, raw_response),
        raw_response=raw_response,
        used_fallback=True,
        message=message,
    )


def _request_paper_summary(
    paper: Paper,
    config: AIConfig,
    report_date: date,
    index: int,
    total_count: int,
) -> str:
    payload = {
        "model": config.model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a careful research assistant. Write concise daily arXiv digests. "
                    "Return strict JSON only. Do not invent claims that are not supported by the supplied metadata "
                    "or abstract."
                ),
            },
            {
                "role": "user",
                "content": _build_paper_prompt(paper, config.language, report_date, index, total_count),
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
        raise RuntimeError(f"AI service returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"AI service request failed: {exc.reason}") from exc

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Unexpected AI response shape") from exc


def _build_paper_prompt(
    paper: Paper,
    language: str,
    report_date: date,
    index: int,
    total_count: int,
) -> str:
    return (
        f"Report date: {report_date.isoformat()}\n"
        f"Daily paper count: {total_count}\n"
        f"Current paper index: {index}/{total_count}\n"
        f"Output language: {language}\n\n"
        "Return ONLY valid JSON. Do not wrap it in Markdown fences. Use this exact shape:\n"
        "{\n"
        '  "arxiv_id": "same arxiv_id from the input, preserving the version suffix such as v1",\n'
        '  "chinese_title": "accurate Chinese translation of the title",\n'
        '  "summary": "Chinese summary in 80-140 Chinese characters: problem, method, key result/contribution.",\n'
        '  "importance": 1,\n'
        '  "importance_reason": "One Chinese sentence explaining the importance rating."\n'
        "}\n\n"
        "Use the same fixed rating standard for every paper in today's run. Do not score relatively against only "
        "this one paper, and do not inflate scores because the request contains a single paper. Importance is an "
        "integer from 1 to 5:\n"
        "5 = likely field-shaping, broadly useful, or unusually strong evidence/method/release;\n"
        "4 = strong contribution worth prioritizing for the topic;\n"
        "3 = solid but specialized or mainly useful to a narrower audience;\n"
        "2 = incremental, limited scope, or unclear empirical strength;\n"
        "1 = low confidence, routine, or insufficient information in the abstract.\n"
        "If the abstract does not support a claim, say it is not specified.\n\n"
        "Paper JSON:\n"
        f"{json.dumps(_paper_payload(paper), ensure_ascii=False, indent=2)}"
    )


def _paper_payload(paper: Paper) -> dict[str, object]:
    return {
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


def _parse_paper_summary(content: str, paper: Paper) -> PaperSummary | None:
    try:
        data = json.loads(_extract_json_object(content))
    except json.JSONDecodeError:
        return None
    item = _extract_paper_summary_object(data, paper)
    if item is None:
        return None

    summary = str(item.get("summary", "")).strip()
    if not summary:
        return None
    return PaperSummary(
        arxiv_id=paper.arxiv_id,
        chinese_title=str(item.get("chinese_title", "")).strip(),
        summary=summary,
        importance=_coerce_importance(item.get("importance", 3)),
        importance_reason=str(item.get("importance_reason", "")).strip() or "AI 未提供评级理由。",
    )


def _extract_paper_summary_object(data: object, paper: Paper) -> dict[str, object] | None:
    if isinstance(data, dict) and "papers" not in data:
        return data
    if isinstance(data, dict) and isinstance(data.get("papers"), list):
        for item in data["papers"]:
            if not isinstance(item, dict):
                continue
            arxiv_id = str(item.get("arxiv_id", "")).strip()
            if not arxiv_id or normalize_arxiv_id(arxiv_id) == normalize_arxiv_id(paper.arxiv_id):
                return item
    return None


def _build_overview(summaries: list[PaperSummary], report_date: date, fallback_count: int) -> str:
    if not summaries:
        return f"{report_date.isoformat()} 没有可用于生成趋势总览的论文。"

    ranked = sorted(
        summaries,
        key=lambda item: (
            -_coerce_importance(item.importance),
            normalize_arxiv_id(item.arxiv_id),
        ),
    )
    high_priority = [item for item in ranked if _coerce_importance(item.importance) >= 4]
    featured = high_priority[:3] or ranked[:3]
    focus = "；".join(_paper_label(item) for item in featured)
    high_count = len(high_priority)

    if high_count:
        trend = (
            f"其中 {high_count} 篇达到 4 分以上，整体更值得从方法创新、关键观测结果或可复用数据资源的角度优先阅读。"
        )
    else:
        trend = "整体以细分问题、局部验证或专门场景的增量推进为主，适合按个人研究方向筛选阅读。"

    overview = f"今日论文的主要关注点集中在：{focus}。{trend}"
    if fallback_count:
        overview += f" 另有 {fallback_count} 篇因 AI 响应异常或不可解析仅基于原始摘要回退，相关判断需保守解读。"
    return overview


def _build_fallback_overview(papers: list[Paper], report_date: date) -> str:
    titles = "；".join(paper.title for paper in papers[:3])
    return (
        f"{report_date.isoformat()} 的论文主要覆盖：{titles}。"
        "由于本次未调用 AI，总览仅依据原始标题与摘要生成，适合用于快速定位候选文章。"
    )


def _build_shortlist(summaries: list[PaperSummary]) -> tuple[str, ...]:
    ranked = sorted(summaries, key=lambda item: (-item.importance, normalize_arxiv_id(item.arxiv_id)))
    selected = [item for item in ranked if item.importance >= 4][:5]
    return tuple(
        f"{item.arxiv_id}：{_paper_label(item)}，重要性 {item.importance}/5，{item.importance_reason}"
        for item in selected
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


def _coerce_importance(value: object) -> int:
    try:
        importance = int(value)
    except (TypeError, ValueError):
        return 3
    return min(5, max(1, importance))


def _fallback_paper_summary(
    paper: Paper,
    reason: str | None = None,
    raw_response: str = "",
) -> PaperSummary:
    abstract = paper.abstract[:260] + ("..." if len(paper.abstract) > 260 else "")
    return PaperSummary(
        arxiv_id=paper.arxiv_id,
        chinese_title="",
        summary=abstract,
        importance=3,
        importance_reason=reason or "AI 未提供结构化评级，暂按中等重要性展示。",
        raw_response=_raw_response_excerpt(_paper_raw_response(paper, raw_response)),
    )


def _paper_label(summary: PaperSummary) -> str:
    return summary.chinese_title or summary.summary[:40]


def _raw_response_excerpt(value: str, max_chars: int = 1800) -> str:
    stripped = value.strip()
    if len(stripped) <= max_chars:
        return stripped
    return stripped[:max_chars].rstrip() + "\n... [truncated]"


def _paper_raw_response(paper: Paper, raw_response: str) -> str:
    prefix = f"{paper.arxiv_id}\n"
    if raw_response.startswith(prefix):
        return raw_response[len(prefix) :]
    return raw_response


def _short_error(exc: BaseException) -> str:
    message = str(exc).strip()
    return message or exc.__class__.__name__


def _log(status: StatusLogger | None, message: str) -> None:
    if status:
        status(message)


def _chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"
