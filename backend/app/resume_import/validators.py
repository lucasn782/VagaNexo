"""Validation helpers for imported resumes."""

from __future__ import annotations

import unicodedata
from pathlib import PurePosixPath

from app.resume_import.exceptions import InvalidResumeFileError

MAX_FILENAME_LENGTH = 255


def sanitize_original_filename(filename: str | None) -> str:
    """Return a safe display name without directory components."""
    normalized = unicodedata.normalize("NFC", (filename or "").replace("\\", "/"))
    name = PurePosixPath(normalized).name.strip()
    name = "".join(character for character in name if character.isprintable())
    if not name:
        raise InvalidResumeFileError("file name is required")
    if len(name) > MAX_FILENAME_LENGTH:
        raise InvalidResumeFileError("file name is too long")
    return name
