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
from app.schemas.auth import (
    CSRFResponse,
    GenericMessageResponse,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    ResendVerificationRequest,
    UserPublicResponse,
    VerifyEmailRequest,
)

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


def _client_ip(request: Request, settings: Settings | None = None) -> str:
    peer_ip = request.client.host if request.client is not None else "unknown"
    current = settings or get_settings()
    if peer_ip in current.auth_trusted_proxies:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Use the rightmost untrusted hop appended by the trusted proxy.
            hops = [hop.strip() for hop in forwarded_for.split(",") if hop.strip()]
            for hop in reversed(hops):
                if hop not in current.auth_trusted_proxies:
                    return hop
        real_ip = request.headers.get("x-real-ip")
        if real_ip and real_ip.strip():
            return real_ip.strip()
    return peer_ip


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
        user=UserPublicResponse(
            id=user.id,
            email=user.email,
            is_active=user.is_active,
            status=user.status,
            email_verified_at=user.email_verified_at,
        ),
        csrf_token=raw_csrf_token,
    )


@router.post(
    "/register",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GenericMessageResponse,
    summary="Register a new account and send email verification",
)
def register(
    payload: RegisterRequest,
    request: Request,
    auth_service: AuthServiceDep,
) -> GenericMessageResponse:
    validate_origin(request)
    auth_service.register_public_user(
        email=payload.email,
        password=payload.password,
        client_ip=_client_ip(request),
    )
    return GenericMessageResponse(
        detail="if registration is eligible, a verification email will be sent shortly"
    )


@router.post(
    "/verify-email",
    status_code=status.HTTP_200_OK,
    response_model=GenericMessageResponse,
    summary="Consume a verification token and activate the user account",
)
def verify_email(
    payload: VerifyEmailRequest,
    request: Request,
    auth_service: AuthServiceDep,
) -> GenericMessageResponse:
    validate_origin(request)
    auth_service.verify_email(
        raw_token=payload.token,
        client_ip=_client_ip(request),
    )
    return GenericMessageResponse(detail="email address verified")


@router.post(
    "/resend-verification",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GenericMessageResponse,
    summary="Request a new verification email for a pending account",
)
def resend_verification(
    payload: ResendVerificationRequest,
    request: Request,
    auth_service: AuthServiceDep,
) -> GenericMessageResponse:
    validate_origin(request)
    auth_service.resend_verification(
        email=payload.email,
        client_ip=_client_ip(request),
    )
    return GenericMessageResponse(
        detail="if the account is pending verification, a verification email will be sent shortly"
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
        status=current_user.status,
        email_verified_at=current_user.email_verified_at,
    )


@router.get(
    "/csrf",
    response_model=CSRFResponse,
    summary="Issue or rotate the CSRF token for the active session",
)
def read_csrf(
    request: Request,
    session_and_user: Annotated[tuple[AuthSession, User], Depends(get_current_session_and_user)],
    auth_service: AuthServiceDep,
) -> CSRFResponse:
    validate_origin(request)
    auth_session, _ = session_and_user
    csrf_token = auth_service.issue_csrf_token(auth_session)
    return CSRFResponse(csrf_token=csrf_token)
