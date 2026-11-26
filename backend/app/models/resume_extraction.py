from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.resume_document import ResumeDocument


class ResumeExtraction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Text extracted from a resume file, always linked to its origin document.

    The binary file never reaches PostgreSQL. The extracted text is stored here
    as the authoritative copy used by the API, and mirrored to the private
    storage directory for later processing stages.
    """

    __tablename__ = "resume_extractions"
    __table_args__ = (
        UniqueConstraint(
            "resume_document_id",
            name="uq_resume_extractions_resume_document_id",
        ),
        CheckConstraint("page_count >= 0", name="page_count_non_negative"),
        CheckConstraint("word_count >= 0", name="word_count_non_negative"),
        CheckConstraint("character_count >= 0", name="character_count_non_negative"),
        Index("ix_resume_extractions_resume_document_id", "resume_document_id"),
    )

    resume_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resume_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    character_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    parser_name: Mapped[str] = mapped_column(String(60), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(40), nullable=False)
    warnings: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    extracted_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)

    resume_document: Mapped[ResumeDocument] = relationship(back_populates="extraction")
