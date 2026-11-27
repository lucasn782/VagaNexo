from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import ParsingStatus, sa_enum
from app.models.mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.candidate_profile import CandidateProfile
    from app.models.resume_extraction import ResumeExtraction


class ResumeDocument(UUIDPrimaryKeyMixin, Base):
    """Metadata of an imported resume file.

    Only metadata is stored in PostgreSQL. The binary content belongs to the
    filesystem storage and is never persisted in the database.
    """

    __tablename__ = "resume_documents"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_resume_documents_storage_key"),
        UniqueConstraint(
            "candidate_profile_id",
            "sha256_hash",
            name="uq_resume_documents_profile_sha256",
        ),
        CheckConstraint("file_size >= 0", name="file_size_non_negative"),
        CheckConstraint(
            "sha256_hash ~ '^[0-9a-f]{64}$'",
            name="sha256_format",
        ),
        CheckConstraint("length(btrim(original_filename)) > 0", name="filename_not_blank"),
        Index("ix_resume_documents_candidate_profile_id", "candidate_profile_id"),
    )

    candidate_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    parsing_status: Mapped[ParsingStatus] = mapped_column(
        sa_enum(ParsingStatus, "parsing_status", length=32),
        nullable=False,
        default=ParsingStatus.PENDING,
        server_default=ParsingStatus.PENDING.value,
    )
    failure_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    candidate_profile: Mapped[CandidateProfile] = relationship(back_populates="resume_documents")
    extraction: Mapped[ResumeExtraction | None] = relationship(
        back_populates="resume_document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
