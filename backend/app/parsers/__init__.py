"""Resume text parsers and the parser registry used by the importer."""

from __future__ import annotations

from app.parsers.base import ParsedDocument, ResumeFileKind, ResumeParser
from app.parsers.docx_parser import DocxResumeParser
from app.parsers.pdf_parser import PdfResumeParser

PARSERS: dict[ResumeFileKind, ResumeParser] = {
    ResumeFileKind.PDF: PdfResumeParser(),
    ResumeFileKind.DOCX: DocxResumeParser(),
}

__all__ = [
    "PARSERS",
    "DocxResumeParser",
    "ParsedDocument",
    "PdfResumeParser",
    "ResumeFileKind",
    "ResumeParser",
]
