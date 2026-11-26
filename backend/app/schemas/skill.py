from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import Field

from app.models.enums import ProficiencyLevel, SkillCategory
from app.schemas.common import (
    APIModel,
    LongText,
    Name,
    ProvenanceCreate,
    ProvenanceResponse,
    ProvenanceUpdate,
)


class SkillBase(APIModel):
    name: Name
    category: SkillCategory = SkillCategory.OTHER
    proficiency_level: ProficiencyLevel = ProficiencyLevel.UNSPECIFIED
    years_experience: float | None = Field(default=None, ge=0, le=80)
    last_used: date | None = None
    description: LongText | None = None


class SkillCreate(SkillBase, ProvenanceCreate):
    pass


class SkillUpdate(ProvenanceUpdate):
    name: Name | None = None
    category: SkillCategory | None = None
    proficiency_level: ProficiencyLevel | None = None
    years_experience: float | None = Field(default=None, ge=0, le=80)
    last_used: date | None = None
    description: LongText | None = None


class SkillResponse(SkillBase, ProvenanceResponse):
    id: UUID
    candidate_profile_id: UUID
    normalized_name: str
