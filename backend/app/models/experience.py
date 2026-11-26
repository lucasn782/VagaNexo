from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import EmploymentType, sa_enum
from app.models.mixins import ProvenanceMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.candidate_profile import CandidateProfile
    from app.models.resume_document import ResumeDocument


class WorkExperience(UUIDPrimaryKeyMixin, TimestampMixin, ProvenanceMixin, Base):
    """Professional experience. Periods and descriptions are preserved as-is."""

    __tablename__ = "work_experiences"
    __table_args__ = (
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="date_order"),
        CheckConstraint(
            "is_current = false OR end_date IS NULL",
            name="current_requires_open_end",
        ),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="confidence_score_range",
        ),
        Index("ix_work_experiences_candidate_profile_id", "candidate_profile_id"),
    )

    candidate_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    job_title: Mapped[str] = mapped_column(String(200), nullable=False)
    employment_type: Mapped[EmploymentType] = mapped_column(
        sa_enum(EmploymentType, "employment_type"),
        nullable=False,
        default=EmploymentType.FULL_TIME,
        server_default=EmploymentType.FULL_TIME.value,
    )
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    achievements: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    candidate_profile: Mapped[CandidateProfile] = relationship(back_populates="experiences")
    source_document: Mapped[ResumeDocument | None] = relationship(
        "ResumeDocument",
        foreign_keys="WorkExperience.source_document_id",
    )
