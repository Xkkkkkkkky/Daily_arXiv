# Daily_arXiv

Daily arXiv email digest: fetch configured arXiv topics, summarize papers with an OpenAI-compatible AI service, rate importance, and send an HTML/plain-text email through SMTP.

每日 arXiv 邮件摘要工具：按配置抓取 arXiv 领域论文，调用兼容 OpenAI API 的 AI 服务生成摘要与评级，并通过 SMTP 发送 HTML/纯文本邮件。

## Features / 功能

- Repeatable `[[topics]]` arXiv queries.
- Email cards with title, Chinese title, authors, Comments, Subjects, summary, rating, and links.
- Local run or GitHub Actions daily run.

- 支持多个顶层 `[[topics]]` 查询。
- 邮件卡片展示标题、中文标题、作者、Comments、Subjects、摘要、评级和链接。
- 支持本地运行和 GitHub Actions 定时运行。

## Quick Start / 快速开始

Python 3.11+ is required.

需要 Python 3.11 或更高版本。

```bash
cp config.example.toml config.toml
python3 -m pip install --requirement requirements.txt
```

Edit `config.toml` for topics and non-secret defaults.

编辑 `config.toml` 配置 topics 和非敏感默认值。

```bash
# Render without AI or email / 不调用 AI、不发邮件
python3 -m daily_arxiv.main --config config.toml --skip-ai --no-email

# Call AI but print only / 调用 AI，但只打印
python3 -m daily_arxiv.main --config config.toml --no-email

# Full run / 完整运行
python3 -m daily_arxiv.main --config config.toml
```

## Configuration / 配置

Core `config.toml` shape:

核心配置结构：

```toml
[arxiv]
max_results_per_topic = 5
lookback_days = 2
timezone = "Asia/Shanghai"
sort_by = "submittedDate"
sort_order = "descending"
request_delay_seconds = 10.0
timeout_seconds = 90
retry_count = 2
retry_backoff_seconds = 60.0
allow_fetch_failure = true

[[topics]]
name = "Performance - Computer Science"
query = "cat:cs.PF"

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
from = "bot@example.com"
from_name = "Daily arXiv"
to = ["you@example.com"]
smtp_port = 587
smtp_use_tls = true
smtp_use_ssl = false
```

`[[topics]]` is arXiv categories. Common query examples: `cat:cs.AI`, `cat:cs.CL`, `cat:cs.CV`, `cat:cs.LG`, `cat:stat.ML`, `cat:astro-ph.CO`, `cat:astro-ph.GA`, `cat:astro-ph.HE`.

`[[topics]]` 是可重复的arXiv类别表。常见查询示例：`cat:cs.AI`、`cat:cs.CL`、`cat:cs.CV`、`cat:cs.LG`、`cat:stat.ML`、`cat:astro-ph.CO`、`cat:astro-ph.GA`、`cat:astro-ph.HE`。

`[digest]` only filters final email display. Fetching and AI summarization still process all papers. If fetched papers exceed `priority_filter_min_total`, the email shows papers with rating at least `priority_filter_min_importance`, capped by `priority_filter_max_papers`.

`[digest]` 只筛选最终邮件展示，不影响抓取和 AI 总结。当抓取数量超过 `priority_filter_min_total` 时，只展示评级不低于 `priority_filter_min_importance` 的论文，最多 `priority_filter_max_papers` 篇。

## Secrets / 密钥

Use environment variables locally or GitHub Actions Secrets in CI. 

本地用环境变量，CI 用 GitHub Actions Secrets。

| Name | Purpose / 用途 |
| --- | --- |
| `AI_API_KEY` | AI API key |
| `AI_BASE_URL` | OpenAI-compatible base URL |
| `AI_MODEL` | Model override |
| `SMTP_HOST` | SMTP host |
| `SMTP_PORT` | SMTP port |
| `SMTP_USER` | SMTP username |
| `SMTP_PASSWORD` | SMTP password or app password |
| `SMTP_USE_TLS` | STARTTLS flag |
| `SMTP_USE_SSL` | SMTP SSL flag |
| `MAIL_FROM` | Sender email address |
| `MAIL_FROM_NAME` | Sender display name |
| `MAIL_TO` | Recipients, comma-separated |

Example local run:

本地示例：

```bash
export AI_API_KEY="..."
export SMTP_HOST="smtp.example.com"
export SMTP_PORT="587"
export SMTP_USER="bot@example.com"
export SMTP_PASSWORD="..."
export MAIL_FROM="bot@example.com"
export MAIL_FROM_NAME="Daily arXiv"
export MAIL_TO="you@example.com"
python3 -m daily_arxiv.main --config config.toml
```

## Notes / 注意

- arXiv may return `HTTP 429` or time out, especially from shared GitHub Actions IPs.
- With `allow_fetch_failure = true`, fetch failures produce a failure digest instead of failing the whole workflow.
- arXiv API `published` dates can differ from website list dates. Use `lookback_days = 2` or `3` if daily runs miss papers.

- arXiv 可能返回 `HTTP 429` 或超时，GitHub Actions 共享出口更常见。
- `allow_fetch_failure = true` 会发送抓取失败摘要，而不是直接让 workflow 失败。
- arXiv API 的 `published` 日期可能不同于网页列表日期。如果每日运行漏文章，可把 `lookback_days` 设为 `2` 或 `3`。
