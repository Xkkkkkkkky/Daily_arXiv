# Daily_arXiv

每日抓取 arXiv 指定领域的新文章，调用在线 AI 服务生成中文摘要，并通过邮件推送到指定邮箱。项目默认按 GitHub Actions 定时运行，也可以在本地手动执行。

## 功能

- 支持配置多个 arXiv 领域或搜索表达式，例如 `cat:cs.AI`、`cat:cs.CL`、`cat:cs.LG`
- 自动过滤最近 `N` 天新发布论文，并按 arXiv ID 去重
- 支持 OpenAI-compatible Chat Completions API，可接入 OpenAI、DeepSeek、OpenRouter、通义千问兼容接口等
- 通过 SMTP 发送 HTML 和纯文本双格式邮件
- GitHub Actions 每日定时运行，也支持手动触发
- 无第三方 Python 依赖，GitHub Actions 不需要安装额外包

## 快速开始

需要 Python 3.11 或更高版本。

1. 复制配置文件：

   ```bash
   cp config.example.toml config.toml
   ```

2. 编辑 `config.toml`，设置 arXiv 领域、收件人、发件人等非敏感配置。

3. 本地测试抓取和邮件正文渲染：

   ```bash
   python3 -m daily_arxiv.main --config config.toml --skip-ai --no-email
   ```

4. 本地完整运行需要设置环境变量：

   ```bash
   export AI_API_KEY="your-ai-api-key"
   export SMTP_HOST="smtp.example.com"
   export SMTP_PORT="587"
   export SMTP_USER="bot@example.com"
   export SMTP_PASSWORD="your-smtp-password"
   export MAIL_FROM="Daily arXiv <bot@example.com>"
   export MAIL_TO="you@example.com"

   python3 -m daily_arxiv.main --config config.toml
   ```

## GitHub Actions 配置

工作流文件位于 `.github/workflows/daily-arxiv.yml`，默认每天北京时间 07:00 运行一次，也可以在 GitHub Actions 页面手动触发。

在仓库的 `Settings -> Secrets and variables -> Actions -> Secrets` 中添加以下 Secrets：

| Secret | 说明 |
| --- | --- |
| `AI_API_KEY` | 在线 AI 服务 API Key |
| `AI_BASE_URL` | 可选，OpenAI-compatible API 地址，默认 `https://api.openai.com/v1` |
| `AI_MODEL` | 可选，模型名，默认读取配置文件里的 `ai.model` |
| `SMTP_HOST` | SMTP 服务器地址 |
| `SMTP_PORT` | SMTP 端口，常见为 `587` 或 `465` |
| `SMTP_USER` | SMTP 登录用户名 |
| `SMTP_PASSWORD` | SMTP 登录密码或应用专用密码 |
| `SMTP_USE_TLS` | 可选，是否启用 STARTTLS，默认 `true` |
| `SMTP_USE_SSL` | 可选，是否使用 SMTP SSL，默认 `false` |
| `MAIL_FROM` | 发件人地址，可覆盖配置文件 |
| `MAIL_TO` | 收件人地址，多个地址用逗号分隔，可覆盖配置文件 |

注意：如果你希望 GitHub Actions 读取 `config.toml`，需要把不含密钥的 `config.toml` 提交到仓库。API Key 和 SMTP 密码不要写入配置文件。

## 配置说明

`config.example.toml` 示例：

```toml
[arxiv]
max_results_per_topic = 25
lookback_days = 1
timezone = "Asia/Shanghai"
request_delay_seconds = 10.0
timeout_seconds = 30
retry_count = 5
retry_backoff_seconds = 60.0

[[topics]]
name = "AI"
query = "cat:cs.AI"

[[topics]]
name = "Machine Learning"
query = "cat:cs.LG"

[[topics]]
name = "Computational Linguistics"
query = "cat:cs.CL"

[ai]
base_url = "https://api.openai.com/v1"
model = "gpt-4o-mini"
temperature = 0.2
max_tokens = 3000
language = "Simplified Chinese"

[email]
subject_prefix = "Daily arXiv"
from = "Daily arXiv <bot@example.com>"
to = ["you@example.com"]
smtp_port = 587
smtp_use_tls = true
smtp_use_ssl = false
```

arXiv 查询语法可以参考 arXiv API 的 `search_query`。常用分类示例：

- `cat:cs.AI`：Artificial Intelligence
- `cat:cs.CL`：Computation and Language
- `cat:cs.CV`：Computer Vision and Pattern Recognition
- `cat:cs.LG`：Machine Learning
- `cat:stat.ML`：Machine Learning

## 命令

```bash
# 正常运行：抓取、总结、发邮件
python3 -m daily_arxiv.main --config config.toml

# 只生成正文并打印，不发送邮件
python3 -m daily_arxiv.main --config config.toml --no-email

# 不调用 AI，用论文标题和摘要片段生成调试正文
python3 -m daily_arxiv.main --config config.toml --skip-ai --no-email
```

## 邮件服务提示

- Gmail、Outlook、QQ 邮箱等通常需要开启 SMTP，并使用应用专用密码。
- `SMTP_PORT=587` 通常搭配 `SMTP_USE_TLS=true`。
- `SMTP_PORT=465` 通常搭配 `SMTP_USE_SSL=true`、`SMTP_USE_TLS=false`。
- 如果发件人和登录用户名不同，请确认邮件服务商允许代发。
