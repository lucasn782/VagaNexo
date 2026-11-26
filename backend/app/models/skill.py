from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import ProficiencyLevel, SkillCategory, sa_enum
from app.models.mixins import ProvenanceMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.candidate_profile import CandidateProfile
    from app.models.resume_document import ResumeDocument


class Skill(UUIDPrimaryKeyMixin, TimestampMixin, ProvenanceMixin, Base):
    """Technical or behavioral competence owned by a candidate profile."""

    __tablename__ = "skills"
    __table_args__ = (
        UniqueConstraint(
            "candidate_profile_id",
            "normalized_name",
            name="uq_skills_profile_normalized_name",
        ),
        CheckConstraint(
            "years_experience IS NULL OR (years_experience >= 0 AND years_experience <= 80)",
            name="years_experience_range",
        ),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="confidence_score_range",
        ),
        Index("ix_skills_candidate_profile_id", "candidate_profile_id"),
        Index("ix_skills_normalized_name", "normalized_name"),
    )

    candidate_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[SkillCategory] = mapped_column(
        sa_enum(SkillCategory, "skill_category"),
        nullable=False,
        default=SkillCategory.OTHER,
        server_default=SkillCategory.OTHER.value,
    )
    proficiency_level: Mapped[ProficiencyLevel] = mapped_column(
        sa_enum(ProficiencyLevel, "proficiency_level"),
        nullable=False,
        default=ProficiencyLevel.UNSPECIFIED,
        server_default=ProficiencyLevel.UNSPECIFIED.value,
    )
    years_experience: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    last_used: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    candidate_profile: Mapped[CandidateProfile] = relationship(back_populates="skills")
    source_document: Mapped[ResumeDocument | None] = relationship(
        "ResumeDocument",
        foreign_keys="Skill.source_document_id",
    )
