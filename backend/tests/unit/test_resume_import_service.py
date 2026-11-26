from __future__ import annotations

import io
import uuid
from pathlib import Path

import docx
import pymupdf
import pytest
from sqlalchemy.orm import Session

from app.models.candidate_profile import CandidateProfile
from app.models.enums import ParsingStatus
from app.parsers.pdf_parser import SCANNED_PDF_WARNING
from app.resume_import.exceptions import (
    DuplicateResumeError,
    InvalidResumeFileError,
    ResumeTooLargeError,
    StorageError,
)
from app.resume_import.hashing import sha256_file
from app.resume_import.service import TRUNCATED_WARNING, ResumeImportService
from app.resume_import.storage import ResumeStorage
from app.resume_import.validators import sanitize_original_filename


def _pdf_bytes(text: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    if text:
        page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def _docx_bytes(text: str) -> bytes:
    buffer = io.BytesIO()
    document = docx.Document()
    document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()


def _create_profile(session: Session, name: str = "Ana Souza") -> CandidateProfile:
    profile = CandidateProfile(full_name=name)
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def test_sanitize_original_filename_strips_directories() -> None:
    assert sanitize_original_filename(r"..\..\secret\curriculo.pdf") == "curriculo.pdf"
    assert sanitize_original_filename("/tmp/evil/cv.docx") == "cv.docx"
    with pytest.raises(InvalidResumeFileError):
        sanitize_original_filename("   ")


def test_storage_prevents_path_traversal_and_uses_uuid_keys(tmp_path: Path) -> None:
    storage = ResumeStorage(tmp_path)
    with pytest.raises(StorageError):
        storage.resolve("../outside.pdf")

    staged = storage.stage(io.BytesIO(b"hello"), max_bytes=1024)
    assert staged.path.parent == storage.temp_root
    profile_id = uuid.uuid4()
    document_id = uuid.uuid4()
    key = storage.commit(staged, profile_id=profile_id, document_id=document_id, extension=".pdf")
    assert key == f"uploads/{profile_id}/{document_id}.pdf"
    assert storage.exists(key)
    assert list(storage.temp_root.iterdir()) == []


def test_storage_cleans_temp_files_when_upload_exceeds_limit(tmp_path: Path) -> None:
    storage = ResumeStorage(tmp_path)
    with pytest.raises(ResumeTooLargeError):
        storage.stage(io.BytesIO(b"x" * 2048), max_bytes=1024)
    assert list(storage.temp_root.iterdir()) == []


def test_service_upload_deduplicates_within_profile_and_allows_other_profile(
    db_session: Session,
    tmp_path: Path,
) -> None:
    profile_a = _create_profile(db_session, "Ana")
    profile_b = _create_profile(db_session, "Bruno")
    storage = ResumeStorage(tmp_path)
    service = ResumeImportService(db_session, storage)
    payload = _pdf_bytes("Ana Souza - Python Engineer")

    doc_a, ext_a = service.upload(
        profile_a.id,
        filename="../../ana_cv.pdf",
        media_type="application/pdf",
        stream=io.BytesIO(payload),
    )
    assert doc_a.original_filename == "ana_cv.pdf"
    assert doc_a.parsing_status is ParsingStatus.COMPLETED
    assert ext_a is not None
    assert ext_a.extracted_storage_key is not None
    assert storage.exists(doc_a.storage_key)
    assert storage.exists(ext_a.extracted_storage_key)
    assert doc_a.sha256_hash == sha256_file(storage.resolve(doc_a.storage_key))

    with pytest.raises(DuplicateResumeError):
        service.upload(
            profile_a.id,
            filename="copy.pdf",
            media_type="application/pdf",
            stream=io.BytesIO(payload),
        )

    doc_b, _ = service.upload(
        profile_b.id,
        filename="bruno.pdf",
        media_type="application/pdf",
        stream=io.BytesIO(payload),
    )
    assert doc_b.id != doc_a.id
    assert doc_b.sha256_hash == doc_a.sha256_hash


def test_service_scanned_pdf_and_truncation_warnings(
    db_session: Session,
    tmp_path: Path,
) -> None:
    profile = _create_profile(db_session)
    storage = ResumeStorage(tmp_path)
    service = ResumeImportService(db_session, storage, max_text_characters=10)

    scanned_doc, scanned_ext = service.upload(
        profile.id,
        filename="scan.pdf",
        media_type="application/pdf",
        stream=io.BytesIO(_pdf_bytes("")),
    )
    assert scanned_doc.parsing_status is ParsingStatus.COMPLETED_WITH_WARNINGS
    assert scanned_ext is not None
    assert scanned_ext.warnings == [SCANNED_PDF_WARNING]

    long_doc, long_ext = service.upload(
        profile.id,
        filename="long.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        stream=io.BytesIO(_docx_bytes("ABCDEFGHIJKLMNOPQRSTUVWXYZ")),
    )
    assert long_doc.parsing_status is ParsingStatus.COMPLETED_WITH_WARNINGS
    assert long_ext is not None
    assert len(long_ext.extracted_text) == 10
    assert TRUNCATED_WARNING in long_ext.warnings


def test_service_delete_removes_db_and_physical_files(
    db_session: Session,
    tmp_path: Path,
) -> None:
    profile = _create_profile(db_session)
    storage = ResumeStorage(tmp_path)
    service = ResumeImportService(db_session, storage)

    document, extraction = service.upload(
        profile.id,
        filename="cv.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        stream=io.BytesIO(_docx_bytes("Backend Engineer")),
    )
    assert extraction is not None
    upload_key = document.storage_key
    extracted_key = extraction.extracted_storage_key
    assert extracted_key is not None

    service.delete_document(profile.id, document.id)
    assert not storage.exists(upload_key)
    assert not storage.exists(extracted_key)
