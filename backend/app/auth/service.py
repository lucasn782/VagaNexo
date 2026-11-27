"""Authentication, account lifecycle, session management, and profile ownership claims."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.exceptions import (
    AuthenticationRequiredError,
    InvalidActionTokenError,
    InvalidCredentialsError,
    InvalidUserDataError,
    RegistrationDisabledError,
    UserAlreadyExistsError,
)
from app.auth.outbox import EmailOutboxService
from app.auth.rate_limit import RateLimiter, RedisLoginRateLimiter
from app.auth.security import (
    dummy_verify_password,
    generate_csrf_token,
    generate_session_token,
    hash_password,
    hash_token,
    needs_rehash,
    normalize_email,
    verify_password,
)
from app.auth.tokens import ActionTokenService
from app.core.config import Settings, get_settings
from app.models.auth_session import AuthSession
from app.models.candidate_profile import CandidateProfile
from app.models.enums import AccountStatus, ActionTokenPurpose
from app.models.user import User
from app.profile.exceptions import ConflictError, ProfileNotFoundError
from app.workers.email_tasks import dispatch_outbox_email

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AuthService:
    """Server-side user identity, lifecycle, and opaque session management."""

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
        verify_email: bool = False,
    ) -> User:
        normalized = normalize_email(email)
        password_hash = hash_password(password)
        account_status = AccountStatus.ACTIVE if is_active else AccountStatus.DISABLED
        user = User(
            email=normalized,
            password_hash=password_hash,
            status=account_status.value,
            is_active=is_active,
            email_verified_at=_utcnow() if verify_email else None,
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

    def register_public_user(
        self,
        *,
        email: str,
        password: str,
        client_ip: str,
    ) -> uuid.UUID | None:
        if not self.settings.auth_public_registration_enabled:
            raise RegistrationDisabledError()

        self.rate_limiter.check_rate_limit(
            scope="general_auth",
            key_value=client_ip or "unknown",
            max_attempts=self.settings.auth_general_rate_limit_max_attempts,
            window_seconds=self.settings.auth_general_rate_limit_window_seconds,
        )
        self.rate_limiter.check_rate_limit(
            scope="register",
            key_value=client_ip or "unknown",
            max_attempts=self.settings.auth_register_rate_limit_max_attempts,
            window_seconds=self.settings.auth_register_rate_limit_window_seconds,
        )

        normalized = normalize_email(email)
        password_hash = hash_password(password)

        existing = self.session.scalar(select(User).where(User.email == normalized))
        if existing is not None:
            # Anti-enumeration: never disclose account existence or status.
            if existing.status == AccountStatus.PENDING_VERIFICATION.value:
                outbox_id = self._issue_verification_and_outbox(existing)
                self.session.commit()
                dispatch_outbox_email(outbox_id)
                return outbox_id
            return None

        user = User(
            email=normalized,
            password_hash=password_hash,
            status=AccountStatus.PENDING_VERIFICATION.value,
            is_active=False,
            email_verified_at=None,
        )
        self.session.add(user)
        try:
            self.session.flush()
            outbox_id = self._issue_verification_and_outbox(user)
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            # Concurrent registration race: return uniform response without leaking DB state.
            return None

        dispatch_outbox_email(outbox_id)
        logger.info("Registered pending user account %s", user.id)
        return outbox_id

    def verify_email(self, *, raw_token: str, client_ip: str) -> User:
        self.rate_limiter.check_rate_limit(
            scope="general_auth",
            key_value=client_ip or "unknown",
            max_attempts=self.settings.auth_general_rate_limit_max_attempts,
            window_seconds=self.settings.auth_general_rate_limit_window_seconds,
        )

        _, user_id = ActionTokenService.consume_token(
            self.session,
            raw_token=raw_token,
            purpose=ActionTokenPurpose.EMAIL_VERIFICATION,
        )
        user = self.session.scalar(select(User).where(User.id == user_id))
        if user is None or user.status in {
            AccountStatus.SUSPENDED.value,
            AccountStatus.DISABLED.value,
        }:
            self.session.rollback()
            raise InvalidActionTokenError()

        now = _utcnow()
        user.set_status(AccountStatus.ACTIVE)
        if user.email_verified_at is None:
            user.email_verified_at = now
        self.session.commit()
        self.session.refresh(user)
        logger.info("Verified email for user account %s", user.id)
        return user

    def resend_verification(self, *, email: str, client_ip: str) -> uuid.UUID | None:
        self.rate_limiter.check_rate_limit(
            scope="general_auth",
            key_value=client_ip or "unknown",
            max_attempts=self.settings.auth_general_rate_limit_max_attempts,
            window_seconds=self.settings.auth_general_rate_limit_window_seconds,
        )
        self.rate_limiter.check_rate_limit(
            scope="email_resend:ip",
            key_value=client_ip or "unknown",
            max_attempts=self.settings.auth_resend_rate_limit_max_attempts,
            window_seconds=self.settings.auth_resend_rate_limit_window_seconds,
        )

        try:
            normalized = normalize_email(email)
        except InvalidUserDataError:
            return None

        self.rate_limiter.check_rate_limit(
            scope="email_resend:acct",
            key_value=normalized,
            max_attempts=self.settings.auth_resend_rate_limit_max_attempts,
            window_seconds=self.settings.auth_resend_rate_limit_window_seconds,
        )

        user = self.session.scalar(select(User).where(User.email == normalized))
        if user is None or user.status != AccountStatus.PENDING_VERIFICATION.value:
            # Anti-enumeration: uniform response, no unnecessary emails for verified/active users.
            return None

        outbox_id = self._issue_verification_and_outbox(user)
        self.session.commit()
        dispatch_outbox_email(outbox_id)
        return outbox_id

    def _issue_verification_and_outbox(self, user: User) -> uuid.UUID:
        ttl = timedelta(hours=self.settings.email_verification_ttl_hours)
        _, raw_token = ActionTokenService.issue_token(
            self.session,
            user_id=user.id,
            purpose=ActionTokenPurpose.EMAIL_VERIFICATION,
            ttl=ttl,
        )
        outbox = EmailOutboxService.enqueue_verification_email(
            self.session,
            user_id=user.id,
            recipient_email=user.email,
            raw_token=raw_token,
            settings=self.settings,
        )
        return outbox.id

    def authenticate(
        self,
        *,
        email: str,
        password: str,
        client_ip: str,
    ) -> tuple[User, str, str]:
        self.rate_limiter.check_rate_limit(
            scope="general_auth",
            key_value=client_ip or "unknown",
            max_attempts=self.settings.auth_general_rate_limit_max_attempts,
            window_seconds=self.settings.auth_general_rate_limit_window_seconds,
        )
        try:
            normalized = normalize_email(email)
        except InvalidUserDataError:
            self.rate_limiter.check_login_allowed(
                client_ip=client_ip,
                normalized_email="__invalid__",
            )
            self.rate_limiter.record_login_failure(
                client_ip=client_ip,
                normalized_email="__invalid__",
            )
            dummy_verify_password(password)
            raise InvalidCredentialsError() from None

        self.rate_limiter.check_login_allowed(
            client_ip=client_ip,
            normalized_email=normalized,
        )

        user = self.session.scalar(select(User).where(User.email == normalized))
        if user is None:
            self.rate_limiter.record_login_failure(
                client_ip=client_ip,
                normalized_email=normalized,
            )
            dummy_verify_password(password)
            raise InvalidCredentialsError()

        if not verify_password(user.password_hash, password):
            self.rate_limiter.record_login_failure(
                client_ip=client_ip,
                normalized_email=normalized,
            )
            raise InvalidCredentialsError()

        if user.status != AccountStatus.ACTIVE.value or not user.is_active:
            self.rate_limiter.record_login_failure(
                client_ip=client_ip,
                normalized_email=normalized,
            )
            raise InvalidCredentialsError()

        self.rate_limiter.record_login_success(
            client_ip=client_ip,
            normalized_email=normalized,
        )

        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

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
        if user is None or user.status != AccountStatus.ACTIVE.value or not user.is_active:
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

        result = self.session.execute(
            update(CandidateProfile)
            .where(
                CandidateProfile.id == profile_id,
                CandidateProfile.user_id.is_(None),
            )
            .values(user_id=user.id)
            .returning(CandidateProfile.id)
        )
        updated_id = result.scalar_one_or_none()
        if updated_id is None:
            self.session.rollback()
            exists = self.session.scalar(
                select(CandidateProfile.id).where(CandidateProfile.id == profile_id)
            )
            if exists is None:
                raise ProfileNotFoundError("profile not found")
            raise ConflictError("profile already has an assigned owner")

        self.session.commit()
        profile = self.session.scalar(
            select(CandidateProfile).where(CandidateProfile.id == profile_id)
        )
        assert profile is not None
        logger.info("Assigned legacy profile %s to user %s", profile.id, user.id)
        return profile
