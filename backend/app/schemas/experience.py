from __future__ import annotations

from datetime import date
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from app.models.enums import EmploymentType
from app.schemas.common import (
    APIModel,
    LongText,
    Name,
    ProvenanceCreate,
    ProvenanceResponse,
    ProvenanceUpdate,
    validate_period,
)


class ExperienceBase(APIModel):
    company: Name
    job_title: Name
    employment_type: EmploymentType = EmploymentType.FULL_TIME
    location: str | None = Field(default=None, max_length=200)
    start_date: date
    end_date: date | None = None
    is_current: bool = False
    description: LongText | None = None
    achievements: list[str] | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        validate_period(self.start_date, self.end_date, self.is_current)
        return self


class ExperienceCreate(ExperienceBase, ProvenanceCreate):
    pass


class ExperienceUpdate(ProvenanceUpdate):
    company: Name | None = None
    job_title: Name | None = None
    employment_type: EmploymentType | None = None
    location: str | None = Field(default=None, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool | None = None
    description: LongText | None = None
    achievements: list[str] | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        validate_period(self.start_date, self.end_date, self.is_current)
        return self


class ExperienceResponse(ExperienceBase, ProvenanceResponse):
    id: UUID
    candidate_profile_id: UUID
