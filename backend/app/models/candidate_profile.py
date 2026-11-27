from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.certification import Certification
    from app.models.education import Education
    from app.models.experience import WorkExperience
    from app.models.language import Language
    from app.models.preference import JobPreferences
    from app.models.project import Project
    from app.models.resume_document import ResumeDocument
    from app.models.skill import Skill
    from app.models.user import User


class CandidateProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Professional identity of the candidate.

    Only data required by the product is stored. Sensitive personal
    information that is not needed to generate resumes is intentionally absent.
    """

    __tablename__ = "candidate_profiles"
    __table_args__ = (
        CheckConstraint("length(btrim(full_name)) > 0", name="full_name_not_blank"),
        Index("ix_candidate_profiles_full_name", "full_name"),
        Index("ix_candidate_profiles_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    professional_headline: Mapped[str | None] = mapped_column(String(200), nullable=True)
    professional_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    github_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    portfolio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    user: Mapped[User | None] = relationship(back_populates="profiles")
    educations: Mapped[list[Education]] = relationship(
        back_populates="candidate_profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Education.start_date.desc()",
    )
    experiences: Mapped[list[WorkExperience]] = relationship(
        back_populates="candidate_profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="WorkExperience.start_date.desc()",
    )
    skills: Mapped[list[Skill]] = relationship(
        back_populates="candidate_profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Skill.name",
    )
    certifications: Mapped[list[Certification]] = relationship(
        back_populates="candidate_profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Certification.issue_date.desc()",
    )
    languages: Mapped[list[Language]] = relationship(
        back_populates="candidate_profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Language.language",
    )
    projects: Mapped[list[Project]] = relationship(
        back_populates="candidate_profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Project.start_date.desc()",
    )
    preferences: Mapped[JobPreferences | None] = relationship(
        back_populates="candidate_profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    resume_documents: Mapped[list[ResumeDocument]] = relationship(
        back_populates="candidate_profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ResumeDocument.uploaded_at.desc()",
    )
