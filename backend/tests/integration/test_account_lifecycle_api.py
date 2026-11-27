from __future__ import annotations

import base64
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.email_provider import FakeEmailProvider
from app.auth.exceptions import InvalidActionTokenError
from app.auth.outbox import EmailOutboxService
from app.auth.outbox_crypto import OutboxCrypto
from app.auth.security import hash_token
from app.auth.tokens import ActionTokenService
from app.core.config import Settings, get_settings
from app.models.account_action_token import AccountActionToken
from app.models.email_outbox import EmailOutbox
from app.models.enums import ActionTokenPurpose, EmailOutboxStatus
from app.models.user import User


def _enable_registration(monkeypatch) -> Settings:
    test_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
    settings = get_settings().model_copy(
        update={
            "auth_public_registration_enabled": True,
            "email_outbox_encryption_keys": SecretStr(f"1:{test_key}"),
        }
    )
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


def test_only_one_concurrent_transaction_can_consume_a_token(
    db_session: Session,
    test_engine: Engine,
) -> None:
    from app.auth.security import hash_password
    from app.models.account_action_token import AccountActionToken
    from app.models.enums import AccountStatus

    user = User(
        email="token-race@example.com",
        password_hash=hash_password("GoodPassword123!"),
        status=AccountStatus.PENDING_VERIFICATION.value,
        is_active=False,
    )
    db_session.add(user)
    db_session.flush()
    raw_token = "race-token-value"
    db_session.add(
        AccountActionToken(
            user_id=user.id,
            purpose=ActionTokenPurpose.EMAIL_VERIFICATION.value,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    db_session.commit()

    factory = sessionmaker(bind=test_engine, class_=Session, expire_on_commit=False)
    barrier = threading.Barrier(2)

    def consume() -> bool:
        with factory() as session:
            barrier.wait()
            try:
                ActionTokenService.consume_token(
                    session,
                    raw_token=raw_token,
                    purpose=ActionTokenPurpose.EMAIL_VERIFICATION,
                )
                session.commit()
                return True
            except InvalidActionTokenError:
                session.rollback()
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: consume(), range(2)))
    assert sorted(results) == [False, True]


def test_expired_outbox_lease_cannot_be_finalized_by_old_worker(
    unauthenticated_client,
    db_session: Session,
    test_engine: Engine,
    monkeypatch,
) -> None:
    settings = _enable_registration(monkeypatch)
    response = unauthenticated_client.post(
        "/api/v1/auth/register",
        json={"email": "outbox-race@example.com", "password": "GoodPassword123!"},
    )
    assert response.status_code == 202
    from app.models.email_outbox import EmailOutbox

    entry = db_session.scalar(
        select(EmailOutbox).where(EmailOutbox.recipient_email == "outbox-race@example.com")
    )
    assert entry is not None
    first_claim = EmailOutboxService.claim_message(
        db_session, outbox_id=entry.id, settings=settings
    )
    assert first_claim is not None and first_claim.claim_token is not None
    stale_claim_token = first_claim.claim_token

    db_session.execute(
        update(EmailOutbox)
        .where(EmailOutbox.id == entry.id)
        .values(lock_expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    db_session.commit()
    factory = sessionmaker(bind=test_engine, class_=Session, expire_on_commit=False)
    with factory() as second_session:
        second_claim = EmailOutboxService.claim_message(
            second_session, outbox_id=entry.id, settings=settings
        )
        assert second_claim is not None
        assert second_claim.claim_token is not None
        assert second_claim.claim_token != stale_claim_token
        current_claim_token = second_claim.claim_token

    provider = FakeEmailProvider()
    assert not EmailOutboxService._deliver_claimed_entry(
        db_session,
        entry=first_claim,
        provider=provider,
        settings=settings,
    )
    assert len(provider.sent_messages) == 1  # delivery may duplicate after an SMTP timeout
    db_session.expire_all()
    current_entry = db_session.get(EmailOutbox, entry.id)
    assert current_entry is not None
    assert current_entry.status == EmailOutboxStatus.SENDING.value
    assert current_entry.claim_token == current_claim_token
    assert current_entry.encrypted_payload is not None


def test_revoked_verification_outbox_message_is_discarded(
    unauthenticated_client,
    db_session: Session,
    monkeypatch,
) -> None:
    settings = _enable_registration(monkeypatch)
    response = unauthenticated_client.post(
        "/api/v1/auth/register",
        json={"email": "revoked-outbox@example.com", "password": "GoodPassword123!"},
    )
    assert response.status_code == 202
    user = db_session.scalar(select(User).where(User.email == "revoked-outbox@example.com"))
    assert user is not None
    token = db_session.scalar(
        select(AccountActionToken).where(AccountActionToken.user_id == user.id)
    )
    assert token is not None
    token.revoked_at = datetime.now(UTC)
    db_session.commit()

    entry = db_session.scalar(
        select(EmailOutbox).where(EmailOutbox.recipient_email == "revoked-outbox@example.com")
    )
    assert entry is not None
    claimed = EmailOutboxService.claim_message(db_session, outbox_id=entry.id, settings=settings)
    assert claimed is not None
    provider = FakeEmailProvider()

    assert not EmailOutboxService._deliver_claimed_entry(
        db_session,
        entry=claimed,
        provider=provider,
        settings=settings,
    )
    assert provider.sent_messages == []
    db_session.expire_all()
    discarded = db_session.get(EmailOutbox, entry.id)
    assert discarded is not None
    assert discarded.status == EmailOutboxStatus.FAILED.value
    assert discarded.encrypted_payload is None


def test_two_workers_cannot_claim_the_same_outbox_message_concurrently(
    unauthenticated_client,
    db_session: Session,
    test_engine: Engine,
    monkeypatch,
) -> None:
    settings = _enable_registration(monkeypatch)
    response = unauthenticated_client.post(
        "/api/v1/auth/register",
        json={"email": "claim-race@example.com", "password": "GoodPassword123!"},
    )
    assert response.status_code == 202
    entry = db_session.scalar(
        select(EmailOutbox).where(EmailOutbox.recipient_email == "claim-race@example.com")
    )
    assert entry is not None

    factory = sessionmaker(bind=test_engine, class_=Session, expire_on_commit=False)
    barrier = threading.Barrier(2)

    def claim() -> str | None:
        with factory() as session:
            barrier.wait()
            claimed = EmailOutboxService.claim_message(
                session, outbox_id=entry.id, settings=settings
            )
            return str(claimed.claim_token) if claimed is not None else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        tokens = list(pool.map(lambda _: claim(), range(2)))
    assert sum(token is not None for token in tokens) == 1
    db_session.refresh(entry)
    assert str(entry.claim_token) in tokens


def test_sweeper_delivers_current_message_and_clears_payload(
    unauthenticated_client,
    db_session: Session,
    monkeypatch,
) -> None:
    settings = _enable_registration(monkeypatch)
    response = unauthenticated_client.post(
        "/api/v1/auth/register",
        json={"email": "sweeper@example.com", "password": "GoodPassword123!"},
    )
    assert response.status_code == 202
    entry = db_session.scalar(
        select(EmailOutbox).where(EmailOutbox.recipient_email == "sweeper@example.com")
    )
    assert entry is not None
    provider = FakeEmailProvider()

    delivered = EmailOutboxService.sweep_pending(
        db_session, provider=provider, settings=settings, batch_size=2
    )

    assert delivered == 1
    assert len(provider.sent_messages) == 1
    db_session.refresh(entry)
    assert entry.status == EmailOutboxStatus.SENT.value
    assert entry.encrypted_payload is None


@pytest.mark.parametrize(
    ("max_attempts", "expected_status", "payload_retained"),
    [
        (3, EmailOutboxStatus.PENDING.value, True),
        (1, EmailOutboxStatus.FAILED.value, False),
    ],
)
def test_outbox_failure_retries_then_clears_terminal_payload(
    unauthenticated_client,
    db_session: Session,
    monkeypatch,
    max_attempts: int,
    expected_status: str,
    payload_retained: bool,
) -> None:
    settings = _enable_registration(monkeypatch).model_copy(
        update={"email_outbox_max_attempts": max_attempts}
    )
    response = unauthenticated_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"outbox-failure-{max_attempts}@example.com",
            "password": "GoodPassword123!",
        },
    )
    assert response.status_code == 202
    entry = db_session.scalar(
        select(EmailOutbox).where(
            EmailOutbox.recipient_email == f"outbox-failure-{max_attempts}@example.com"
        )
    )
    assert entry is not None

    delivered = EmailOutboxService.process_message(
        db_session,
        outbox_id=entry.id,
        provider=FakeEmailProvider(fail_with="connection failed"),
        settings=settings,
    )

    assert not delivered
    db_session.refresh(entry)
    assert entry.status == expected_status
    assert (entry.encrypted_payload is not None) is payload_retained
    assert entry.claim_token is None


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
