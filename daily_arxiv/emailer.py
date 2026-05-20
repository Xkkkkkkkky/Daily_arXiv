from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from .config import EmailConfig


def send_email(config: EmailConfig, subject: str, text_body: str, html_body: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.mail_from
    message["To"] = ", ".join(config.mail_to)
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    if config.smtp_use_ssl:
        with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=30, context=ssl.create_default_context()) as smtp:
            _login_and_send(smtp, config, message)
    else:
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as smtp:
            if config.smtp_use_tls:
                smtp.starttls(context=ssl.create_default_context())
            _login_and_send(smtp, config, message)


def _login_and_send(smtp: smtplib.SMTP, config: EmailConfig, message: EmailMessage) -> None:
    if config.smtp_user:
        smtp.login(config.smtp_user, config.smtp_password)
    smtp.send_message(message)
