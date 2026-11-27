"""Validation rules shared by the Profile Engine service layer."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal

from app.models.enums import (
    CefrLevel,
    ProficiencyFramework,
    SourceType,
    ValidationStatus,
)
from app.profile.exceptions import InvalidProfileDataError

_WHITESPACE = re.compile(r"\s+")


def normalize_skill_name(name: str) -> str:
    """Return a stable comparison key for a skill name.

    Accents, case and repeated whitespace are removed so that "Comunicação"
    and "comunicacao" are treated as the same competence.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _WHITESPACE.sub(" ", without_accents).strip().casefold()


def validate_period(
    start_date: date | None,
    end_date: date | None,
    is_current: bool | None,
    *,
    label: str = "end_date",
) -> None:
    if start_date is not None and end_date is not None and end_date < start_date:
        raise InvalidProfileDataError(f"{label} must be greater than or equal to start_date")
    if is_current and end_date is not None:
        raise InvalidProfileDataError("end_date must be empty when is_current is true")


def validate_certification_dates(issue_date: date | None, expiration_date: date | None) -> None:
    if issue_date is not None and expiration_date is not None and expiration_date < issue_date:
        raise InvalidProfileDataError("expiration_date must be greater than or equal to issue_date")


def validate_salary_range(
    minimum: float | Decimal | None,
    maximum: float | Decimal | None,
) -> None:
    if minimum is not None and minimum < 0:
        raise InvalidProfileDataError("minimum_salary must be greater than or equal to 0")
    if maximum is not None and maximum < 0:
        raise InvalidProfileDataError("maximum_salary must be greater than or equal to 0")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise InvalidProfileDataError(
            "minimum_salary must be lower than or equal to maximum_salary"
        )


def validate_years_experience(value: float | Decimal | None) -> None:
    if value is not None and not 0 <= value <= 80:
        raise InvalidProfileDataError("years_experience must be between 0 and 80")


def validate_language_profile(
    proficiency_framework: ProficiencyFramework | None,
    cefr_level: CefrLevel | None,
) -> None:
    if cefr_level is not None and proficiency_framework != ProficiencyFramework.CEFR:
        raise InvalidProfileDataError("cefr_level requires proficiency_framework='cefr'")


def resolve_validation_status(
    source_type: SourceType,
    requested: ValidationStatus | None,
) -> ValidationStatus:
    """Apply the provenance rules for a new record.

    Manual records may be confirmed by the user. Document and AI records always
    start as pending and can only be confirmed through the explicit validation
    endpoints.
    """
    if source_type in (SourceType.DOCUMENT, SourceType.AI):
        if requested not in (None, ValidationStatus.PENDING):
            raise InvalidProfileDataError(
                "document and ai records must start with validation_status 'pending'"
            )
        return ValidationStatus.PENDING
    return requested if requested is not None else ValidationStatus.CONFIRMED


def validate_storage_key(storage_key: str) -> None:
    if (
        not storage_key
        or storage_key.strip() != storage_key
        or "\x00" in storage_key
        or "\\" in storage_key
        or ":" in storage_key
        or storage_key.startswith("/")
        or storage_key.endswith("/")
    ):
        raise InvalidProfileDataError("storage_key must be a relative path without traversal")
    parts = storage_key.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise InvalidProfileDataError("storage_key must be a relative path without traversal")
