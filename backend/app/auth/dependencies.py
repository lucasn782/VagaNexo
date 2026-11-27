"""FastAPI dependencies for authentication, CSRF, Origin checks, and ownership."""

from __future__ import annotations

import uuid
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.exceptions import (
    AuthenticationRequiredError,
    CSRFError,
    OriginNotAllowedError,
)
from app.auth.rate_limit import RateLimiter, RedisLoginRateLimiter
from app.auth.security import verify_token_hash
from app.auth.service import AuthService
from app.core.config import Settings, get_settings
from app.database.dependencies import get_db
from app.models.auth_session import AuthSession
from app.models.candidate_profile import CandidateProfile
from app.models.user import User
from app.profile.exceptions import ProfileNotFoundError

SessionDep = Annotated[Session, Depends(get_db)]


def get_rate_limiter() -> RateLimiter:
    return RedisLoginRateLimiter.from_settings()


def get_auth_service(
    session: SessionDep,
    rate_limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> AuthService:
    return AuthService(session, rate_limiter=rate_limiter)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def validate_origin(request: Request, settings: Settings | None = None) -> None:
    """Reject requests whose Origin or Referer is outside the configured allowlist."""
    current = settings or get_settings()
    origin = request.headers.get("origin")
    if origin is not None:
        if origin not in current.cors_origins:
            raise OriginNotAllowedError()
        return

    referer = request.headers.get("referer")
    if referer is not None:
        parsed = urlsplit(referer)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise OriginNotAllowedError()
        referer_origin = f"{parsed.scheme}://{parsed.netloc}"
        if referer_origin not in current.cors_origins:
            raise OriginNotAllowedError()
        return

    if current.app_env == "production":
        raise OriginNotAllowedError()


def get_current_session_and_user(
    request: Request,
    auth_service: AuthServiceDep,
) -> tuple[AuthSession, User]:
    settings = get_settings()
    raw_token = request.cookies.get(settings.auth_session_cookie_name)
    if not raw_token:
        raise AuthenticationRequiredError()
    return auth_service.get_active_session(raw_token)


def get_current_user(
    session_and_user: Annotated[tuple[AuthSession, User], Depends(get_current_session_and_user)],
) -> User:
    _, user = session_and_user
    return user


def get_current_active_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not user.is_active:
        raise AuthenticationRequiredError("user account is inactive")
    return user


def require_csrf(
    request: Request,
    session_and_user: Annotated[tuple[AuthSession, User], Depends(get_current_session_and_user)],
) -> tuple[AuthSession, User]:
    """Enforce Origin allowlist and X-CSRF-Token validation on state-changing routes."""
    validate_origin(request)
    auth_session, user = session_and_user
    csrf_header = request.headers.get("x-csrf-token")
    if not verify_token_hash(csrf_header, auth_session.csrf_token_hash):
        raise CSRFError()
    return auth_session, user


def require_csrf_user(
    session_and_user: Annotated[tuple[AuthSession, User], Depends(require_csrf)],
) -> User:
    _, user = session_and_user
    return user


ActiveUserDep = Annotated[User, Depends(get_current_active_user)]
CSRFProtectedUserDep = Annotated[User, Depends(require_csrf_user)]


def require_owned_profile(
    profile_id: uuid.UUID,
    current_user: ActiveUserDep,
    db: SessionDep,
) -> CandidateProfile:
    """Load a profile only when it is explicitly owned by ``current_user``.

    Legacy profiles with ``user_id IS NULL`` and profiles belonging to other
    users return 404 Not Found to prevent cross-tenant existence disclosure.
    """
    profile = db.scalar(
        select(CandidateProfile).where(
            CandidateProfile.id == profile_id,
            CandidateProfile.user_id == current_user.id,
        )
    )
    if profile is None:
        raise ProfileNotFoundError("profile not found")
    return profile
