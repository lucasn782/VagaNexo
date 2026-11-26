"""Parser contracts shared by the PDF and DOCX implementations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class ResumeFileKind(StrEnum):
    PDF = "pdf"
    DOCX = "docx"


@dataclass(frozen=True)
class ParsedDocument:
    """Result of extracting a resume without interpreting its content."""

    text: str
    page_count: int
    parser_name: str
    parser_version: str
    warnings: tuple[str, ...] = ()


class ResumeParser(Protocol):
    def parse(self, path: Path) -> ParsedDocument: ...
