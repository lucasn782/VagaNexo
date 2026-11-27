from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.auth_session import AuthSession
    from app.models.candidate_profile import CandidateProfile


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Authenticated account independent of candidate profile contact details."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("length(btrim(email)) > 0", name="email_not_blank"),)

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )

    profiles: Mapped[list[CandidateProfile]] = relationship(
        back_populates="user",
        order_by="CandidateProfile.created_at.asc()",
    )
    sessions: Mapped[list[AuthSession]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
