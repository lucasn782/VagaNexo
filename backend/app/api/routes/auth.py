"""Authentication endpoints: login, logout, current user, and CSRF token."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.auth.dependencies import (
    ActiveUserDep,
    AuthServiceDep,
    get_current_session_and_user,
    require_csrf,
    validate_origin,
)
from app.core.config import Settings, get_settings
from app.models.auth_session import AuthSession
from app.models.user import User
from app.schemas.auth import CSRFResponse, LoginRequest, LoginResponse, UserPublicResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _cookie_secure(settings: Settings) -> bool:
    if settings.auth_cookie_secure is not None:
        return settings.auth_cookie_secure
    return settings.app_env == "production"


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.auth_session_cookie_name,
        value=token,
        max_age=settings.auth_session_ttl_seconds,
        httponly=True,
        secure=_cookie_secure(settings),
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.auth_session_cookie_name,
        path="/",
        httponly=True,
        secure=_cookie_secure(settings),
        samesite="lax",
    )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Authenticate user and establish an opaque session cookie",
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth_service: AuthServiceDep,
) -> LoginResponse:
    validate_origin(request)
    user, raw_session_token, raw_csrf_token = auth_service.authenticate(
        email=payload.email,
        password=payload.password,
        client_ip=_client_ip(request),
    )
    settings = get_settings()
    _set_session_cookie(response, raw_session_token, settings)
    return LoginResponse(
        user=UserPublicResponse(id=user.id, email=user.email, is_active=user.is_active),
        csrf_token=raw_csrf_token,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Revoke the active session and clear the session cookie",
)
def logout(
    session_and_user: Annotated[tuple[AuthSession, User], Depends(require_csrf)],
    auth_service: AuthServiceDep,
) -> Response:
    auth_session, _ = session_and_user
    auth_service.revoke_session(auth_session)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_session_cookie(response, get_settings())
    return response


@router.get(
    "/me",
    response_model=UserPublicResponse,
    summary="Return the currently authenticated user",
)
def read_me(current_user: ActiveUserDep) -> UserPublicResponse:
    return UserPublicResponse(
        id=current_user.id,
        email=current_user.email,
        is_active=current_user.is_active,
    )


@router.get(
    "/csrf",
    response_model=CSRFResponse,
    summary="Issue or rotate the CSRF token for the active session",
)
def read_csrf(
    session_and_user: Annotated[tuple[AuthSession, User], Depends(get_current_session_and_user)],
    auth_service: AuthServiceDep,
) -> CSRFResponse:
    auth_session, _ = session_and_user
    csrf_token = auth_service.issue_csrf_token(auth_session)
    return CSRFResponse(csrf_token=csrf_token)
