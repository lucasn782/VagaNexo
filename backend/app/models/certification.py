from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import ProvenanceMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.candidate_profile import CandidateProfile
    from app.models.resume_document import ResumeDocument


class Certification(UUIDPrimaryKeyMixin, TimestampMixin, ProvenanceMixin, Base):
    """Certification or structured course credential.

    Free courses must not be confused with professional certifications; the
    issuing organization and credential identifiers are kept to allow auditing.
    """

    __tablename__ = "certifications"
    __table_args__ = (
        CheckConstraint(
            "expiration_date IS NULL OR issue_date IS NULL OR expiration_date >= issue_date",
            name="date_order",
        ),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="confidence_score_range",
        ),
        Index("ix_certifications_candidate_profile_id", "candidate_profile_id"),
    )

    candidate_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    issuing_organization: Mapped[str] = mapped_column(String(200), nullable=False)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    credential_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    credential_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    candidate_profile: Mapped[CandidateProfile] = relationship(back_populates="certifications")
    source_document: Mapped[ResumeDocument | None] = relationship(
        "ResumeDocument",
        foreign_keys="Certification.source_document_id",
    )
