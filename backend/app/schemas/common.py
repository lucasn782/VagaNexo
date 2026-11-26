from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, TypeAdapter

from app.models.enums import SourceType, ValidationStatus

Name = Annotated[str, StringConstraints(min_length=1, max_length=200)]
ShortLabel = Annotated[str, StringConstraints(min_length=1, max_length=120)]
LongText = Annotated[str, StringConstraints(max_length=20_000)]


class APIModel(BaseModel):
    """Base model shared by every request and response schema."""

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


def validate_period(
    start_date: date | None,
    end_date: date | None,
    is_current: bool | None,
    *,
    label: str = "end_date",
) -> None:
    if start_date is not None and end_date is not None and end_date < start_date:
        raise ValueError(f"{label} must be greater than or equal to start_date")
    if is_current and end_date is not None:
        raise ValueError("end_date must be empty when is_current is true")


_HTTP_URL_ADAPTER: TypeAdapter[HttpUrl] = TypeAdapter(HttpUrl)


def validate_http_url(value: str | None) -> str | None:
    """Validate an optional absolute HTTP(S) URL without rewriting the value."""
    if value is None or value == "":
        return None
    _HTTP_URL_ADAPTER.validate_python(value)
    return value


def validate_salary_range(minimum: float | None, maximum: float | None) -> None:
    if minimum is not None and minimum < 0:
        raise ValueError("minimum_salary must be greater than or equal to 0")
    if maximum is not None and maximum < 0:
        raise ValueError("maximum_salary must be greater than or equal to 0")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError("minimum_salary must be lower than or equal to maximum_salary")


class ProvenanceCreate(APIModel):
    source_type: SourceType = SourceType.MANUAL
    validation_status: ValidationStatus | None = Field(
        default=None,
        description=(
            "Leave empty to let the server decide: manual records become confirmed, "
            "document and AI records always start as pending."
        ),
    )
    source_document_id: UUID | None = None
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)


class ProvenanceUpdate(APIModel):
    source_type: SourceType | None = None
    source_document_id: UUID | None = None
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)


class ProvenanceResponse(APIModel):
    source_type: SourceType
    validation_status: ValidationStatus
    source_document_id: UUID | None
    confidence_score: float | None
    created_at: datetime
    updated_at: datetime


class ValidationStatusResponse(APIModel):
    resource: str
    id: UUID
    validation_status: ValidationStatus
    updated_at: datetime


class MessageResponse(APIModel):
    detail: str
