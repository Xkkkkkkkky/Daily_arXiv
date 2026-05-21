from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from .config import EmailConfig


def send_email(config: EmailConfig, subject: str, text_body: str, html_body: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = _format_sender(config)
    message["To"] = ", ".join(config.mail_to)
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    try:
        if config.smtp_use_ssl:
            with smtplib.SMTP_SSL(
                config.smtp_host,
                config.smtp_port,
                timeout=30,
                context=ssl.create_default_context(),
            ) as smtp:
                smtp.ehlo()
                _login_and_send(smtp, config, message)
        else:
            with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as smtp:
                smtp.ehlo()
                if config.smtp_use_tls:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                _login_and_send(smtp, config, message)
    except (
        OSError,
        smtplib.SMTPException,
        ssl.SSLError,
    ) as exc:
        raise RuntimeError(_smtp_error_message(config, exc)) from exc


def _login_and_send(smtp: smtplib.SMTP, config: EmailConfig, message: EmailMessage) -> None:
    if config.smtp_user:
        smtp.login(config.smtp_user, config.smtp_password)
    smtp.send_message(message)


def _format_sender(config: EmailConfig) -> str:
    if not config.mail_from_name:
        return config.mail_from
    _, address = parseaddr(config.mail_from)
    return formataddr((config.mail_from_name, address or config.mail_from))


def _smtp_error_message(config: EmailConfig, exc: BaseException) -> str:
    detail = str(exc).strip() or exc.__class__.__name__
    return (
        f"Failed to send email via SMTP {config.smtp_host}:{config.smtp_port} "
        f"using {_smtp_mode(config)}. {detail}. {_smtp_hint(config)}"
    )


def _smtp_mode(config: EmailConfig) -> str:
    if config.smtp_use_ssl:
        return "implicit SSL"
    if config.smtp_use_tls:
        return "STARTTLS"
    return "plain SMTP"


def _smtp_hint(config: EmailConfig) -> str:
    if config.smtp_port == 465 and not config.smtp_use_ssl:
        return "Port 465 normally requires SMTP_USE_SSL=true and SMTP_USE_TLS=false."
    if config.smtp_port == 587 and config.smtp_use_ssl:
        return "Port 587 normally requires SMTP_USE_TLS=true and SMTP_USE_SSL=false."
    if config.smtp_port == 587 and not config.smtp_use_tls:
        return "Port 587 normally requires SMTP_USE_TLS=true."
    if config.smtp_port == 25:
        return (
            "Port 25 is often blocked or restricted on CI runners; "
            "prefer port 465 with SSL or 587 with STARTTLS."
        )
    return (
        "Check SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, and the TLS/SSL mode. "
        "Use SSL for port 465, or STARTTLS for port 587."
    )
