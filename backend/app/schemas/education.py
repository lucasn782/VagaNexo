from __future__ import annotations

from datetime import date
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.common import (
    APIModel,
    LongText,
    Name,
    ProvenanceCreate,
    ProvenanceResponse,
    ProvenanceUpdate,
    validate_period,
)


class EducationBase(APIModel):
    institution: Name
    degree: Name
    field_of_study: str | None = Field(default=None, max_length=200)
    start_date: date
    end_date: date | None = None
    is_current: bool = False
    description: LongText | None = None

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        validate_period(self.start_date, self.end_date, self.is_current)
        return self


class EducationCreate(EducationBase, ProvenanceCreate):
    pass


class EducationUpdate(ProvenanceUpdate):
    institution: Name | None = None
    degree: Name | None = None
    field_of_study: str | None = Field(default=None, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool | None = None
    description: LongText | None = None

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        validate_period(self.start_date, self.end_date, self.is_current)
        return self


class EducationResponse(EducationBase, ProvenanceResponse):
    id: UUID
    candidate_profile_id: UUID
