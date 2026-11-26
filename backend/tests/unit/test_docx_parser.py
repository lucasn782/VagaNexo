from __future__ import annotations

import zipfile
from pathlib import Path

import docx
import pytest

from app.parsers.docx_parser import EMPTY_CONTENT_WARNING, DocxResumeParser
from app.resume_import.exceptions import InvalidResumeFileError


def test_docx_parser_extracts_paragraphs_tables_headers_and_unicode(tmp_path: Path) -> None:
    docx_path = tmp_path / "resume.docx"
    document = docx.Document()
    document.sections[0].header.paragraphs[0].text = "Currículo Vitae — João Silva"
    document.add_heading("Experiência Profissional", level=1)
    document.add_paragraph("Engenheiro de Software Sênior em São Paulo.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Tecnologia"
    table.cell(0, 1).text = "Nível"
    table.cell(1, 0).text = "Python"
    table.cell(1, 1).text = "Avançado"
    document.sections[0].footer.paragraphs[0].text = "Página 1"
    document.save(str(docx_path))

    parser = DocxResumeParser()
    result = parser.parse(docx_path)

    assert result.parser_name == "python-docx"
    assert result.warnings == ()
    assert "Experiência Profissional" in result.text
    assert "Engenheiro de Software Sênior em São Paulo." in result.text
    assert "Python | Avançado" in result.text
    assert "Currículo Vitae — João Silva" in result.text
    assert "Página 1" in result.text


def test_docx_parser_flags_empty_document(tmp_path: Path) -> None:
    docx_path = tmp_path / "empty.docx"
    document = docx.Document()
    document.save(str(docx_path))

    parser = DocxResumeParser()
    result = parser.parse(docx_path)

    assert result.text == ""
    assert result.warnings == (EMPTY_CONTENT_WARNING,)


def test_docx_parser_rejects_corrupted_docx(tmp_path: Path) -> None:
    bad_docx = tmp_path / "corrupt.docx"
    with zipfile.ZipFile(bad_docx, "w") as archive:
        archive.writestr("[Content_Types].xml", "<invalid-xml")
        archive.writestr("word/document.xml", "<broken")

    parser = DocxResumeParser()
    with pytest.raises(InvalidResumeFileError):
        parser.parse(bad_docx)
