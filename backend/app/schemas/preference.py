from __future__ import annotations

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.models.enums import EmploymentType, SeniorityLevel, WorkMode
from app.schemas.common import APIModel, validate_salary_range


class JobPreferencesUpsert(APIModel):
    preferred_job_titles: list[str] = Field(default_factory=list, max_length=50)
    preferred_locations: list[str] = Field(default_factory=list, max_length=50)
    work_modes: list[WorkMode] = Field(default_factory=list, max_length=3)
    employment_types: list[EmploymentType] = Field(default_factory=list, max_length=7)
    minimum_salary: float | None = Field(default=None, ge=0, le=999_999_999)
    maximum_salary: float | None = Field(default=None, ge=0, le=999_999_999)
    salary_currency: str | None = Field(default=None, min_length=3, max_length=3)
    willingness_to_relocate: bool = False
    preferred_seniority: SeniorityLevel | None = None

    @field_validator("salary_currency")
    @classmethod
    def _normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.upper()

    @model_validator(mode="after")
    def _check_salary(self) -> Self:
        validate_salary_range(self.minimum_salary, self.maximum_salary)
        return self


class JobPreferencesResponse(APIModel):
    id: UUID
    candidate_profile_id: UUID
    preferred_job_titles: list[str]
    preferred_locations: list[str]
    work_modes: list[WorkMode]
    employment_types: list[EmploymentType]
    minimum_salary: float | None
    maximum_salary: float | None
    salary_currency: str | None
    willingness_to_relocate: bool
    preferred_seniority: SeniorityLevel | None
    created_at: datetime
    updated_at: datetime
