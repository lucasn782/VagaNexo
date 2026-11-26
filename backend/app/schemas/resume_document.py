from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.models.enums import ParsingStatus
from app.schemas.common import APIModel


class ResumeDocumentCreate(APIModel):
    """Metadata only. The binary file is stored outside PostgreSQL."""

    original_filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=3, max_length=100, pattern=r"^[\w.+-]+/[\w.+-]+$")
    file_size: int = Field(ge=0, le=100 * 1024 * 1024)
    sha256_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    storage_key: str = Field(min_length=1, max_length=500)
    parsing_status: ParsingStatus = ParsingStatus.PENDING

    @field_validator("sha256_hash")
    @classmethod
    def _lowercase_hash(cls, value: str) -> str:
        return value.lower()


class ResumeDocumentUpdate(APIModel):
    original_filename: str | None = Field(default=None, min_length=1, max_length=255)
    media_type: str | None = Field(
        default=None,
        min_length=3,
        max_length=100,
        pattern=r"^[\w.+-]+/[\w.+-]+$",
    )
    parsing_status: ParsingStatus | None = None


class ResumeDocumentResponse(APIModel):
    id: UUID
    candidate_profile_id: UUID
    original_filename: str
    media_type: str
    file_size: int
    sha256_hash: str
    storage_key: str
    parsing_status: ParsingStatus
    failure_reason: str | None = None
    uploaded_at: datetime
