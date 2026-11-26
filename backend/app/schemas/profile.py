from __future__ import annotations

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.schemas.certification import CertificationResponse
from app.schemas.common import APIModel, LongText, Name, validate_http_url
from app.schemas.education import EducationResponse
from app.schemas.experience import ExperienceResponse
from app.schemas.language import LanguageResponse
from app.schemas.preference import JobPreferencesResponse
from app.schemas.project import ProjectResponse
from app.schemas.resume_document import ResumeDocumentResponse
from app.schemas.skill import SkillResponse


def _check_email(value: str | None) -> str | None:
    if value is None:
        return None
    local, _, domain = value.partition("@")
    if not local or not domain or " " in value or "." not in domain:
        raise ValueError("invalid email address")
    return value


class CandidateProfileBase(APIModel):
    full_name: Name
    professional_headline: str | None = Field(default=None, max_length=200)
    professional_summary: LongText | None = None
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    linkedin_url: str | None = Field(default=None, max_length=500)
    github_url: str | None = Field(default=None, max_length=500)
    portfolio_url: str | None = Field(default=None, max_length=500)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str | None) -> str | None:
        return _check_email(value)

    @field_validator("linkedin_url", "github_url", "portfolio_url")
    @classmethod
    def _validate_urls(cls, value: str | None) -> str | None:
        return validate_http_url(value)


class CandidateProfileCreate(CandidateProfileBase):
    pass


class CandidateProfileUpdate(APIModel):
    full_name: Name | None = None
    professional_headline: str | None = Field(default=None, max_length=200)
    professional_summary: LongText | None = None
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    linkedin_url: str | None = Field(default=None, max_length=500)
    github_url: str | None = Field(default=None, max_length=500)
    portfolio_url: str | None = Field(default=None, max_length=500)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str | None) -> str | None:
        return _check_email(value)

    @field_validator("linkedin_url", "github_url", "portfolio_url")
    @classmethod
    def _validate_urls(cls, value: str | None) -> str | None:
        return validate_http_url(value)

    @model_validator(mode="after")
    def _check_not_empty(self) -> Self:
        if "full_name" in self.model_fields_set and self.full_name is None:
            raise ValueError("full_name cannot be null")
        return self


class CandidateProfileResponse(CandidateProfileBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    educations: list[EducationResponse] = Field(default_factory=list)
    experiences: list[ExperienceResponse] = Field(default_factory=list)
    skills: list[SkillResponse] = Field(default_factory=list)
    certifications: list[CertificationResponse] = Field(default_factory=list)
    languages: list[LanguageResponse] = Field(default_factory=list)
    projects: list[ProjectResponse] = Field(default_factory=list)
    preferences: JobPreferencesResponse | None = None
    resume_documents: list[ResumeDocumentResponse] = Field(default_factory=list)
