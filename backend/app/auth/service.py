"""Authentication, session lifecycle, and profile ownership claims."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.exceptions import (
    AuthenticationRequiredError,
    InvalidCredentialsError,
    InvalidUserDataError,
    UserAlreadyExistsError,
)
from app.auth.rate_limit import RateLimiter, RedisLoginRateLimiter
from app.auth.security import (
    dummy_verify_password,
    generate_csrf_token,
    generate_session_token,
    hash_password,
    hash_token,
    normalize_email,
    verify_password,
)
from app.core.config import Settings, get_settings
from app.models.auth_session import AuthSession
from app.models.candidate_profile import CandidateProfile
from app.models.user import User
from app.profile.exceptions import ConflictError, ProfileNotFoundError

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AuthService:
    """Server-side user identity and opaque session management."""

    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.rate_limiter = rate_limiter or RedisLoginRateLimiter.from_settings(self.settings)

    def create_user(
        self,
        *,
        email: str,
        password: str,
        is_active: bool = True,
    ) -> User:
        normalized = normalize_email(email)
        password_hash = hash_password(password)
        user = User(
            email=normalized,
            password_hash=password_hash,
            is_active=is_active,
        )
        self.session.add(user)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise UserAlreadyExistsError() from exc
        self.session.refresh(user)
        logger.info("Provisioned user account %s", user.id)
        return user

    def authenticate(
        self,
        *,
        email: str,
        password: str,
        client_ip: str,
    ) -> tuple[User, str, str]:
        try:
            normalized = normalize_email(email)
        except InvalidUserDataError:
            self.rate_limiter.check_login_attempt(
                client_ip=client_ip,
                normalized_email="__invalid__",
            )
            dummy_verify_password(password)
            raise InvalidCredentialsError() from None

        self.rate_limiter.check_login_attempt(
            client_ip=client_ip,
            normalized_email=normalized,
        )

        user = self.session.scalar(select(User).where(User.email == normalized))
        if user is None:
            dummy_verify_password(password)
            raise InvalidCredentialsError()

        if not verify_password(user.password_hash, password):
            raise InvalidCredentialsError()

        if not user.is_active:
            raise InvalidCredentialsError()

        raw_session_token = generate_session_token()
        raw_csrf_token = generate_csrf_token()
        now = _utcnow()
        auth_session = AuthSession(
            user_id=user.id,
            token_hash=hash_token(raw_session_token),
            csrf_token_hash=hash_token(raw_csrf_token),
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(seconds=self.settings.auth_session_ttl_seconds),
        )
        self.session.add(auth_session)
        self.session.commit()
        return user, raw_session_token, raw_csrf_token

    def get_active_session(self, raw_session_token: str | None) -> tuple[AuthSession, User]:
        if not raw_session_token:
            raise AuthenticationRequiredError()

        token_digest = hash_token(raw_session_token)
        auth_session = self.session.scalar(
            select(AuthSession).where(AuthSession.token_hash == token_digest)
        )
        if auth_session is None:
            raise AuthenticationRequiredError()

        now = _utcnow()
        expires_at = auth_session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        if auth_session.revoked_at is not None or expires_at <= now:
            raise AuthenticationRequiredError("session expired or revoked")

        user = self.session.scalar(select(User).where(User.id == auth_session.user_id))
        if user is None or not user.is_active:
            raise AuthenticationRequiredError("user account is inactive")

        auth_session.last_seen_at = now
        self.session.commit()
        return auth_session, user

    def issue_csrf_token(self, auth_session: AuthSession) -> str:
        raw_csrf_token = generate_csrf_token()
        auth_session.csrf_token_hash = hash_token(raw_csrf_token)
        auth_session.last_seen_at = _utcnow()
        self.session.commit()
        return raw_csrf_token

    def revoke_session(self, auth_session: AuthSession) -> None:
        if auth_session.revoked_at is None:
            auth_session.revoked_at = _utcnow()
            self.session.commit()

    def claim_profile(self, *, profile_id: uuid.UUID, email: str) -> CandidateProfile:
        normalized = normalize_email(email)
        user = self.session.scalar(select(User).where(User.email == normalized))
        if user is None:
            raise InvalidUserDataError("target user account does not exist")

        profile = self.session.scalar(
            select(CandidateProfile).where(CandidateProfile.id == profile_id)
        )
        if profile is None:
            raise ProfileNotFoundError("profile not found")

        if profile.user_id is not None:
            raise ConflictError("profile already has an assigned owner")

        profile.user_id = user.id
        self.session.commit()
        self.session.refresh(profile)
        logger.info("Assigned legacy profile %s to user %s", profile.id, user.id)
        return profile
