# Daily_arXiv

Daily_arXiv fetches recent arXiv papers for configured topics, asks an OpenAI-compatible AI service for Chinese summaries and importance ratings, then sends a clean HTML/plain-text email digest through SMTP.

Daily_arXiv 会按配置抓取 arXiv 论文，调用兼容 OpenAI Chat Completions 的 AI 服务生成中文摘要与重要性评级，并通过 SMTP 发送 HTML/纯文本邮件。

## Features / 功能

- Multiple arXiv topics with top-level `[[topics]]` blocks.
- Uses the `arxiv` Python package for API fetching and parsing.
- Deduplicates papers by arXiv ID and keeps topic labels.
- Shows title, Chinese title, authors, comments, subjects, summary, links, and AI importance rating.
- Optional display filter: when there are many papers, only high-rated papers are shown in the final email.
- Runs locally or daily via GitHub Actions.

- 支持任意数量的顶层 `[[topics]]`。
- 使用 `arxiv` Python 包抓取和解析 API 结果。
- 按 arXiv ID 去重，并保留命中的 topic 标签。
- 邮件展示原文标题、中文标题、作者、Comments、Subjects、摘要、链接和 AI 重要性评级。
- 支持最终邮件按评级筛选，文章很多时只展示高优先级论文。
- 支持本地运行和 GitHub Actions 定时运行。

## Setup / 安装

Requires Python 3.11+.

需要 Python 3.11 或更高版本。

```bash
cp config.example.toml config.toml
python3 -m pip install -r requirements.txt
```

Edit `config.toml` for topics and non-secret defaults. Keep API keys and SMTP passwords in environment variables or GitHub Secrets.

编辑 `config.toml` 配置 topics 和非敏感默认值。API Key 与 SMTP 密码应放在环境变量或 GitHub Secrets 中。

## Run / 运行

```bash
# Build digest without AI or email / 不调用 AI、不发邮件
python3 -m daily_arxiv.main --config config.toml --skip-ai --no-email

# Build digest with AI, print instead of sending / 调用 AI，但只打印不发邮件
python3 -m daily_arxiv.main --config config.toml --no-email

# Full run / 完整运行
python3 -m daily_arxiv.main --config config.toml
```

Required environment variables for full local runs:

本地完整运行需要：

```bash
export AI_API_KEY="your-ai-api-key"
export SMTP_HOST="smtp.example.com"
export SMTP_PORT="587"
export SMTP_USER="bot@example.com"
export SMTP_PASSWORD="your-smtp-password"
export MAIL_FROM="Daily arXiv <bot@example.com>"
export MAIL_TO="you@example.com"
```

## Config / 配置

Minimal shape:

基础结构：

```toml
[arxiv]
max_results_per_topic = 5
lookback_days = 1
timezone = "Asia/Shanghai"
sort_by = "submittedDate"
sort_order = "descending"
request_delay_seconds = 10.0
timeout_seconds = 90
retry_count = 2
retry_backoff_seconds = 60.0
allow_fetch_failure = true

[[topics]]
name = "Astrophysics - Cosmology"
query = "cat:astro-ph.CO"

[ai]
base_url = "https://api.openai.com/v1"
model = "gpt-4o-mini"
temperature = 0.2
max_tokens = 4000
language = "Simplified Chinese"

[digest]
priority_filter_enabled = true
priority_filter_min_total = 10
priority_filter_min_importance = 4
priority_filter_max_papers = 12

[email]
subject_prefix = "Daily arXiv"
from = "Daily arXiv <bot@example.com>"
to = ["you@example.com"]
smtp_port = 587
smtp_use_tls = true
smtp_use_ssl = false
```

`[[topics]]` is top-level and repeatable. Example queries: `cat:cs.AI`, `cat:cs.CL`, `cat:cs.CV`, `cat:cs.LG`, `cat:stat.ML`, `cat:astro-ph.CO`, `cat:astro-ph.GA`, `cat:astro-ph.HE`.

`[[topics]]` 是可重复的顶层表。常见查询包括：`cat:cs.AI`、`cat:cs.CL`、`cat:cs.CV`、`cat:cs.LG`、`cat:stat.ML`、`cat:astro-ph.CO`、`cat:astro-ph.GA`、`cat:astro-ph.HE`。

The `[digest]` filter affects only final email display, not arXiv fetching or AI summarization. With the example above, if more than 10 papers are fetched, the email shows papers rated at least 4/5, capped at 12 papers. If none meet the rating threshold, it falls back to the highest-rated papers.

`[digest]` 只影响最终邮件展示，不影响抓取和 AI 总结。以上示例表示：当抓取论文数超过 10 篇时，邮件优先展示评级不低于 4/5 的论文，最多 12 篇；如果没有论文达到阈值，则退回展示评分最高的论文。

## GitHub Actions / GitHub Actions

The workflow is `.github/workflows/daily-arxiv.yml`. It runs daily at 23:00 UTC, i.e. 07:00 Asia/Shanghai, and also supports manual dispatch.

工作流文件是 `.github/workflows/daily-arxiv.yml`。默认每天 UTC 23:00，即北京时间 07:00 运行，也支持手动触发。

Add these repository secrets:

需要添加以下仓库 Secrets：

| Secret | Meaning / 含义 |
| --- | --- |
| `AI_API_KEY` | AI service API key |
| `AI_BASE_URL` | Optional OpenAI-compatible base URL |
| `AI_MODEL` | Optional model override |
| `SMTP_HOST` | SMTP host |
| `SMTP_PORT` | SMTP port, usually `587` or `465` |
| `SMTP_USER` | SMTP username |
| `SMTP_PASSWORD` | SMTP password or app password |
| `SMTP_USE_TLS` | Optional STARTTLS flag |
| `SMTP_USE_SSL` | Optional SMTP SSL flag |
| `MAIL_FROM` | Sender address |
| `MAIL_TO` | Recipient addresses, comma-separated |

Do not commit secrets. `config.toml` should contain only non-sensitive defaults.

不要提交密钥。`config.toml` 只应包含非敏感默认配置。

## Notes / 说明

- arXiv API may return `HTTP 429` or time out, especially from shared GitHub Actions IPs.
- `allow_fetch_failure = true` sends a fetch-failure digest instead of failing the whole workflow.
- arXiv API `published` dates may differ from the website list date; use `lookback_days = 2` or `3` if daily windows miss papers.

- arXiv API 可能返回 `HTTP 429` 或超时，GitHub Actions 共享出口更常见。
- `allow_fetch_failure = true` 会发送抓取失败通知，而不是让整个 workflow 直接失败。
- arXiv API 的 `published` 日期可能不同于网页列表日期；如果每日窗口漏文章，可以把 `lookback_days` 设为 `2` 或 `3`。
