from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import ProjectType, sa_enum
from app.models.mixins import ProvenanceMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.candidate_profile import CandidateProfile
    from app.models.resume_document import ResumeDocument


class Project(UUIDPrimaryKeyMixin, TimestampMixin, ProvenanceMixin, Base):
    """Personal, academic, open-source or professional project."""

    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="date_order"),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="confidence_score_range",
        ),
        Index("ix_projects_candidate_profile_id", "candidate_profile_id"),
    )

    candidate_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str | None] = mapped_column(String(200), nullable=True)
    project_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    technologies: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    project_type: Mapped[ProjectType] = mapped_column(
        sa_enum(ProjectType, "project_type", length=16),
        nullable=False,
        default=ProjectType.OTHER,
        server_default=ProjectType.OTHER.value,
    )

    candidate_profile: Mapped[CandidateProfile] = relationship(back_populates="projects")
    source_document: Mapped[ResumeDocument | None] = relationship(
        "ResumeDocument",
        foreign_keys="Project.source_document_id",
    )
