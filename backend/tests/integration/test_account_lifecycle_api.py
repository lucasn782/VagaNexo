from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.outbox_crypto import OutboxCrypto
from app.core.config import Settings, get_settings
from app.models.account_action_token import AccountActionToken
from app.models.email_outbox import EmailOutbox
from app.models.user import User


def _enable_registration(monkeypatch) -> Settings:
    settings = get_settings().model_copy(update={"auth_public_registration_enabled": True})
    monkeypatch.setattr("app.auth.service.get_settings", lambda: settings)
    monkeypatch.setattr("app.auth.service.dispatch_outbox_email", lambda _outbox_id: None)
    return settings


def test_registration_verification_and_login_flow(
    unauthenticated_client,
    db_session: Session,
    monkeypatch,
) -> None:
    settings = _enable_registration(monkeypatch)
    response = unauthenticated_client.post(
        "/api/v1/auth/register",
        json={"email": "  New.User@Example.com ", "password": "GoodPassword123!"},
    )
    assert response.status_code == 202
    assert "eligible" in response.json()["detail"]

    user = db_session.scalar(select(User).where(User.email == "new.user@example.com"))
    assert user is not None
    assert user.status == "pending_verification"
    assert user.is_active is False
    assert user.email_verified_at is None
    assert (
        unauthenticated_client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": "GoodPassword123!"},
        ).status_code
        == 401
    )

    token_row = db_session.scalar(
        select(AccountActionToken).where(AccountActionToken.user_id == user.id)
    )
    outbox = db_session.scalar(select(EmailOutbox).where(EmailOutbox.user_id == user.id))
    assert token_row is not None
    assert outbox is not None
    assert token_row.token_hash not in (outbox.encrypted_payload or "")
    assert token_row.token_hash != "GoodPassword123!"
    assert outbox.encrypted_payload
    token = OutboxCrypto.from_settings(settings).decrypt_payload(
        outbox.encrypted_payload,
        key_version=outbox.payload_key_version,
        outbox_id=str(outbox.id),
        template_name=outbox.template_name,
    )["token"]

    assert unauthenticated_client.get(f"/api/v1/auth/verify-email?token={token}").status_code == 405
    db_session.refresh(token_row)
    assert token_row.consumed_at is None
    verified = unauthenticated_client.post("/api/v1/auth/verify-email", json={"token": token})
    assert verified.status_code == 200, verified.text
    db_session.refresh(user)
    assert user.status == "active"
    assert user.is_active is True
    assert user.email_verified_at is not None

    login = unauthenticated_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "GoodPassword123!"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["user"]["status"] == "active"
    assert (
        unauthenticated_client.post("/api/v1/auth/verify-email", json={"token": token}).status_code
        == 400
    )


def test_registration_disabled_and_duplicate_are_generic(
    unauthenticated_client,
    db_session: Session,
    monkeypatch,
) -> None:
    settings = get_settings().model_copy(update={"auth_public_registration_enabled": False})
    monkeypatch.setattr("app.auth.service.get_settings", lambda: settings)
    disabled = unauthenticated_client.post(
        "/api/v1/auth/register",
        json={"email": "disabled@example.com", "password": "GoodPassword123!"},
    )
    assert disabled.status_code == 403

    settings = _enable_registration(monkeypatch)
    from app.auth.service import AuthService

    AuthService(db_session).create_user(email="exists@example.com", password="GoodPassword123!")
    duplicate = unauthenticated_client.post(
        "/api/v1/auth/register",
        json={"email": "exists@example.com", "password": "GoodPassword123!"},
    )
    assert duplicate.status_code == 202
    assert duplicate.json() == {
        "detail": "if registration is eligible, a verification email will be sent shortly"
    }
    assert (
        db_session.scalar(select(User).where(User.email == "exists@example.com")).status == "active"
    )
    assert (
        db_session.scalar(
            select(EmailOutbox).where(EmailOutbox.recipient_email == "exists@example.com")
        )
        is None
    )
