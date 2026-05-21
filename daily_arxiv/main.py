from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .ai_client import DailySummary, build_fallback_summary, summarize_papers
from .arxiv_client import (
    ArxivFetchStats,
    Paper,
    fetch_new_papers_with_stats,
    normalize_arxiv_id,
)
from .config import ConfigError, DigestConfig, EmailConfig, load_config, validate_email_config
from .emailer import send_email
from .render import build_html_digest, build_subject, build_text_digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch arXiv papers, summarize them with AI, and send an email digest.")
    parser.add_argument("--config", default="config.toml", help="Path to TOML config file.")
    parser.add_argument("--no-email", action="store_true", help="Print the digest instead of sending email.")
    parser.add_argument("--skip-ai", action="store_true", help="Build a debug digest without calling the AI service.")
    args = parser.parse_args(argv)

    try:
        _status(f"Loading config from {args.config}")
        config = load_config(Path(args.config))
        _status(
            f"Config loaded: {len(config.arxiv.topics)} topic(s), "
            f"lookback_days={config.arxiv.lookback_days}, "
            f"max_results_per_topic={config.arxiv.max_results_per_topic}"
        )
        if not args.no_email:
            _status("Validating email configuration")
            validate_email_config(config.email)

        report_date = _local_date(config.arxiv.timezone)
        _status(f"Report date resolved as {report_date.isoformat()} in {config.arxiv.timezone}")
        fetch_error = ""
        fetch_stats: ArxivFetchStats | None = None
        try:
            _status("Starting arXiv fetch")
            papers, fetch_stats = fetch_new_papers_with_stats(config.arxiv, status=_status)
            _status(f"arXiv fetch complete: {len(papers)} unique paper(s)")
        except Exception as exc:
            if not config.arxiv.allow_fetch_failure:
                raise
            papers = []
            fetch_error = str(exc)
            print(f"arXiv fetch failed; sending failure digest instead: {fetch_error}", file=sys.stderr)

        if fetch_error:
            _status("Building arXiv failure digest")
            summary = _fetch_failure_summary(fetch_error, report_date)
        elif args.skip_ai:
            _status("AI summarization skipped by --skip-ai")
            summary = build_fallback_summary(papers, report_date)
        else:
            summary = summarize_papers(papers, config.ai, report_date, status=_status)

        _status("Applying display priority filter")
        display_papers, filter_note = _apply_priority_filter(papers, summary, config.digest)
        if filter_note:
            summary = replace(summary, overview=f"{summary.overview.strip()}\n\n{filter_note}")

        _status(f"Rendering digest: {len(display_papers)} displayed paper(s)")
        subject = (
            f"{config.email.subject_prefix} - {report_date.isoformat()} - arXiv fetch failed"
            if fetch_error
            else build_subject(config.email.subject_prefix, report_date, len(display_papers))
        )
        text_body = build_text_digest(summary, display_papers, report_date, fetch_stats, papers)
        html_body = build_html_digest(summary, display_papers, report_date, fetch_stats, papers)

        if args.no_email:
            _status("No-email mode enabled; printing text digest")
            print(text_body)
            _status("Run complete")
            return 0

        _status(
            f"Sending email to {len(config.email.mail_to)} recipient(s) "
            f"via {config.email.smtp_host}:{config.email.smtp_port} ({_smtp_mode(config.email)})"
        )
        send_email(config.email, subject, text_body, html_body)
        print(f"Sent digest with {len(papers)} fetched papers and {len(display_papers)} displayed papers")
        _status("Run complete")
        return 0
    except (ConfigError, ZoneInfoNotFoundError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Runtime error: {exc}", file=sys.stderr)
        return 1


def _local_date(timezone: str) -> date:
    return datetime.now(ZoneInfo(timezone)).date()


def _status(message: str) -> None:
    print(f"[daily-arxiv] {message}", file=sys.stderr, flush=True)


def _smtp_mode(email_config: EmailConfig) -> str:
    if email_config.smtp_use_ssl:
        return "SSL"
    if email_config.smtp_use_tls:
        return "STARTTLS"
    return "plain"


def _apply_priority_filter(
    papers: list[Paper],
    summary: DailySummary,
    config: DigestConfig,
) -> tuple[list[Paper], str]:
    if not config.priority_filter_enabled or len(papers) <= config.priority_filter_min_total:
        return papers, ""

    importance_by_id = {
        normalize_arxiv_id(item.arxiv_id): item.importance
        for item in summary.paper_summaries
    }

    ranked = sorted(
        papers,
        key=lambda paper: (
            -importance_by_id.get(normalize_arxiv_id(paper.arxiv_id), 0),
            -paper.published.timestamp(),
        ),
    )
    selected = [
        paper
        for paper in ranked
        if importance_by_id.get(normalize_arxiv_id(paper.arxiv_id), 0) >= config.priority_filter_min_importance
    ]

    if not selected:
        selected = ranked
        threshold_note = (
            f"没有论文达到重要性 {config.priority_filter_min_importance}/5，"
            "因此改为展示评分最高的论文。"
        )
    else:
        threshold_note = f"仅展示重要性 {config.priority_filter_min_importance}/5 及以上论文。"

    if config.priority_filter_max_papers:
        selected = selected[: config.priority_filter_max_papers]

    note = (
        f"展示筛选：本次共抓取 {len(papers)} 篇论文，超过配置阈值 "
        f"{config.priority_filter_min_total} 篇。{threshold_note}"
        f"最终展示 {len(selected)} 篇。"
    )
    return selected, note


def _fetch_failure_summary(error: str, report_date: date) -> DailySummary:
    return DailySummary(
        overview=(
            f"arXiv paper fetching failed after the configured retries on {report_date.isoformat()}, "
            "so no AI summary was generated for this run.\n\n"
            "The most likely cause is temporary arXiv API rate limiting or network timeout from the GitHub Actions runner.\n\n"
            f"Error: {error}"
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
