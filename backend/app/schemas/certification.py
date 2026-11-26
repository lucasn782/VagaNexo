from __future__ import annotations

from datetime import date
from typing import Self
from uuid import UUID

from pydantic import field_validator, model_validator

from app.schemas.common import (
    APIModel,
    Name,
    ProvenanceCreate,
    ProvenanceResponse,
    ProvenanceUpdate,
    validate_http_url,
)


class CertificationBase(APIModel):
    name: Name
    issuing_organization: Name
    issue_date: date | None = None
    expiration_date: date | None = None
    credential_id: str | None = None
    credential_url: str | None = None

    @field_validator("credential_url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        return validate_http_url(value)

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        if (
            self.issue_date is not None
            and self.expiration_date is not None
            and self.expiration_date < self.issue_date
        ):
            raise ValueError("expiration_date must be greater than or equal to issue_date")
        return self


class CertificationCreate(CertificationBase, ProvenanceCreate):
    pass


class CertificationUpdate(ProvenanceUpdate):
    name: Name | None = None
    issuing_organization: Name | None = None
    issue_date: date | None = None
    expiration_date: date | None = None
    credential_id: str | None = None
    credential_url: str | None = None

    @field_validator("credential_url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        return validate_http_url(value)

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        if (
            self.issue_date is not None
            and self.expiration_date is not None
            and self.expiration_date < self.issue_date
        ):
            raise ValueError("expiration_date must be greater than or equal to issue_date")
        return self


class CertificationResponse(CertificationBase, ProvenanceResponse):
    id: UUID
    candidate_profile_id: UUID
