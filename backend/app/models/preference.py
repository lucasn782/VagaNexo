from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import SeniorityLevel, sa_enum
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.candidate_profile import CandidateProfile


class JobPreferences(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Job search preferences. One row per candidate profile.

    Lists are stored as JSONB so new work modes or employment types can be
    added without changing the central profile model.
    """

    __tablename__ = "job_preferences"
    __table_args__ = (
        UniqueConstraint(
            "candidate_profile_id",
            name="uq_job_preferences_profile",
        ),
        CheckConstraint(
            "minimum_salary IS NULL OR minimum_salary >= 0",
            name="minimum_salary_non_negative",
        ),
        CheckConstraint(
            "maximum_salary IS NULL OR maximum_salary >= 0",
            name="maximum_salary_non_negative",
        ),
        CheckConstraint(
            "minimum_salary IS NULL OR maximum_salary IS NULL OR minimum_salary <= maximum_salary",
            name="salary_range",
        ),
        Index("ix_job_preferences_candidate_profile_id", "candidate_profile_id"),
    )

    candidate_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    preferred_job_titles: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    preferred_locations: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    work_modes: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    employment_types: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    minimum_salary: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    maximum_salary: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    willingness_to_relocate: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default="false",
    )
    preferred_seniority: Mapped[SeniorityLevel | None] = mapped_column(
        sa_enum(SeniorityLevel, "seniority_level", length=16),
        nullable=True,
    )

    candidate_profile: Mapped[CandidateProfile] = relationship(back_populates="preferences")
