"""PDF text extraction with PyMuPDF (current ``pymupdf`` import)."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from app.parsers.base import ParsedDocument
from app.parsers.text_normalizer import join_pages, normalize_text
from app.resume_import.exceptions import (
    EncryptedResumeError,
    ExtractionFailedError,
    InvalidResumeFileError,
)

SCANNED_PDF_WARNING = "scanned_pdf_no_text"


class PdfResumeParser:
    name = "pymupdf"
    version = str(getattr(pymupdf, "__version__", "unknown"))

    def parse(self, path: Path) -> ParsedDocument:
        try:
            document = pymupdf.open(path)
        except Exception as exc:  # noqa: BLE001 - library raises several error types
            raise InvalidResumeFileError("file content is not a valid PDF") from exc

        try:
            if document.needs_pass:
                raise EncryptedResumeError("encrypted PDF documents are not supported")
            if not document.is_pdf:
                raise InvalidResumeFileError("file content is not a valid PDF")

            try:
                pages = [
                    normalize_text(document.load_page(index).get_text("text"))
                    for index in range(document.page_count)
                ]
            except Exception as exc:  # noqa: BLE001 - defensive around MuPDF
                raise ExtractionFailedError() from exc

            page_count = document.page_count
        finally:
            document.close()

        text = join_pages(pages)
        warnings = () if text else (SCANNED_PDF_WARNING,)
        return ParsedDocument(
            text=text,
            page_count=page_count,
            parser_name=self.name,
            parser_version=self.version,
            warnings=warnings,
        )
