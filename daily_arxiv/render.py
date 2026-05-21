from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date

from .ai_client import DailySummary, PaperSummary
from .arxiv_client import (
    ArxivFetchStats,
    Paper,
    TopicFetchStats,
    normalize_arxiv_id,
)


@dataclass(frozen=True)
class DigestDisplayStats:
    total_fetched: int
    displayed: int
    strategy: str
    importance_filter: str = ""


@dataclass(frozen=True)
class TopicStyle:
    background: str
    border: str
    accent: str
    soft: str
    text: str


TOPIC_PALETTE = (
    TopicStyle("#f8fbff", "#bfdbfe", "#2563eb", "#eff6ff", "#1e3a8a"),
    TopicStyle("#f8fffb", "#bbf7d0", "#16a34a", "#f0fdf4", "#14532d"),
    TopicStyle("#fffbeb", "#fde68a", "#d97706", "#fffbeb", "#78350f"),
    TopicStyle("#fdf7ff", "#e9d5ff", "#9333ea", "#faf5ff", "#581c87"),
    TopicStyle("#fff7f7", "#fecaca", "#dc2626", "#fef2f2", "#7f1d1d"),
    TopicStyle("#f7fffe", "#99f6e4", "#0d9488", "#f0fdfa", "#134e4a"),
)


def build_subject(prefix: str, report_date: date, paper_count: int) -> str:
    suffix = "paper" if paper_count == 1 else "papers"
    return f"{prefix} - {report_date.isoformat()} - {paper_count} {suffix}"


def build_text_digest(
    summary: DailySummary,
    papers: list[Paper],
    report_date: date,
    fetch_stats: ArxivFetchStats | None = None,
    all_papers: list[Paper] | None = None,
    display_stats: DigestDisplayStats | None = None,
) -> str:
    insights = _insights_by_id(summary)
    display_stats = display_stats or DigestDisplayStats(len(all_papers or papers), len(papers), "未配置筛选信息")
    lines = [
        f"Daily arXiv Digest - {report_date.isoformat()}",
        f"Fetched: {display_stats.total_fetched}; Displayed: {display_stats.displayed}",
        f"Filter: {display_stats.strategy}",
        "",
        "Overview:",
        summary.overview.strip(),
        "",
    ]

    if summary.shortlist:
        lines.append("Worth reading first:")
        lines.extend(f"- {item}" for item in summary.shortlist)
        lines.append("")

    if not papers:
        lines.append("No new papers matched the configured topics.")
        data_lines = _text_data_overview(summary, all_papers or papers, fetch_stats)
        if data_lines:
            lines.extend(["", *data_lines])
        return "\n".join(lines).strip() + "\n"

    lines.append("Papers:")
    for index, paper in enumerate(papers, start=1):
        insight = insights.get(normalize_arxiv_id(paper.arxiv_id), _empty_insight(paper))
        lines.extend(
            [
                "",
                f"{index}. {paper.title}",
                f"   Authors: {_format_authors(paper)}",
                f"   Importance: {insight.importance}/5 - {insight.importance_reason}",
                f"   Comments: {_format_comments(paper)}",
                f"   Subjects: {_format_subjects(paper)}",
                f"   Chinese title: {insight.chinese_title or 'Not provided'}",
                f"   Summary: {insight.summary}",
                *(_text_raw_response_lines(insight.raw_response) if insight.raw_response else []),
                f"   arXiv: {paper.link}",
                f"   PDF: {paper.pdf_url or 'N/A'}",
            ]
        )
    data_lines = _text_data_overview(summary, all_papers or papers, fetch_stats)
    if data_lines:
        lines.extend(["", *data_lines])
    return "\n".join(lines).strip() + "\n"


def build_html_digest(
    summary: DailySummary,
    papers: list[Paper],
    report_date: date,
    fetch_stats: ArxivFetchStats | None = None,
    all_papers: list[Paper] | None = None,
    display_stats: DigestDisplayStats | None = None,
) -> str:
    insights = _insights_by_id(summary)
    source_papers = all_papers or papers
    display_stats = display_stats or DigestDisplayStats(len(source_papers), len(papers), "未配置筛选信息")
    topic_styles = _topic_styles(fetch_stats, source_papers)
    paper_cards = "\n".join(
        _paper_card(index, paper, insights, _paper_style(paper, topic_styles))
        for index, paper in enumerate(papers, start=1)
    )
    if not paper_cards:
        paper_cards = _empty_state()

    shortlist = _shortlist_block(summary)
    displayed_ids = {normalize_arxiv_id(paper.arxiv_id) for paper in papers}
    data_overview = _html_data_overview(summary, source_papers, fetch_stats, topic_styles, displayed_ids)
    preheader = f"Daily arXiv digest for {report_date.isoformat()} with {len(papers)} papers."

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Daily arXiv Digest</title>
</head>
<body style="margin:0; padding:0; background:#f3f6fb; color:#1f2937; font-family:Arial, 'Microsoft YaHei', sans-serif;">
  <div style="display:none; max-height:0; overflow:hidden; opacity:0;">{html.escape(preheader)}</div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f6fb; margin:0; padding:0;">
    <tr>
      <td align="center" style="padding:28px 12px;">
        <table role="presentation" width="760" cellspacing="0" cellpadding="0" style="width:100%; max-width:760px; border-collapse:separate; border-spacing:0;">
          <tr>
            <td style="background:#16213e; color:#ffffff; padding:28px 30px; border-radius:14px 14px 0 0;">
              <div style="font-size:12px; letter-spacing:0; text-transform:uppercase; color:#a8c7ff; font-weight:700;">Daily arXiv</div>
              <h1 style="margin:8px 0 8px; font-size:28px; line-height:1.25; font-weight:800;">{html.escape(report_date.isoformat())} 论文速览</h1>
              {_hero_stats(display_stats)}
            </td>
          </tr>
          <tr>
            <td style="background:#ffffff; padding:24px 30px 8px; border-left:1px solid #dbe3ef; border-right:1px solid #dbe3ef;">
              {_paragraph_block(summary.overview)}
              {shortlist}
            </td>
          </tr>
          <tr>
            <td style="background:#ffffff; padding:8px 30px 30px; border-left:1px solid #dbe3ef; border-right:1px solid #dbe3ef; border-bottom:1px solid #dbe3ef; border-radius:0 0 14px 14px;">
              {paper_cards}
              {data_overview}
            </td>
          </tr>
          <tr>
            <td style="padding:16px 4px 0; color:#6b7280; font-size:12px; line-height:1.5;">
              本邮件由 GitHub Actions 自动生成。评分基于论文标题与摘要，由 AI 按 1-5 分估计研究重要性，仅供筛选阅读优先级。
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _hero_stats(display_stats: DigestDisplayStats) -> str:
    importance_filter = display_stats.importance_filter or "未筛选"
    return f"""
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:12px; max-width:620px; border-collapse:separate; border-spacing:0;">
                <tr>
                  <td width="50%" style="padding:9px 12px; background:#223159; border:1px solid #3b5285; border-radius:8px 0 0 8px; color:#dbe7ff; font-size:12px; font-weight:700;">文章数<br><span style="display:inline-block; margin-top:3px; color:#ffffff; font-size:18px; font-weight:800;">{display_stats.total_fetched} 篇</span></td>
                  <td width="50%" style="padding:9px 12px; background:#223159; border-top:1px solid #3b5285; border-right:1px solid #3b5285; border-bottom:1px solid #3b5285; border-radius:0 8px 8px 0; color:#dbe7ff; font-size:12px; font-weight:700;">
                    展示数
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:3px; border-collapse:collapse;">
                      <tr>
                        <td style="color:#ffffff; font-size:18px; font-weight:800;">{display_stats.displayed} 篇</td>
                        <td align="right" valign="bottom" style="color:#a8c7ff; font-size:11px; font-weight:800; white-space:nowrap;">{html.escape(importance_filter)}</td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>"""


def _topic_styles(fetch_stats: ArxivFetchStats | None, papers: list[Paper]) -> dict[str, TopicStyle]:
    topic_names: list[str] = []

    def add_topic(name: str) -> None:
        if name and name not in topic_names:
            topic_names.append(name)

    if fetch_stats is not None:
        for topic in fetch_stats.topics:
            add_topic(topic.name)
    for paper in papers:
        for topic in paper.topics:
            add_topic(topic)
    return {
        name: TOPIC_PALETTE[index % len(TOPIC_PALETTE)]
        for index, name in enumerate(topic_names)
    }


def _paper_style(paper: Paper, topic_styles: dict[str, TopicStyle]) -> TopicStyle:
    for topic in paper.topics:
        if topic in topic_styles:
            return topic_styles[topic]
    return TOPIC_PALETTE[0]


def _paper_card(index: int, paper: Paper, insights: dict[str, PaperSummary], style: TopicStyle) -> str:
    insight = insights.get(normalize_arxiv_id(paper.arxiv_id), _empty_insight(paper))
    authors = _format_authors(paper)
    comments = _format_comments(paper)
    subjects = _format_subjects(paper)
    topics = ", ".join(paper.topics)
    pdf_link = _link_button(paper.pdf_url, "PDF") if paper.pdf_url else ""
    chinese_title = (
        f'<div style="font-size:17px; line-height:1.45; color:#0f766e; font-weight:700; margin:8px 0 10px;">{html.escape(insight.chinese_title)}</div>'
        if insight.chinese_title
        else ""
    )
    raw_response = _raw_response_block(insight.raw_response)
    anchor = _paper_anchor_id(paper.arxiv_id)

    return f"""
              <a id="{html.escape(anchor)}" name="{html.escape(anchor)}"></a>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border:1px solid {style.border}; border-radius:12px; margin:0 0 16px; background:{style.background};">
                <tr>
                  <td style="padding:20px 20px 18px;">
                    <div style="font-size:12px; color:{style.text}; font-weight:800; margin-bottom:8px;">论文 {index} · {html.escape(topics)}</div>
                    <a href="{html.escape(paper.link)}" style="font-size:19px; line-height:1.35; color:#0b63ce; font-weight:800; text-decoration:none;">{html.escape(paper.title)}</a>
                    {chinese_title}
                    <div style="margin:10px 0 12px; padding:10px 12px; background:{style.soft}; border:1px solid {style.border}; border-radius:8px;">
                      <span style="font-size:13px; color:#475569; font-weight:800;">作者：</span>
                      <span style="font-size:13px; line-height:1.65; color:#334155;">{html.escape(authors)}</span>
                      <div style="margin-top:8px;">
                        <span style="font-size:13px; color:#475569; font-weight:800;">重要性：</span>
                        {_rating_badge(insight.importance)}
                      </div>
                      <div style="margin-top:8px;">
                        <span style="font-size:13px; color:#475569; font-weight:800;">Comments：</span>
                        <span style="font-size:13px; line-height:1.65; color:#334155;">{html.escape(comments)}</span>
                      </div>
                      <div style="margin-top:8px;">
                        <span style="font-size:13px; color:#475569; font-weight:800;">Subjects：</span>
                        <span style="font-size:13px; line-height:1.65; color:#334155;">{html.escape(subjects)}</span>
                      </div>
                    </div>
                    <div style="margin:14px 0 0; padding:14px 16px; background:#ffffff; border-left:4px solid {style.accent}; border-radius:8px;">
                      <div style="font-size:13px; color:#374151; font-weight:800; margin-bottom:6px;">摘要</div>
                      <div style="font-size:15px; line-height:1.72; color:#1f2937;">{html.escape(insight.summary)}</div>
                      {raw_response}
                    </div>
                    <div style="margin:12px 0 0; padding:12px 14px; background:#fff8eb; border:1px solid #f4d59e; border-radius:8px;">
                      <span style="font-size:13px; color:#92400e; font-weight:800;">评级理由：</span>
                      <span style="font-size:14px; line-height:1.65; color:#4b5563;">{html.escape(insight.importance_reason)}</span>
                    </div>
                    <div style="font-size:12px; line-height:1.6; color:#667085; margin:14px 0 0;">
                      arXiv:{html.escape(paper.arxiv_id)} · {html.escape(paper.published.date().isoformat())}
                    </div>
                    <div style="margin-top:14px;">
                      {_link_button(paper.link, "arXiv")}
                      {pdf_link}
                    </div>
                  </td>
                </tr>
              </table>"""


def _raw_response_block(raw_response: str) -> str:
    if not raw_response:
        return ""
    return f"""
                      <div style="margin-top:10px; padding:9px 10px; background:#f8fafc; border:1px solid #edf2f7; border-radius:6px;">
                        <div style="font-size:11px; color:#94a3b8; font-weight:700; margin-bottom:5px;">AI 原始响应（未解析）</div>
                        <pre style="margin:0; white-space:pre-wrap; word-break:break-word; font-family:Consolas, Menlo, monospace; font-size:11px; line-height:1.45; color:#94a3b8;">{html.escape(raw_response)}</pre>
                      </div>"""


def _text_raw_response_lines(raw_response: str) -> list[str]:
    return [
        "   AI raw response (unparsed):",
        *[f"     {line}" for line in raw_response.splitlines()],
    ]


def _html_data_overview(
    summary: DailySummary,
    papers: list[Paper],
    fetch_stats: ArxivFetchStats | None,
    topic_styles: dict[str, TopicStyle],
    displayed_ids: set[str],
) -> str:
    if fetch_stats is None:
        return ""

    insights = _insights_by_id(summary)
    rows = "\n".join(
        _topic_data_row(
            topic,
            papers,
            insights,
            topic_styles.get(topic.name, TOPIC_PALETTE[index % len(TOPIC_PALETTE)]),
        )
        for index, topic in enumerate(fetch_stats.topics)
    )
    all_ratings = _all_paper_rating_table(papers, insights, topic_styles, displayed_ids)
    return f"""
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border:1px solid #d8e2ef; border-radius:10px; margin:18px 0 0; background:#f8fbff;">
                <tr>
                  <td style="padding:14px 16px 12px;">
                    <div style="font-size:14px; color:#16213e; font-weight:800; margin-bottom:4px;">数据概览</div>
                    <div style="font-size:12px; line-height:1.55; color:#64748b; margin-bottom:10px;">
                      请求 {len(fetch_stats.topics)} 个 topic · 近 {fetch_stats.lookback_days} 天处理窗口 · 去重后 {fetch_stats.unique_paper_count} 篇 · max_results_per_topic={fetch_stats.max_results_per_topic}
                    </div>
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
                      <tr>
                        <th align="left" style="padding:7px 6px; border-bottom:1px solid #dbe3ef; color:#475569; font-size:11px; font-weight:800;">Topic</th>
                        <th align="center" style="padding:7px 6px; border-bottom:1px solid #dbe3ef; color:#475569; font-size:11px; font-weight:800;">处理</th>
                        <th align="center" style="padding:7px 6px; border-bottom:1px solid #dbe3ef; color:#475569; font-size:11px; font-weight:800;">上限</th>
                        <th align="left" style="padding:7px 6px; border-bottom:1px solid #dbe3ef; color:#475569; font-size:11px; font-weight:800;">评分分布</th>
                      </tr>
                      {rows}
                    </table>
                    {all_ratings}
                  </td>
                </tr>
              </table>"""


def _all_paper_rating_table(
    papers: list[Paper],
    insights: dict[str, PaperSummary],
    topic_styles: dict[str, TopicStyle],
    displayed_ids: set[str],
) -> str:
    if not papers:
        return ""
    rows = "\n".join(
        _paper_rating_row(paper, insights, topic_styles, displayed_ids)
        for paper in papers
    )
    return f"""
                    <div style="font-size:12px; color:#16213e; font-weight:800; margin:12px 0 6px;">全部文章评级</div>
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
                      {rows}
                    </table>"""


def _paper_rating_row(
    paper: Paper,
    insights: dict[str, PaperSummary],
    topic_styles: dict[str, TopicStyle],
    displayed_ids: set[str],
) -> str:
    normalized_id = normalize_arxiv_id(paper.arxiv_id)
    insight = insights.get(normalized_id, _empty_insight(paper))
    style = _paper_style(paper, topic_styles)
    topic_text = ", ".join(paper.topics) or "N/A"
    title = insight.chinese_title or paper.title
    status = "展示" if normalized_id in displayed_ids else "未展示"
    status_color = "#166534" if normalized_id in displayed_ids else "#64748b"
    status_background = "#dcfce7" if normalized_id in displayed_ids else "#f1f5f9"
    return f"""
                      <tr style="background:{style.background};">
                        <td width="16%" style="padding:5px 6px 5px 8px; border-left:4px solid {style.accent}; border-bottom:1px solid {style.border}; vertical-align:top;">
                          <a href="{html.escape(paper.link)}" style="font-size:10px; line-height:1.3; color:{style.text}; font-weight:800; text-decoration:none;">{html.escape(paper.arxiv_id)}</a>
                        </td>
                        <td width="55%" style="padding:5px 6px; border-bottom:1px solid {style.border}; vertical-align:top;">
                          <div style="font-size:10px; line-height:1.35; color:#1f2937; font-weight:700;">{html.escape(title)}</div>
                          <div style="font-size:9px; line-height:1.3; color:#64748b; margin-top:2px;">{html.escape(topic_text)}</div>
                        </td>
                        <td width="13%" align="center" style="padding:5px 6px; border-bottom:1px solid {style.border}; vertical-align:top;">
                          <span style="display:inline-block; min-width:32px; padding:2px 5px; border-radius:999px; background:#ffffff; border:1px solid {style.border}; color:#111827; font-size:10px; font-weight:800;">{insight.importance}/5</span>
                        </td>
                        <td width="16%" align="right" style="padding:5px 6px; border-bottom:1px solid {style.border}; vertical-align:top;">
                          <span style="display:inline-block; padding:2px 5px; border-radius:999px; background:{status_background}; color:{status_color}; font-size:9px; font-weight:800;">{status}</span>
                        </td>
                      </tr>"""


def _topic_data_row(
    topic: TopicFetchStats,
    papers: list[Paper],
    insights: dict[str, PaperSummary],
    style: TopicStyle,
) -> str:
    topic_name = topic.name
    topic_papers = [paper for paper in papers if topic_name in paper.topics]
    counts = _rating_counts(topic_papers, insights)
    average = _average_rating(counts)
    limit_badge = _topic_status_badge(topic)
    average_text = f"avg {average:.1f}" if average else "avg N/A"
    error_line = (
        f'<div style="font-size:11px; line-height:1.35; color:#b91c1c; margin-top:3px;">{html.escape(topic.error)}</div>'
        if topic.error
        else ""
    )
    return f"""
                      <tr style="background:{style.background};">
                        <td style="padding:8px 6px 8px 9px; border-left:4px solid {style.accent}; border-bottom:1px solid {style.border}; vertical-align:top; width:42%;">
                          <div style="font-size:12px; line-height:1.35; color:{style.text}; font-weight:800;">{html.escape(topic_name)}</div>
                          <div style="font-size:11px; line-height:1.35; color:#64748b; margin-top:2px;">{html.escape(topic.query)}</div>
                          {error_line}
                        </td>
                        <td align="center" style="padding:8px 6px; border-bottom:1px solid {style.border}; vertical-align:top; width:10%;">
                          <span style="font-size:13px; color:#111827; font-weight:800;">{topic.processed_count}</span>
                        </td>
                        <td align="center" style="padding:8px 6px; border-bottom:1px solid {style.border}; vertical-align:top; width:12%;">
                          {limit_badge}
                        </td>
                        <td style="padding:8px 6px; border-bottom:1px solid {style.border}; vertical-align:top; width:36%;">
                          <div style="font-size:11px; color:#64748b; margin-bottom:4px;">{average_text} · {_rating_count_text(counts)}</div>
                          {_rating_strip(counts)}
                        </td>
                      </tr>"""


def _topic_status_badge(topic: TopicFetchStats) -> str:
    if topic.error:
        return (
            '<span style="display:inline-block; padding:3px 7px; border-radius:999px; '
            'background:#fee2e2; color:#991b1b; font-size:11px; font-weight:800;">失败</span>'
        )
    if topic.hit_max_results:
        return (
            '<span style="display:inline-block; padding:3px 7px; border-radius:999px; '
            'background:#fef3c7; color:#92400e; font-size:11px; font-weight:800;">触顶</span>'
        )
    return (
        '<span style="display:inline-block; padding:3px 7px; border-radius:999px; '
        'background:#dcfce7; color:#166534; font-size:11px; font-weight:800;">未触顶</span>'
    )


def _rating_counts(papers: list[Paper], insights: dict[str, PaperSummary]) -> dict[int, int]:
    counts = {rating: 0 for rating in range(1, 6)}
    for paper in papers:
        insight = insights.get(normalize_arxiv_id(paper.arxiv_id), _empty_insight(paper))
        importance = min(5, max(1, insight.importance))
        counts[importance] += 1
    return counts


def _average_rating(counts: dict[int, int]) -> float:
    total = sum(counts.values())
    if not total:
        return 0.0
    return sum(rating * count for rating, count in counts.items()) / total


def _rating_count_text(counts: dict[int, int]) -> str:
    return " ".join(f"{rating}:{counts[rating]}" for rating in range(5, 0, -1))


def _rating_strip(counts: dict[int, int]) -> str:
    total = sum(counts.values())
    if not total:
        return '<div style="height:8px; border-radius:999px; background:#e5e7eb;"></div>'

    colors = {
        5: "#dc2626",
        4: "#f59e0b",
        3: "#0284c7",
        2: "#64748b",
        1: "#cbd5e1",
    }
    segments = []
    for rating in range(5, 0, -1):
        count = counts[rating]
        if not count:
            continue
        width = count / total * 100
        segments.append(
            f'<span style="display:inline-block; height:8px; width:{width:.1f}%; '
            f'background:{colors[rating]}; vertical-align:top;"></span>'
        )
    return (
        '<div style="height:8px; overflow:hidden; border-radius:999px; background:#e5e7eb; '
        f'white-space:nowrap;">{"".join(segments)}</div>'
    )


def _text_data_overview(
    summary: DailySummary,
    papers: list[Paper],
    fetch_stats: ArxivFetchStats | None,
) -> list[str]:
    if fetch_stats is None:
        return []

    insights = _insights_by_id(summary)
    lines = [
        "Data overview:",
        (
            f"- Requested topics: {len(fetch_stats.topics)}; lookback: {fetch_stats.lookback_days} day(s); "
            f"unique papers: {fetch_stats.unique_paper_count}; max_results_per_topic: "
            f"{fetch_stats.max_results_per_topic}"
        ),
    ]
    for topic in fetch_stats.topics:
        topic_papers = [paper for paper in papers if topic.name in paper.topics]
        counts = _rating_counts(topic_papers, insights)
        average = _average_rating(counts)
        average_text = f"{average:.1f}" if average else "N/A"
        hit_limit = _text_topic_status(topic)
        lines.append(
            f"- {topic.name} ({topic.query}): processed {topic.processed_count}, "
            f"status {hit_limit}, avg {average_text}, ratings {_rating_count_text(counts)}"
        )
    return lines


def _text_topic_status(topic: TopicFetchStats) -> str:
    if topic.error:
        return f"failed ({topic.error})"
    return "hit max yes" if topic.hit_max_results else "hit max no"


def _paragraph_block(text: str) -> str:
    paragraphs = [part.strip() for part in text.splitlines() if part.strip()]
    if not paragraphs:
        paragraphs = ["暂无总览。"]
    return "\n".join(
        f'<p style="margin:0 0 12px; font-size:15px; line-height:1.75; color:#374151;">{html.escape(paragraph)}</p>'
        for paragraph in paragraphs
    )


def _shortlist_block(summary: DailySummary) -> str:
    if not summary.shortlist:
        return ""
    items = "".join(
        f'<li style="margin:0 0 8px; font-size:14px; line-height:1.65; color:#374151;">{_shortlist_item_html(item)}</li>'
        for item in summary.shortlist
    )
    return f"""
              <div style="margin:18px 0 8px; padding:16px 18px; background:#eef6ff; border:1px solid #c8ddff; border-radius:10px;">
                <div style="font-size:14px; color:#0b63ce; font-weight:800; margin-bottom:8px;">优先阅读</div>
                <ol style="margin:0; padding-left:20px;">{items}</ol>
              </div>"""


def _shortlist_item_html(item: str) -> str:
    match = re.match(r"\s*([^：:\s]+)", item)
    if not match:
        return html.escape(item)
    arxiv_id = match.group(1)
    rest = item[match.end(1) :]
    anchor = _paper_anchor_id(arxiv_id)
    return (
        f'<a href="#{html.escape(anchor)}" style="color:#0b63ce; font-weight:800; text-decoration:none;">'
        f'{html.escape(arxiv_id)}</a>{html.escape(rest)}'
    )


def _paper_anchor_id(arxiv_id: str) -> str:
    normalized = normalize_arxiv_id(arxiv_id) or arxiv_id.strip()
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", normalized).strip("-")
    return f"paper-{safe or 'item'}"


def _rating_badge(importance: int) -> str:
    color = "#475569"
    background = "#eef2f7"
    if importance >= 5:
        color = "#991b1b"
        background = "#fee2e2"
    elif importance == 4:
        color = "#92400e"
        background = "#fef3c7"
    elif importance == 3:
        color = "#075985"
        background = "#e0f2fe"
    return (
        f'<span style="display:inline-block; padding:7px 10px; border-radius:999px; '
        f'background:{background}; color:{color}; font-size:13px; font-weight:800;">重要性 {importance}/5</span>'
    )


def _link_button(url: str, label: str) -> str:
    return (
        f'<a href="{html.escape(url)}" style="display:inline-block; margin:0 8px 6px 0; padding:8px 12px; '
        f'background:#0b63ce; color:#ffffff; border-radius:7px; font-size:13px; font-weight:700; '
        f'text-decoration:none;">{html.escape(label)}</a>'
    )


def _empty_state() -> str:
    return """
              <div style="padding:24px; background:#f9fafb; border:1px dashed #cbd5e1; border-radius:10px; color:#4b5563; font-size:15px;">
                No new papers matched the configured topics.
              </div>"""


def _insights_by_id(summary: DailySummary) -> dict[str, PaperSummary]:
    return {normalize_arxiv_id(item.arxiv_id): item for item in summary.paper_summaries}


def _format_authors(paper: Paper) -> str:
    return ", ".join(paper.authors) if paper.authors else "N/A"


def _format_comments(paper: Paper) -> str:
    return paper.comment.strip() or "N/A"


def _format_subjects(paper: Paper) -> str:
    subjects = paper.categories or ((paper.primary_category,) if paper.primary_category else ())
    return ", ".join(subjects) if subjects else "N/A"


def _empty_insight(paper: Paper) -> PaperSummary:
    abstract = paper.abstract[:260] + ("..." if len(paper.abstract) > 260 else "")
    return PaperSummary(
        arxiv_id=paper.arxiv_id,
        chinese_title="",
        summary=abstract,
        importance=3,
        importance_reason="AI 未提供该论文的结构化评级，暂按中等重要性展示。",
    )
