"""Cryptographic primitives for passwords, opaque sessions, and CSRF tokens."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.auth.exceptions import InvalidUserDataError

_PASSWORD_HASHER = PasswordHasher()
# Dummy hash computed once at import time to mitigate timing-based user enumeration.
_DUMMY_PASSWORD_HASH = _PASSWORD_HASHER.hash("vaganexo-dummy-constant-time-password")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 256


def normalize_email(raw_email: str) -> str:
    """Normalize an email address with strip() + casefold() and validate structure."""
    if not isinstance(raw_email, str):
        raise InvalidUserDataError("invalid email address")
    normalized = raw_email.strip().casefold()
    if (
        not normalized
        or len(normalized) > 320
        or any(ch.isspace() for ch in normalized)
        or normalized.count("@") != 1
    ):
        raise InvalidUserDataError("invalid email address")
    local, _, domain = normalized.partition("@")
    if (
        not local
        or not domain
        or "." not in domain
        or domain.startswith(".")
        or domain.endswith(".")
    ):
        raise InvalidUserDataError("invalid email address")
    return normalized


def validate_password_strength(password: str) -> None:
    """Enforce baseline password length constraints."""
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidUserDataError(
            f"password must be at least {MIN_PASSWORD_LENGTH} characters long"
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise InvalidUserDataError(f"password must not exceed {MAX_PASSWORD_LENGTH} characters")


def hash_password(password: str) -> str:
    """Hash a password using Argon2id."""
    validate_password_strength(password)
    return _PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Verify a password against an Argon2id hash."""
    if not password or not password_hash:
        return False
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Return True if an Argon2id hash should be upgraded to current parameters."""
    try:
        return _PASSWORD_HASHER.check_needs_rehash(password_hash)
    except InvalidHashError:
        return False


def dummy_verify_password(password: str) -> None:
    """Perform a constant-time dummy Argon2id check when an account does not exist."""
    verify_password(_DUMMY_PASSWORD_HASH, password or "dummy")


def generate_session_token() -> str:
    """Generate a URL-safe opaque session token with 256 bits of entropy."""
    return secrets.token_urlsafe(32)


def generate_csrf_token() -> str:
    """Generate a URL-safe CSRF token with 256 bits of entropy."""
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest of an opaque session or CSRF token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def verify_token_hash(raw_token: str | None, expected_hash: str | None) -> bool:
    """Constant-time verification of a raw token against its persisted SHA-256 hash."""
    if not raw_token or not expected_hash:
        return False
    actual_hash = hash_token(raw_token)
    return hmac.compare_digest(actual_hash, expected_hash)
