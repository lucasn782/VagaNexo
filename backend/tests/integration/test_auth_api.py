from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_rate_limiter
from app.auth.rate_limit import InMemoryRateLimiter
from app.auth.service import AuthService
from app.core.config import get_settings
from app.main import app
from app.models.auth_session import AuthSession


def test_login_sets_secure_httponly_cookie_and_returns_public_user(
    unauthenticated_client: TestClient,
    db_session: Session,
) -> None:
    AuthService(db_session).create_user(
        email="alice@example.com",
        password="AlicePassword123!",
    )

    resp = unauthenticated_client.post(
        "/api/v1/auth/login",
        json={"email": "  ALICE@Example.com ", "password": "AlicePassword123!"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["is_active"] is True
    assert "password_hash" not in body["user"]
    assert "csrf_token" in body

    set_cookie = resp.headers.get("set-cookie", "")
    assert f"{get_settings().auth_session_cookie_name}=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/" in set_cookie

    me_resp = unauthenticated_client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json() == {
        "id": body["user"]["id"],
        "email": "alice@example.com",
        "is_active": True,
    }


def test_login_rejects_wrong_password_nonexistent_and_inactive_with_generic_error(
    unauthenticated_client: TestClient,
    db_session: Session,
) -> None:
    AuthService(db_session).create_user(
        email="active@example.com",
        password="CorrectPassword123!",
    )
    AuthService(db_session).create_user(
        email="inactive@example.com",
        password="CorrectPassword123!",
        is_active=False,
    )

    bad_pw = unauthenticated_client.post(
        "/api/v1/auth/login",
        json={"email": "active@example.com", "password": "WrongPassword!"},
    )
    missing = unauthenticated_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "WrongPassword!"},
    )
    inactive = unauthenticated_client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@example.com", "password": "CorrectPassword123!"},
    )
    assert bad_pw.status_code == 401
    assert missing.status_code == 401
    assert inactive.status_code == 401
    assert bad_pw.json() == missing.json() == inactive.json()


def test_csrf_origin_logout_and_revoked_session_rejection(
    unauthenticated_client: TestClient,
    db_session: Session,
) -> None:
    AuthService(db_session).create_user(
        email="csrf@example.com",
        password="CsrfPassword123!",
    )

    # Disallowed Origin on login is rejected
    bad_origin_login = unauthenticated_client.post(
        "/api/v1/auth/login",
        json={"email": "csrf@example.com", "password": "CsrfPassword123!"},
        headers={"Origin": "https://evil.example.com"},
    )
    assert bad_origin_login.status_code == 403

    login_resp = unauthenticated_client.post(
        "/api/v1/auth/login",
        json={"email": "csrf@example.com", "password": "CsrfPassword123!"},
    )
    assert login_resp.status_code == 200
    csrf_token = login_resp.json()["csrf_token"]

    # State-changing request without CSRF fails
    no_csrf = unauthenticated_client.post("/api/v1/profiles", json={"full_name": "Blocked"})
    assert no_csrf.status_code == 403

    # State-changing request with wrong CSRF fails
    bad_csrf = unauthenticated_client.post(
        "/api/v1/profiles",
        json={"full_name": "Blocked"},
        headers={"X-CSRF-Token": "wrong-token"},
    )
    assert bad_csrf.status_code == 403

    # Rotate CSRF via /csrf
    csrf_resp = unauthenticated_client.get("/api/v1/auth/csrf")
    assert csrf_resp.status_code == 200
    rotated_csrf = csrf_resp.json()["csrf_token"]
    assert rotated_csrf != csrf_token

    # Old CSRF is now invalid, rotated CSRF works for logout
    assert (
        unauthenticated_client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf_token},
        ).status_code
        == 403
    )

    logout_resp = unauthenticated_client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": rotated_csrf},
    )
    assert logout_resp.status_code == 204

    # Revoked session cannot be reused
    assert unauthenticated_client.get("/api/v1/auth/me").status_code == 401


def test_expired_session_is_rejected(
    unauthenticated_client: TestClient,
    db_session: Session,
) -> None:
    user = AuthService(db_session).create_user(
        email="expired@example.com",
        password="ExpiredPassword123!",
    )
    login_resp = unauthenticated_client.post(
        "/api/v1/auth/login",
        json={"email": "expired@example.com", "password": "ExpiredPassword123!"},
    )
    assert login_resp.status_code == 200

    auth_session = db_session.scalar(select(AuthSession).where(AuthSession.user_id == user.id))
    assert auth_session is not None
    auth_session.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    assert unauthenticated_client.get("/api/v1/auth/me").status_code == 401


def test_cors_and_rate_limiting_enforced(
    unauthenticated_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # CORS allows configured origin with credentials, rejects unknown origin
    preflight_ok = unauthenticated_client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, X-CSRF-Token",
        },
    )
    assert preflight_ok.status_code == 200
    assert preflight_ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert preflight_ok.headers.get("access-control-allow-credentials") == "true"

    preflight_bad = unauthenticated_client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://attacker.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in preflight_bad.headers

    # Rate limit triggers 429
    strict_limiter = InMemoryRateLimiter(max_attempts=2, window_seconds=300)
    app.dependency_overrides[get_rate_limiter] = lambda: strict_limiter
    for _ in range(2):
        r = unauthenticated_client.post(
            "/api/v1/auth/login",
            json={"email": "rl@example.com", "password": "wrong"},
        )
        assert r.status_code == 401
    blocked = unauthenticated_client.post(
        "/api/v1/auth/login",
        json={"email": "rl@example.com", "password": "wrong"},
    )
    assert blocked.status_code == 429
