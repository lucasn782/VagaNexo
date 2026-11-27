"""Domain exceptions for VagaNexo authentication and authorization."""

from __future__ import annotations


class AuthError(Exception):
    """Base error translated into a controlled HTTP response."""

    status_code = 400
    detail = "authentication error"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.__class__.detail
        super().__init__(self.detail)


class InvalidCredentialsError(AuthError):
    status_code = 401
    detail = "invalid email or password"


class AuthenticationRequiredError(AuthError):
    status_code = 401
    detail = "authentication required"


class CSRFError(AuthError):
    status_code = 403
    detail = "invalid or missing CSRF token"


class OriginNotAllowedError(AuthError):
    status_code = 403
    detail = "origin not allowed"


class RateLimitExceededError(AuthError):
    status_code = 429
    detail = "too many login attempts; please try again later"


class RateLimiterUnavailableError(AuthError):
    status_code = 503
    detail = "authentication rate limiting is temporarily unavailable"


class UserAlreadyExistsError(AuthError):
    status_code = 409
    detail = "a user with this email already exists"


class InvalidUserDataError(AuthError):
    status_code = 422
    detail = "invalid user data"
