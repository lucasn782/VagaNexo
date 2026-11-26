"""DOCX text extraction with python-docx.

Paragraphs, headings, tables, headers and footers are read in document order.
The original file is never modified.
"""

from __future__ import annotations

from pathlib import Path

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.parsers.base import ParsedDocument
from app.parsers.text_normalizer import normalize_inline, normalize_text
from app.resume_import.exceptions import ExtractionFailedError, InvalidResumeFileError

EMPTY_CONTENT_WARNING = "empty_extracted_content"


class DocxResumeParser:
    name = "python-docx"
    version = str(getattr(docx, "__version__", "unknown"))

    def parse(self, path: Path) -> ParsedDocument:
        try:
            document = docx.Document(str(path))
        except Exception as exc:  # noqa: BLE001 - python-docx raises several error types
            raise InvalidResumeFileError("file content is not a valid DOCX document") from exc

        try:
            blocks: list[str] = []
            for block in document.iter_inner_content():
                if isinstance(block, Paragraph):
                    text = normalize_inline(block.text)
                    if text:
                        blocks.append(text)
                elif isinstance(block, Table):
                    blocks.extend(self._table_lines(block))

            for section in document.sections:
                for container in (section.header, section.footer):
                    for paragraph in container.paragraphs:
                        text = normalize_inline(paragraph.text)
                        if text:
                            blocks.append(text)
        except Exception as exc:  # noqa: BLE001 - defensive around python-docx
            raise ExtractionFailedError() from exc

        text = normalize_text("\n".join(blocks))
        warnings = () if text else (EMPTY_CONTENT_WARNING,)
        return ParsedDocument(
            text=text,
            page_count=0,
            parser_name=self.name,
            parser_version=self.version,
            warnings=warnings,
        )

    @staticmethod
    def _table_lines(table: Table) -> list[str]:
        lines: list[str] = []
        for row in table.rows:
            cells = [normalize_inline(cell.text) for cell in row.cells]
            line = " | ".join(cell for cell in cells if cell)
            if line:
                lines.append(line)
        return lines
