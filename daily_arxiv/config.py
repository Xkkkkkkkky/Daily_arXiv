from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when runtime configuration is missing or invalid."""


@dataclass(frozen=True)
class TopicConfig:
    name: str
    query: str


@dataclass(frozen=True)
class ArxivConfig:
    topics: tuple[TopicConfig, ...]
    max_results_per_topic: int = 25
    lookback_days: int = 1
    timezone: str = "Asia/Shanghai"
    sort_by: str = "submittedDate"
    sort_order: str = "descending"
    request_delay_seconds: float = 3.0
    timeout_seconds: int = 30
    retry_count: int = 2
    retry_backoff_seconds: float = 10.0


@dataclass(frozen=True)
class AIConfig:
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 0.2
    max_tokens: int = 3000
    language: str = "Simplified Chinese"
    timeout_seconds: int = 120


@dataclass(frozen=True)
class EmailConfig:
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    mail_from: str = ""
    mail_to: tuple[str, ...] = ()
    subject_prefix: str = "Daily arXiv"


@dataclass(frozen=True)
class AppConfig:
    arxiv: ArxivConfig
    ai: AIConfig
    email: EmailConfig


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    with path.open("rb") as config_file:
        data = tomllib.load(config_file)

    return AppConfig(
        arxiv=_load_arxiv_config(data),
        ai=_load_ai_config(data.get("ai", {})),
        email=_load_email_config(data.get("email", {})),
    )


def validate_email_config(config: EmailConfig) -> None:
    missing = []
    if not config.smtp_host:
        missing.append("SMTP_HOST or email.smtp_host")
    if not config.mail_from:
        missing.append("MAIL_FROM or email.from")
    if not config.mail_to:
        missing.append("MAIL_TO or email.to")
    if config.smtp_user and not config.smtp_password:
        missing.append("SMTP_PASSWORD or email.smtp_password")
    if missing:
        raise ConfigError("Missing email configuration: " + ", ".join(missing))


def _load_arxiv_config(data: dict[str, Any]) -> ArxivConfig:
    arxiv_data = data.get("arxiv", {})
    topics = _load_topics(data, arxiv_data)
    if not topics:
        raise ConfigError("Add at least one [[topics]] entry or arxiv.query")

    return ArxivConfig(
        topics=topics,
        max_results_per_topic=_int(arxiv_data.get("max_results_per_topic", 25), "arxiv.max_results_per_topic"),
        lookback_days=_int(arxiv_data.get("lookback_days", 1), "arxiv.lookback_days"),
        timezone=str(arxiv_data.get("timezone", "Asia/Shanghai")),
        sort_by=str(arxiv_data.get("sort_by", "submittedDate")),
        sort_order=str(arxiv_data.get("sort_order", "descending")),
        request_delay_seconds=_float(arxiv_data.get("request_delay_seconds", 3.0), "arxiv.request_delay_seconds"),
        timeout_seconds=_int(arxiv_data.get("timeout_seconds", 30), "arxiv.timeout_seconds"),
        retry_count=_int(arxiv_data.get("retry_count", 2), "arxiv.retry_count"),
        retry_backoff_seconds=_float(arxiv_data.get("retry_backoff_seconds", 10.0), "arxiv.retry_backoff_seconds"),
    )


def _load_topics(data: dict[str, Any], arxiv_data: dict[str, Any]) -> tuple[TopicConfig, ...]:
    topics_data = data.get("topics", [])
    topics: list[TopicConfig] = []
    for index, item in enumerate(topics_data, start=1):
        if not isinstance(item, dict):
            raise ConfigError(f"topics[{index}] must be a table")
        name = str(item.get("name", "")).strip()
        query = str(item.get("query", "")).strip()
        if not name or not query:
            raise ConfigError(f"topics[{index}] requires both name and query")
        topics.append(TopicConfig(name=name, query=query))

    fallback_query = str(arxiv_data.get("query", "")).strip()
    if fallback_query and not topics:
        topics.append(TopicConfig(name=str(arxiv_data.get("name", "arXiv")), query=fallback_query))
    return tuple(topics)


def _load_ai_config(ai_data: dict[str, Any]) -> AIConfig:
    return AIConfig(
        api_key=_env("AI_API_KEY") or str(ai_data.get("api_key", "")).strip(),
        base_url=_env("AI_BASE_URL") or str(ai_data.get("base_url", "https://api.openai.com/v1")).strip(),
        model=_env("AI_MODEL") or str(ai_data.get("model", "gpt-4o-mini")).strip(),
        temperature=_float(_env("AI_TEMPERATURE") or ai_data.get("temperature", 0.2), "ai.temperature"),
        max_tokens=_int(_env("AI_MAX_TOKENS") or ai_data.get("max_tokens", 3000), "ai.max_tokens"),
        language=_env("AI_LANGUAGE") or str(ai_data.get("language", "Simplified Chinese")).strip(),
        timeout_seconds=_int(_env("AI_TIMEOUT_SECONDS") or ai_data.get("timeout_seconds", 120), "ai.timeout_seconds"),
    )


def _load_email_config(email_data: dict[str, Any]) -> EmailConfig:
    mail_to = _email_list(_env("MAIL_TO") or "", email_data.get("to", []))
    return EmailConfig(
        smtp_host=_env("SMTP_HOST") or str(email_data.get("smtp_host", "")).strip(),
        smtp_port=_int(_env("SMTP_PORT") or email_data.get("smtp_port", 587), "email.smtp_port"),
        smtp_user=_env("SMTP_USER") or str(email_data.get("smtp_user", "")).strip(),
        smtp_password=_env("SMTP_PASSWORD") or str(email_data.get("smtp_password", "")).strip(),
        smtp_use_tls=_bool(_env("SMTP_USE_TLS") or email_data.get("smtp_use_tls", True), "email.smtp_use_tls"),
        smtp_use_ssl=_bool(_env("SMTP_USE_SSL") or email_data.get("smtp_use_ssl", False), "email.smtp_use_ssl"),
        mail_from=_env("MAIL_FROM") or str(email_data.get("from", "")).strip(),
        mail_to=mail_to,
        subject_prefix=str(email_data.get("subject_prefix", "Daily arXiv")).strip(),
    )


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _email_list(env_value: str, config_value: Any) -> tuple[str, ...]:
    if env_value.strip():
        raw_items = env_value.split(",")
    elif isinstance(config_value, str):
        raw_items = config_value.split(",")
    elif isinstance(config_value, list):
        raw_items = [str(item) for item in config_value]
    else:
        raw_items = []
    return tuple(item.strip() for item in raw_items if item.strip())


def _int(value: Any, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} must be an integer") from exc


def _float(value: Any, name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} must be a number") from exc


def _bool(value: Any, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    raise ConfigError(f"{name} must be a boolean")
