from __future__ import annotations

import sys
import time
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import arxiv
import requests

from .config import ArxivConfig, ConfigError, TopicConfig


TRANSIENT_HTTP_STATUSES = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class Paper:
    arxiv_id: str
    title: str
    authors: tuple[str, ...]
    abstract: str
    published: datetime
    updated: datetime
    link: str
    pdf_url: str
    primary_category: str
    categories: tuple[str, ...]
    topics: tuple[str, ...]
    comment: str = ""


def fetch_new_papers(config: ArxivConfig, now: datetime | None = None) -> list[Paper]:
    now_utc = (now or datetime.now(UTC)).astimezone(UTC)
    since = now_utc - timedelta(days=config.lookback_days)
    papers_by_id: dict[str, Paper] = {}

    for index, topic in enumerate(config.topics):
        if index > 0 and config.request_delay_seconds > 0:
            time.sleep(config.request_delay_seconds)

        for paper in _fetch_topic(topic, config, since):
            existing = papers_by_id.get(paper.arxiv_id)
            if existing is None:
                papers_by_id[paper.arxiv_id] = paper
            elif topic.name not in existing.topics:
                papers_by_id[paper.arxiv_id] = replace(existing, topics=existing.topics + (topic.name,))

    return sorted(papers_by_id.values(), key=lambda paper: paper.published, reverse=True)


def _fetch_topic(topic: TopicConfig, config: ArxivConfig, since: datetime) -> list[Paper]:
    for attempt in range(config.retry_count + 1):
        try:
            return _fetch_topic_once(topic, config, since)
        except arxiv.HTTPError as exc:
            if exc.status not in TRANSIENT_HTTP_STATUSES or attempt >= config.retry_count:
                raise RuntimeError(f"arXiv API returned HTTP {exc.status} after {attempt + 1} attempt(s)") from exc
            _sleep_before_retry(config, attempt, f"HTTP {exc.status}")
        except (arxiv.UnexpectedEmptyPageError, requests.exceptions.RequestException) as exc:
            if attempt >= config.retry_count:
                raise RuntimeError(f"arXiv API request failed after {attempt + 1} attempt(s): {exc}") from exc
            _sleep_before_retry(config, attempt, str(exc))

    raise RuntimeError("arXiv API request failed unexpectedly")


def _fetch_topic_once(topic: TopicConfig, config: ArxivConfig, since: datetime) -> list[Paper]:
    client = arxiv.Client(
        page_size=config.max_results_per_topic,
        delay_seconds=max(3.0, config.request_delay_seconds),
        num_retries=0,
    )
    _set_client_timeout(client, config.timeout_seconds)
    search = arxiv.Search(
        query=topic.query,
        max_results=config.max_results_per_topic,
        sort_by=_sort_criterion(config.sort_by),
        sort_order=_sort_order(config.sort_order),
    )

    papers: list[Paper] = []
    for result in client.results(search):
        paper = _paper_from_result(result, topic)
        if paper.published >= since:
            papers.append(paper)
    return papers


def _set_client_timeout(client: arxiv.Client, timeout_seconds: int) -> None:
    original_get = client._session.get

    def get_with_timeout(url: str, **kwargs: object) -> requests.Response:
        kwargs.setdefault("timeout", timeout_seconds)
        return original_get(url, **kwargs)

    client._session.get = get_with_timeout


def _sleep_before_retry(config: ArxivConfig, attempt: int, reason: str) -> None:
    delay = config.retry_backoff_seconds * (attempt + 1)
    if delay > 0:
        print(
            f"arXiv request failed with {reason}; retrying in {delay:.0f}s "
            f"(attempt {attempt + 2}/{config.retry_count + 1})",
            file=sys.stderr,
        )
        time.sleep(delay)


def _paper_from_result(result: arxiv.Result, topic: TopicConfig) -> Paper:
    return Paper(
        arxiv_id=result.get_short_id(),
        title=_clean_text(result.title),
        authors=tuple(_clean_text(author.name) for author in result.authors if author.name),
        abstract=_clean_text(result.summary),
        published=_as_utc(result.published),
        updated=_as_utc(result.updated),
        link=result.entry_id,
        pdf_url=result.pdf_url or "",
        primary_category=result.primary_category,
        categories=tuple(result.categories),
        topics=(topic.name,),
        comment=_clean_text(result.comment or ""),
    )


def normalize_arxiv_id(value: str) -> str:
    arxiv_id = value.strip().rsplit("/", 1)[-1]
    return re.sub(r"v\d+$", "", arxiv_id)


def _sort_criterion(value: str) -> arxiv.SortCriterion:
    normalized = value.strip().lower()
    for criterion in arxiv.SortCriterion:
        if criterion.value.lower() == normalized:
            return criterion
    valid = ", ".join(criterion.value for criterion in arxiv.SortCriterion)
    raise ConfigError(f"arxiv.sort_by must be one of: {valid}")


def _sort_order(value: str) -> arxiv.SortOrder:
    normalized = value.strip().lower()
    for order in arxiv.SortOrder:
        if order.value.lower() == normalized:
            return order
    valid = ", ".join(order.value for order in arxiv.SortOrder)
    raise ConfigError(f"arxiv.sort_order must be one of: {valid}")


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
