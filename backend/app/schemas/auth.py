from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel


class LoginRequest(APIModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class RegisterRequest(APIModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)


class VerifyEmailRequest(APIModel):
    token: str = Field(min_length=16, max_length=512)


class ResendVerificationRequest(APIModel):
    email: str = Field(min_length=3, max_length=320)


class UserPublicResponse(APIModel):
    id: UUID
    email: str
    is_active: bool
    status: str = "active"
    email_verified_at: datetime | None = None


class LoginResponse(APIModel):
    user: UserPublicResponse
    csrf_token: str


class CSRFResponse(APIModel):
    csrf_token: str


class GenericMessageResponse(APIModel):
    detail: str
