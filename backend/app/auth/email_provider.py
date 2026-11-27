"""Decoupled transactional email provider interface, templates, and adapters."""

from __future__ import annotations

import logging
import smtplib
import ssl
import threading
from dataclasses import dataclass
from email.message import EmailMessage as StdEmailMessage
from email.utils import formataddr
from typing import Protocol
from urllib.parse import urlencode

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TransactionalEmail:
    to_email: str
    subject: str
    text_body: str
    html_body: str


class EmailProvider(Protocol):
    def send(self, message: TransactionalEmail) -> None: ...


class EmailDeliveryError(Exception):
    """Sanitized delivery failure raised by an EmailProvider."""


class FakeEmailProvider:
    """In-memory email provider for automated tests without external SMTP traffic."""

    def __init__(self, *, fail_with: str | None = None) -> None:
        self._lock = threading.Lock()
        self.sent_messages: list[TransactionalEmail] = []
        self.fail_with = fail_with

    def send(self, message: TransactionalEmail) -> None:
        if self.fail_with is not None:
            raise EmailDeliveryError(self.fail_with)
        with self._lock:
            self.sent_messages.append(message)


class SMTPEmailProvider:
    """SMTP/Mailpit email delivery adapter with TLS, timeout, and sanitized errors."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, message: TransactionalEmail) -> None:
        if self.settings.mail_use_tls and self.settings.mail_use_ssl:
            raise EmailDeliveryError("SMTP TLS and SSL modes are mutually exclusive")
        if self.settings.app_env == "production" and not (
            self.settings.mail_use_tls or self.settings.mail_use_ssl
        ):
            raise EmailDeliveryError("TLS is required for SMTP in production")

        mime = StdEmailMessage()
        mime["From"] = formataddr((self.settings.mail_from_name, self.settings.mail_from_address))
        mime["To"] = message.to_email
        mime["Subject"] = message.subject
        mime.set_content(message.text_body)
        mime.add_alternative(message.html_body, subtype="html")

        try:
            if self.settings.mail_use_ssl:
                with smtplib.SMTP_SSL(
                    self.settings.mail_host,
                    self.settings.mail_port,
                    timeout=self.settings.mail_timeout,
                    context=ssl.create_default_context(),
                ) as client:
                    self._authenticate_and_send(client, mime)
            else:
                with smtplib.SMTP(
                    self.settings.mail_host,
                    self.settings.mail_port,
                    timeout=self.settings.mail_timeout,
                ) as client:
                    if self.settings.mail_use_tls:
                        client.starttls(context=ssl.create_default_context())
                    self._authenticate_and_send(client, mime)
        except smtplib.SMTPException as exc:
            raise EmailDeliveryError(f"SMTP error ({type(exc).__name__})") from exc
        except OSError as exc:
            raise EmailDeliveryError(f"SMTP connection error ({type(exc).__name__})") from exc

    def _authenticate_and_send(self, client: smtplib.SMTP, mime: StdEmailMessage) -> None:
        password = self.settings.mail_password.get_secret_value()
        if self.settings.mail_username:
            client.login(self.settings.mail_username, password)
        client.send_message(mime)


def build_verification_url(*, base_url: str, raw_token: str) -> str:
    """Build verification URL strictly from trusted server APP_PUBLIC_BASE_URL."""
    base = base_url.rstrip("/")
    # A fragment is not sent to the web server or included in HTTP access logs.
    fragment = urlencode({"token": raw_token})
    return f"{base}/verify-email#{fragment}"


def render_verification_email(
    *,
    recipient_email: str,
    raw_token: str,
    base_url: str,
    ttl_hours: int,
) -> TransactionalEmail:
    verify_url = build_verification_url(base_url=base_url, raw_token=raw_token)
    subject = "Verify your VagaNexo AI account"
    text_body = (
        "Welcome to VagaNexo AI.\n\n"
        f"Confirm your email address by opening the link below (valid for {ttl_hours} hours):\n"
        f"{verify_url}\n\n"
        "If you did not create an account, you can ignore this message."
    )
    html_body = (
        "<p>Welcome to <strong>VagaNexo AI</strong>.</p>"
        f"<p>Confirm your email address (valid for {ttl_hours} hours):</p>"
        f'<p><a href="{verify_url}">Verify email address</a></p>'
        "<p>If you did not create an account, you can ignore this message.</p>"
    )
    return TransactionalEmail(
        to_email=recipient_email,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
    )


def build_email_provider(settings: Settings | None = None) -> EmailProvider:
    current = settings or get_settings()
    if current.mail_provider == "smtp":
        return SMTPEmailProvider(current)
    if current.mail_provider == "fake" and current.app_env != "production":
        return FakeEmailProvider()
    raise EmailDeliveryError("email provider is unavailable or misconfigured")
