from __future__ import annotations

from typing import Self
from uuid import UUID

from pydantic import model_validator

from app.models.enums import CefrLevel, LanguageProficiency, ProficiencyFramework
from app.schemas.common import (
    APIModel,
    ProvenanceCreate,
    ProvenanceResponse,
    ProvenanceUpdate,
    ShortLabel,
)


class LanguageBase(APIModel):
    language: ShortLabel
    proficiency_level: LanguageProficiency = LanguageProficiency.UNSPECIFIED
    proficiency_framework: ProficiencyFramework | None = None
    cefr_level: CefrLevel | None = None

    @model_validator(mode="after")
    def _check_cefr(self) -> Self:
        if self.cefr_level is not None and self.proficiency_framework != ProficiencyFramework.CEFR:
            raise ValueError("cefr_level requires proficiency_framework='cefr'")
        return self


class LanguageCreate(LanguageBase, ProvenanceCreate):
    pass


class LanguageUpdate(ProvenanceUpdate):
    language: ShortLabel | None = None
    proficiency_level: LanguageProficiency | None = None
    proficiency_framework: ProficiencyFramework | None = None
    cefr_level: CefrLevel | None = None

    @model_validator(mode="after")
    def _check_cefr(self) -> Self:
        if self.cefr_level is not None and self.proficiency_framework != ProficiencyFramework.CEFR:
            raise ValueError("cefr_level requires proficiency_framework='cefr'")
        return self


class LanguageResponse(LanguageBase, ProvenanceResponse):
    id: UUID
    candidate_profile_id: UUID
