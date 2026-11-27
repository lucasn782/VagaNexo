from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel


class LoginRequest(APIModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class UserPublicResponse(APIModel):
    id: UUID
    email: str
    is_active: bool


class LoginResponse(APIModel):
    user: UserPublicResponse
    csrf_token: str


class CSRFResponse(APIModel):
    csrf_token: str
