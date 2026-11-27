from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, SmallInteger, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import EmailOutboxStatus
from app.models.mixins import UUIDPrimaryKeyMixin


class EmailOutbox(UUIDPrimaryKeyMixin, Base):
    """Transactional email outbox with AEAD-encrypted temporary payload."""

    __tablename__ = "email_outbox"
    __table_args__ = (
        Index("ix_email_outbox_status_available_at", "status", "available_at"),
        Index("ix_email_outbox_lock_expires_at", "lock_expires_at"),
        Index("ix_email_outbox_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    template_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=EmailOutboxStatus.PENDING.value,
        server_default=text("'pending'"),
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    claim_token: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    lock_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    encrypted_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_key_version: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
