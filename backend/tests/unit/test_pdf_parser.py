from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from app.parsers.pdf_parser import SCANNED_PDF_WARNING, PdfResumeParser
from app.parsers.text_normalizer import PAGE_SEPARATOR
from app.resume_import.exceptions import EncryptedResumeError, InvalidResumeFileError


def _make_pdf(path: Path, pages: list[str], *, password: str | None = None) -> Path:
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    if password is not None:
        document.save(
            path,
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw=password,
            user_pw=password,
        )
    else:
        document.save(path)
    document.close()
    return path


def test_pdf_parser_extracts_multipage_text_with_page_breaks(tmp_path: Path) -> None:
    pdf_path = _make_pdf(
        tmp_path / "resume.pdf",
        ["Ana Souza - Backend Engineer", "Experience at Acme Corp - Sao Paulo"],
    )
    parser = PdfResumeParser()
    result = parser.parse(pdf_path)

    assert result.parser_name == "pymupdf"
    assert result.page_count == 2
    assert result.warnings == ()
    assert PAGE_SEPARATOR in result.text
    first_page, second_page = result.text.split(PAGE_SEPARATOR)
    assert "Ana Souza" in first_page
    assert "Acme Corp" in second_page


def test_pdf_parser_flags_scanned_pdf_without_text(tmp_path: Path) -> None:
    pdf_path = _make_pdf(tmp_path / "scanned.pdf", [""])
    parser = PdfResumeParser()
    result = parser.parse(pdf_path)

    assert result.page_count == 1
    assert result.text == ""
    assert result.warnings == (SCANNED_PDF_WARNING,)


def test_pdf_parser_rejects_encrypted_pdf(tmp_path: Path) -> None:
    pdf_path = _make_pdf(tmp_path / "secret.pdf", ["Confidential"], password="secret")
    parser = PdfResumeParser()
    with pytest.raises(EncryptedResumeError):
        parser.parse(pdf_path)


def test_pdf_parser_rejects_corrupted_pdf(tmp_path: Path) -> None:
    bad_pdf = tmp_path / "corrupt.pdf"
    bad_pdf.write_bytes(b"%PDF-1.7\nnot-a-valid-xref-structure")
    parser = PdfResumeParser()
    with pytest.raises(InvalidResumeFileError):
        parser.parse(bad_pdf)
