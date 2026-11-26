from __future__ import annotations

from datetime import date
from typing import Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.models.enums import ProjectType
from app.schemas.common import (
    APIModel,
    LongText,
    Name,
    ProvenanceCreate,
    ProvenanceResponse,
    ProvenanceUpdate,
    validate_http_url,
    validate_period,
)


class ProjectBase(APIModel):
    name: Name
    description: LongText | None = None
    role: str | None = Field(default=None, max_length=200)
    project_url: str | None = Field(default=None, max_length=500)
    start_date: date | None = None
    end_date: date | None = None
    technologies: list[str] | None = Field(default=None, max_length=50)
    project_type: ProjectType = ProjectType.OTHER

    @field_validator("project_url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        return validate_http_url(value)

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        validate_period(self.start_date, self.end_date, None)
        return self


class ProjectCreate(ProjectBase, ProvenanceCreate):
    pass


class ProjectUpdate(ProvenanceUpdate):
    name: Name | None = None
    description: LongText | None = None
    role: str | None = Field(default=None, max_length=200)
    project_url: str | None = Field(default=None, max_length=500)
    start_date: date | None = None
    end_date: date | None = None
    technologies: list[str] | None = Field(default=None, max_length=50)
    project_type: ProjectType | None = None

    @field_validator("project_url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        return validate_http_url(value)

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        validate_period(self.start_date, self.end_date, None)
        return self


class ProjectResponse(ProjectBase, ProvenanceResponse):
    id: UUID
    candidate_profile_id: UUID
