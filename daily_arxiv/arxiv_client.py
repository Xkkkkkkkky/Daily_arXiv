from __future__ import annotations

import time
import socket
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from .config import ArxivConfig, TopicConfig


ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATOM_NS = "http://www.w3.org/2005/Atom"
ARXIV_NS = "http://arxiv.org/schemas/atom"
NS = {"atom": ATOM_NS, "arxiv": ARXIV_NS}
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
    query = urllib.parse.urlencode(
        {
            "search_query": topic.query,
            "start": 0,
            "max_results": config.max_results_per_topic,
            "sortBy": config.sort_by,
            "sortOrder": config.sort_order,
        }
    )
    request = urllib.request.Request(
        f"{ARXIV_API_URL}?{query}",
        headers={"User-Agent": "daily-arxiv/0.1 (+https://github.com)"},
    )

    body = _read_response(request, config)
    root = ET.fromstring(body)
    papers: list[Paper] = []
    for entry in root.findall("atom:entry", NS):
        paper = _parse_entry(entry, topic)
        if paper.published >= since:
            papers.append(paper)
    return papers


def _read_response(request: urllib.request.Request, config: ArxivConfig) -> bytes:
    for attempt in range(config.retry_count + 1):
        try:
            with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in TRANSIENT_HTTP_STATUSES or attempt >= config.retry_count:
                detail = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"arXiv API returned HTTP {exc.code}: {detail[:500]}") from exc
            _sleep_before_retry(config, attempt)
        except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
            if attempt >= config.retry_count:
                raise RuntimeError(f"arXiv API request failed after {attempt + 1} attempt(s): {exc}") from exc
            _sleep_before_retry(config, attempt)

    raise RuntimeError("arXiv API request failed unexpectedly")


def _sleep_before_retry(config: ArxivConfig, attempt: int) -> None:
    delay = config.retry_backoff_seconds * (attempt + 1)
    if delay > 0:
        time.sleep(delay)


def _parse_entry(entry: ET.Element, topic: TopicConfig) -> Paper:
    arxiv_url = _text(entry, "atom:id")
    arxiv_id = arxiv_url.rstrip("/").rsplit("/", 1)[-1]
    primary_category = entry.find("arxiv:primary_category", NS)
    categories = tuple(
        category.attrib.get("term", "")
        for category in entry.findall("atom:category", NS)
        if category.attrib.get("term")
    )

    link = arxiv_url
    pdf_url = ""
    for link_node in entry.findall("atom:link", NS):
        rel = link_node.attrib.get("rel")
        href = link_node.attrib.get("href", "")
        title = link_node.attrib.get("title")
        if rel == "alternate" and href:
            link = href
        if title == "pdf" and href:
            pdf_url = href

    return Paper(
        arxiv_id=arxiv_id,
        title=_clean_text(_text(entry, "atom:title")),
        authors=tuple(
            _clean_text(_text(author, "atom:name"))
            for author in entry.findall("atom:author", NS)
            if _text(author, "atom:name")
        ),
        abstract=_clean_text(_text(entry, "atom:summary")),
        published=_parse_datetime(_text(entry, "atom:published")),
        updated=_parse_datetime(_text(entry, "atom:updated")),
        link=link,
        pdf_url=pdf_url,
        primary_category=primary_category.attrib.get("term", "") if primary_category is not None else "",
        categories=categories,
        topics=(topic.name,),
    )


def _text(node: ET.Element, path: str) -> str:
    child = node.find(path, NS)
    return child.text if child is not None and child.text is not None else ""


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _parse_datetime(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
