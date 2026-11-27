from __future__ import annotations

import ssl
from unittest.mock import MagicMock

import pytest

from app.auth.email_provider import EmailDeliveryError, SMTPEmailProvider, TransactionalEmail
from app.core.config import Settings


def _message() -> TransactionalEmail:
    return TransactionalEmail("user@example.com", "Subject", "Text", "<p>HTML</p>")


def test_smtp_tls_uses_certificate_verifying_context(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(app_env="production", mail_use_tls=True)
    client = MagicMock()
    client.__enter__.return_value = client
    monkeypatch.setattr("app.auth.email_provider.smtplib.SMTP", lambda *args, **kwargs: client)

    SMTPEmailProvider(settings).send(_message())

    context = client.starttls.call_args.kwargs["context"]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_smtp_rejects_conflicting_tls_modes() -> None:
    settings = Settings(mail_use_tls=True, mail_use_ssl=True)
    with pytest.raises(EmailDeliveryError, match="mutually exclusive"):
        SMTPEmailProvider(settings).send(_message())
