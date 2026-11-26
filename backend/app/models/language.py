from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import (
    CefrLevel,
    LanguageProficiency,
    ProficiencyFramework,
    sa_enum,
)
from app.models.mixins import ProvenanceMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.candidate_profile import CandidateProfile
    from app.models.resume_document import ResumeDocument


class Language(UUIDPrimaryKeyMixin, TimestampMixin, ProvenanceMixin, Base):
    """Spoken language with an optional CEFR level."""

    __tablename__ = "languages"
    __table_args__ = (
        UniqueConstraint(
            "candidate_profile_id",
            "language",
            name="uq_languages_profile_language",
        ),
        CheckConstraint(
            "cefr_level IS NULL OR proficiency_framework = 'cefr'",
            name="cefr_requires_framework",
        ),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="confidence_score_range",
        ),
        Index("ix_languages_candidate_profile_id", "candidate_profile_id"),
    )

    candidate_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    language: Mapped[str] = mapped_column(String(80), nullable=False)
    proficiency_level: Mapped[LanguageProficiency] = mapped_column(
        sa_enum(LanguageProficiency, "language_proficiency"),
        nullable=False,
        default=LanguageProficiency.UNSPECIFIED,
        server_default=LanguageProficiency.UNSPECIFIED.value,
    )
    proficiency_framework: Mapped[ProficiencyFramework | None] = mapped_column(
        sa_enum(ProficiencyFramework, "proficiency_framework", length=16),
        nullable=True,
    )
    cefr_level: Mapped[CefrLevel | None] = mapped_column(
        sa_enum(CefrLevel, "cefr_level", length=2),
        nullable=True,
    )

    candidate_profile: Mapped[CandidateProfile] = relationship(back_populates="languages")
    source_document: Mapped[ResumeDocument | None] = relationship(
        "ResumeDocument",
        foreign_keys="Language.source_document_id",
    )
