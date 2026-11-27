from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import AccountStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.account_action_token import AccountActionToken
    from app.models.auth_session import AuthSession
    from app.models.candidate_profile import CandidateProfile


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Authenticated account independent of candidate profile contact details."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(btrim(email)) > 0", name="email_not_blank"),
        CheckConstraint(
            "status IN ('pending_verification', 'active', 'suspended', 'disabled')",
            name="valid_status",
        ),
        CheckConstraint(
            "(status = 'active' AND is_active = true) "
            "OR (status <> 'active' AND is_active = false)",
            name="status_matches_is_active",
        ),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AccountStatus.ACTIVE.value,
        server_default=text("'active'"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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
    action_tokens: Mapped[list[AccountActionToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None

    def set_status(self, new_status: AccountStatus) -> None:
        """Update canonical account status and keep is_active synchronized."""
        self.status = new_status.value
        self.is_active = new_status == AccountStatus.ACTIVE
