from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .ai_client import build_fallback_summary, summarize_papers
from .arxiv_client import fetch_new_papers
from .config import ConfigError, load_config, validate_email_config
from .emailer import send_email
from .render import build_html_digest, build_subject, build_text_digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch arXiv papers, summarize them with AI, and send an email digest.")
    parser.add_argument("--config", default="config.toml", help="Path to TOML config file.")
    parser.add_argument("--no-email", action="store_true", help="Print the digest instead of sending email.")
    parser.add_argument("--skip-ai", action="store_true", help="Build a debug digest without calling the AI service.")
    args = parser.parse_args(argv)

    try:
        config = load_config(Path(args.config))
        if not args.no_email:
            validate_email_config(config.email)

        report_date = _local_date(config.arxiv.timezone)
        fetch_error = ""
        try:
            papers = fetch_new_papers(config.arxiv)
        except Exception as exc:
            if not config.arxiv.allow_fetch_failure:
                raise
            papers = []
            fetch_error = str(exc)
            print(f"arXiv fetch failed; sending failure digest instead: {fetch_error}", file=sys.stderr)

        if fetch_error:
            summary = _fetch_failure_summary(fetch_error, report_date)
        elif args.skip_ai:
            summary = build_fallback_summary(papers, report_date)
        else:
            summary = summarize_papers(papers, config.ai, report_date)

        subject = (
            f"{config.email.subject_prefix} - {report_date.isoformat()} - arXiv fetch failed"
            if fetch_error
            else build_subject(config.email.subject_prefix, report_date, len(papers))
        )
        text_body = build_text_digest(summary, papers, report_date)
        html_body = build_html_digest(summary, papers, report_date)

        if args.no_email:
            print(text_body)
            return 0

        send_email(config.email, subject, text_body, html_body)
        print(f"Sent digest with {len(papers)} papers to {', '.join(config.email.mail_to)}")
        return 0
    except (ConfigError, ZoneInfoNotFoundError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Runtime error: {exc}", file=sys.stderr)
        return 1


def _local_date(timezone: str) -> date:
    return datetime.now(ZoneInfo(timezone)).date()


def _fetch_failure_summary(error: str, report_date: date) -> str:
    return (
        f"arXiv paper fetching failed after the configured retries on {report_date.isoformat()}, "
        "so no AI summary was generated for this run.\n\n"
        "The most likely cause is temporary arXiv API rate limiting or network timeout from the GitHub Actions runner.\n\n"
        f"Error: {error}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
