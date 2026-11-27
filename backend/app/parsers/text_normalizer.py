"""Text normalization for extracted resumes.

The goal is to make the text stable for later AI processing without rewriting
its meaning: accents, Unicode characters and professional content are kept.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

# Keep tab, newline and form feed (page separator); drop other control bytes.
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f]")
_INLINE_SPACES = re.compile(r"[^\S\n\f]+")
_TRAILING_SPACES = re.compile(r"[ \t]+\n")
_EXCESS_NEWLINES = re.compile(r"\n{3,}")

PAGE_SEPARATOR = "\f"


def normalize_text(text: str) -> str:
    """Normalize line breaks and whitespace while preserving the content."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _CONTROL_CHARACTERS.sub("", normalized)
    normalized = _INLINE_SPACES.sub(" ", normalized)
    normalized = _TRAILING_SPACES.sub("\n", normalized)
    normalized = _EXCESS_NEWLINES.sub("\n\n", normalized)
    return normalized.strip()


def normalize_inline(text: str) -> str:
    """Normalize a single paragraph or table cell without keeping line breaks."""
    return " ".join(normalize_text(text).split())


def join_pages(pages: Sequence[str]) -> str:
    """Join page texts with a form feed so page boundaries survive."""
    cleaned = [normalize_text(page) for page in pages]
    return PAGE_SEPARATOR.join(page for page in cleaned if page)


def count_words(text: str) -> int:
    return len(text.split())


def count_characters(text: str) -> int:
    return len(text)
