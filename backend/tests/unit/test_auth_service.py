from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.auth.exceptions import (
    AuthenticationRequiredError,
    InvalidCredentialsError,
    InvalidUserDataError,
    RateLimiterUnavailableError,
    RateLimitExceededError,
    UserAlreadyExistsError,
)
from app.auth.rate_limit import InMemoryRateLimiter, RedisLoginRateLimiter
from app.auth.security import hash_token, normalize_email, verify_password
from app.auth.service import AuthService
from app.cli import run_cli
from app.core.config import Settings
from app.models.candidate_profile import CandidateProfile
from app.profile.exceptions import ConflictError, InvalidProfileDataError
from app.profile.service import ProfileService
from app.resume_import.service import ResumeImportService
from app.resume_import.storage import ResumeStorage


def test_normalize_email_and_validation() -> None:
    assert normalize_email("  Alice.Smith@Example.COM ") == "alice.smith@example.com"
    for bad in ("", "not-an-email", "a@b", "a b@example.com", "a@.example.com"):
        with pytest.raises(InvalidUserDataError):
            normalize_email(bad)


def test_create_user_uses_argon2id_and_rejects_duplicates(db_session: Session) -> None:
    service = AuthService(
        db_session,
        rate_limiter=InMemoryRateLimiter(max_attempts=10, window_seconds=60),
    )
    user = service.create_user(email="  Ana@Example.com ", password="StrongPassword123!")
    assert user.email == "ana@example.com"
    assert user.password_hash.startswith("$argon2id$")
    assert verify_password(user.password_hash, "StrongPassword123!")
    assert not verify_password(user.password_hash, "WrongPassword")

    with pytest.raises(UserAlreadyExistsError):
        service.create_user(email="ana@example.com", password="AnotherPassword123!")


def test_authenticate_session_lifecycle_expiration_and_revocation(db_session: Session) -> None:
    limiter = InMemoryRateLimiter(max_attempts=10, window_seconds=60)
    service = AuthService(db_session, rate_limiter=limiter)
    user = service.create_user(email="bob@example.com", password="SecretPassword123!")

    authed_user, raw_token, raw_csrf = service.authenticate(
        email="BOB@example.com",
        password="SecretPassword123!",
        client_ip="127.0.0.1",
    )
    assert authed_user.id == user.id
    assert len(raw_token) >= 32
    assert len(raw_csrf) >= 32

    auth_session, loaded_user = service.get_active_session(raw_token)
    assert loaded_user.id == user.id
    assert auth_session.token_hash == hash_token(raw_token)
    assert auth_session.token_hash != raw_token
    assert auth_session.csrf_token_hash == hash_token(raw_csrf)

    # Revoke session
    service.revoke_session(auth_session)
    with pytest.raises(AuthenticationRequiredError):
        service.get_active_session(raw_token)

    # Expired session
    _, raw_token2, _ = service.authenticate(
        email="bob@example.com",
        password="SecretPassword123!",
        client_ip="127.0.0.1",
    )
    sess2, _ = service.get_active_session(raw_token2)
    sess2.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    with pytest.raises(AuthenticationRequiredError):
        service.get_active_session(raw_token2)


def test_inactive_user_cannot_authenticate_or_use_session(db_session: Session) -> None:
    limiter = InMemoryRateLimiter(max_attempts=10, window_seconds=60)
    service = AuthService(db_session, rate_limiter=limiter)
    user = service.create_user(email="disabled@example.com", password="SecretPassword123!")
    _, raw_token, _ = service.authenticate(
        email="disabled@example.com",
        password="SecretPassword123!",
        client_ip="127.0.0.1",
    )

    user.is_active = False
    db_session.commit()

    with pytest.raises(InvalidCredentialsError):
        service.authenticate(
            email="disabled@example.com",
            password="SecretPassword123!",
            client_ip="127.0.0.1",
        )
    with pytest.raises(AuthenticationRequiredError):
        service.get_active_session(raw_token)


def test_redis_rate_limiter_enforces_limits_and_fails_closed_in_production() -> None:
    class FakeRedis:
        def __init__(self, *, fail: bool = False) -> None:
            self.fail = fail
            self.counts: dict[str, int] = {}

        def eval(self, _script: str, _numkeys: int, key: str, _ttl: str) -> int:
            if self.fail:
                raise RedisError("connection refused")
            assert "user@example.com" not in key
            self.counts[key] = self.counts.get(key, 0) + 1
            return self.counts[key]

    limiter = RedisLoginRateLimiter(
        FakeRedis(),  # type: ignore[arg-type]
        max_attempts=2,
        window_seconds=300,
        fail_closed=True,
    )
    limiter.check_login_attempt(client_ip="10.0.0.1", normalized_email="user@example.com")
    limiter.check_login_attempt(client_ip="10.0.0.1", normalized_email="user@example.com")
    with pytest.raises(RateLimitExceededError):
        limiter.check_login_attempt(client_ip="10.0.0.1", normalized_email="user@example.com")

    prod_down = RedisLoginRateLimiter(
        FakeRedis(fail=True),  # type: ignore[arg-type]
        max_attempts=2,
        window_seconds=300,
        fail_closed=True,
    )
    with pytest.raises(RateLimiterUnavailableError):
        prod_down.check_login_attempt(client_ip="10.0.0.1", normalized_email="user@example.com")

    # Non-production falls back safely without crashing
    dev_down = RedisLoginRateLimiter(
        FakeRedis(fail=True),  # type: ignore[arg-type]
        max_attempts=2,
        window_seconds=300,
        fail_closed=False,
    )
    dev_down.check_login_attempt(client_ip="10.0.0.1", normalized_email="user@example.com")


def test_cli_create_user_and_claim_profile(db_session: Session) -> None:
    legacy_profile = CandidateProfile(full_name="Legacy Candidate")
    db_session.add(legacy_profile)
    db_session.commit()
    db_session.refresh(legacy_profile)
    assert legacy_profile.user_id is None

    rc = run_cli(
        ["create-user", "--email", "cli-owner@example.com"],
        session=db_session,
        password_prompt=lambda: "CliSecretPassword123!",
    )
    assert rc == 0

    # Aborted confirmation leaves legacy profile unowned
    rc_abort = run_cli(
        [
            "claim-profile",
            "--profile-id",
            str(legacy_profile.id),
            "--email",
            "cli-owner@example.com",
        ],
        session=db_session,
        confirm_prompt=lambda _pid, _email: False,
    )
    assert rc_abort == 1
    db_session.refresh(legacy_profile)
    assert legacy_profile.user_id is None

    # Confirmed claim assigns ownership
    rc_claim = run_cli(
        [
            "claim-profile",
            "--profile-id",
            str(legacy_profile.id),
            "--email",
            "cli-owner@example.com",
        ],
        session=db_session,
        confirm_prompt=lambda _pid, _email: True,
    )
    assert rc_claim == 0
    db_session.refresh(legacy_profile)
    assert legacy_profile.user_id is not None

    # Attempting to reassign an already-owned profile fails with ConflictError
    other_user = AuthService(db_session, settings=Settings()).create_user(
        email="other@example.com",
        password="OtherPassword123!",
    )
    with pytest.raises(ConflictError):
        AuthService(db_session).claim_profile(
            profile_id=legacy_profile.id,
            email=other_user.email,
        )

    # Non-existent profile UUID returns non-zero
    assert (
        run_cli(
            [
                "claim-profile",
                "--profile-id",
                str(uuid.uuid4()),
                "--email",
                "cli-owner@example.com",
            ],
            session=db_session,
            confirm_prompt=lambda _pid, _email: True,
        )
        == 1
    )


def test_profile_and_resume_services_fail_closed_on_missing_user_id(
    db_session: Session,
    tmp_path: Path,
) -> None:
    legacy_profile = CandidateProfile(full_name="Unowned Legacy")
    db_session.add(legacy_profile)
    db_session.commit()

    with pytest.raises(InvalidProfileDataError):
        ProfileService(db_session, user_id=None)  # type: ignore[arg-type]

    storage = ResumeStorage.from_settings(Settings(storage_root=tmp_path))
    with pytest.raises(InvalidProfileDataError):
        ResumeImportService(db_session, storage, user_id=None)  # type: ignore[arg-type]


def test_authenticate_rehashes_password_when_needed(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = InMemoryRateLimiter(max_attempts=10, window_seconds=60)
    service = AuthService(db_session, rate_limiter=limiter)
    user = service.create_user(email="rehash@example.com", password="RehashPassword123!")
    original_hash = user.password_hash

    monkeypatch.setattr("app.auth.service.needs_rehash", lambda _h: True)
    service.authenticate(
        email="rehash@example.com",
        password="RehashPassword123!",
        client_ip="127.0.0.1",
    )
    db_session.refresh(user)
    assert user.password_hash != original_hash
    assert verify_password(user.password_hash, "RehashPassword123!")
