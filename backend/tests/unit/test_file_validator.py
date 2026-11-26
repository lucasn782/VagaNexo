from __future__ import annotations

import zipfile
from pathlib import Path

import docx
import pymupdf
import pytest

from app.parsers.base import ResumeFileKind
from app.parsers.file_validator import validate_resume_file
from app.resume_import.exceptions import EncryptedResumeError, InvalidResumeFileError


def _write_valid_pdf(path: Path, *, password: str | None = None) -> Path:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Sample Resume")
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


def _write_valid_docx(path: Path) -> Path:
    document = docx.Document()
    document.add_paragraph("Sample Resume")
    document.save(str(path))
    return path


def test_validate_accepts_valid_pdf_and_docx(tmp_path: Path) -> None:
    pdf_path = _write_valid_pdf(tmp_path / "cv.pdf")
    docx_path = _write_valid_docx(tmp_path / "cv.docx")

    pdf_result = validate_resume_file(
        filename="cv.pdf",
        declared_media_type="application/pdf",
        path=pdf_path,
        max_archive_entries=2000,
        max_uncompressed_bytes=50_000_000,
    )
    assert pdf_result.kind is ResumeFileKind.PDF
    assert pdf_result.media_type == "application/pdf"
    assert pdf_result.extension == ".pdf"

    docx_result = validate_resume_file(
        filename="cv.docx",
        declared_media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        path=docx_path,
        max_archive_entries=2000,
        max_uncompressed_bytes=50_000_000,
    )
    assert docx_result.kind is ResumeFileKind.DOCX
    assert docx_result.extension == ".docx"


def test_validate_rejects_empty_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    with pytest.raises(InvalidResumeFileError, match="empty"):
        validate_resume_file(
            filename="empty.pdf",
            declared_media_type="application/pdf",
            path=empty,
            max_archive_entries=2000,
            max_uncompressed_bytes=50_000_000,
        )


def test_validate_rejects_disallowed_extension_and_mismatched_mime(tmp_path: Path) -> None:
    txt = tmp_path / "notes.txt"
    txt.write_text("hello", encoding="utf-8")
    with pytest.raises(InvalidResumeFileError):
        validate_resume_file(
            filename="notes.txt",
            declared_media_type="text/plain",
            path=txt,
            max_archive_entries=2000,
            max_uncompressed_bytes=50_000_000,
        )

    pdf_path = _write_valid_pdf(tmp_path / "cv.pdf")
    with pytest.raises(InvalidResumeFileError, match="media type"):
        validate_resume_file(
            filename="cv.pdf",
            declared_media_type="image/png",
            path=pdf_path,
            max_archive_entries=2000,
            max_uncompressed_bytes=50_000_000,
        )


def test_validate_rejects_spoofed_pdf_and_invalid_zip(tmp_path: Path) -> None:
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_text("not a pdf", encoding="utf-8")
    with pytest.raises(InvalidResumeFileError):
        validate_resume_file(
            filename="fake.pdf",
            declared_media_type="application/pdf",
            path=fake_pdf,
            max_archive_entries=2000,
            max_uncompressed_bytes=50_000_000,
        )

    fake_docx = tmp_path / "fake.docx"
    fake_docx.write_bytes(b"PK\x03\x04corrupted-zip-body")
    with pytest.raises(InvalidResumeFileError):
        validate_resume_file(
            filename="fake.docx",
            declared_media_type="application/zip",
            path=fake_docx,
            max_archive_entries=2000,
            max_uncompressed_bytes=50_000_000,
        )


def test_validate_rejects_encrypted_pdf(tmp_path: Path) -> None:
    encrypted = _write_valid_pdf(tmp_path / "locked.pdf", password="123")
    with pytest.raises(EncryptedResumeError):
        validate_resume_file(
            filename="locked.pdf",
            declared_media_type="application/pdf",
            path=encrypted,
            max_archive_entries=2000,
            max_uncompressed_bytes=50_000_000,
        )


def test_validate_rejects_suspicious_docx_zip(tmp_path: Path) -> None:
    missing_parts = tmp_path / "missing.docx"
    with zipfile.ZipFile(missing_parts, "w") as archive:
        archive.writestr("random.txt", "hello")
    with pytest.raises(InvalidResumeFileError, match="missing required"):
        validate_resume_file(
            filename="missing.docx",
            declared_media_type="application/zip",
            path=missing_parts,
            max_archive_entries=2000,
            max_uncompressed_bytes=50_000_000,
        )

    traversal = tmp_path / "traversal.docx"
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<doc/>")
        archive.writestr("../../evil.txt", "boom")
    with pytest.raises(InvalidResumeFileError, match="unsafe path"):
        validate_resume_file(
            filename="traversal.docx",
            declared_media_type="application/zip",
            path=traversal,
            max_archive_entries=2000,
            max_uncompressed_bytes=50_000_000,
        )

    bomb = tmp_path / "bomb.docx"
    with zipfile.ZipFile(bomb, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "A" * 50_000)
    with pytest.raises(InvalidResumeFileError, match="allowed size"):
        validate_resume_file(
            filename="bomb.docx",
            declared_media_type="application/zip",
            path=bomb,
            max_archive_entries=2000,
            max_uncompressed_bytes=10_000,
        )

    too_many = tmp_path / "many.docx"
    with zipfile.ZipFile(too_many, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<doc/>")
        for idx in range(5):
            archive.writestr(f"extra_{idx}.txt", "x")
    with pytest.raises(InvalidResumeFileError, match="too many entries"):
        validate_resume_file(
            filename="many.docx",
            declared_media_type="application/zip",
            path=too_many,
            max_archive_entries=4,
            max_uncompressed_bytes=50_000_000,
        )
