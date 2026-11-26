from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import SourceType, ValidationStatus, sa_enum


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ProvenanceMixin:
    """Traceability shared by every professional fact stored in the profile.

    The origin of the information and the confirmation state are persisted so
    that imported or AI-suggested data never becomes a confirmed fact without
    an explicit user action.
    """

    source_type: Mapped[SourceType] = mapped_column(
        sa_enum(SourceType, "source_type", length=16),
        nullable=False,
        default=SourceType.MANUAL,
        server_default=SourceType.MANUAL.value,
    )
    validation_status: Mapped[ValidationStatus] = mapped_column(
        sa_enum(ValidationStatus, "validation_status", length=16),
        nullable=False,
        default=ValidationStatus.PENDING,
        server_default=ValidationStatus.PENDING.value,
    )
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resume_documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    confidence_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        info={"description": "Confidence between 0 and 1 when the fact was extracted."},
    )
