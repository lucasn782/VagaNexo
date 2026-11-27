from __future__ import annotations

import io
import logging
import os
import uuid
from pathlib import Path

import docx
import pymupdf
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.candidate_profile import CandidateProfile
from app.models.enums import ParsingStatus
from app.models.resume_document import ResumeDocument
from app.models.resume_extraction import ResumeExtraction
from app.parsers.pdf_parser import SCANNED_PDF_WARNING
from app.profile.exceptions import InvalidProfileDataError
from app.profile.validators import validate_storage_key
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
    assert db_session.get(ResumeDocument, document.id) is None
    assert (
        db_session.scalar(
            select(ResumeExtraction).where(ResumeExtraction.resume_document_id == document.id)
        )
        is None
    )


def test_storage_rejects_traversal_windows_separators_and_directory_deletion(
    tmp_path: Path,
) -> None:
    storage = ResumeStorage(tmp_path)
    storage.ensure_ready()

    bad_keys = [
        "",
        "../outside.pdf",
        "../../other-profile/file.pdf",
        "/absolute/path/file.pdf",
        r"uploads\profile\file.pdf",
        r"C:\evil\file.pdf",
        "uploads//profile/file.pdf",
        "uploads/./profile/file.pdf",
        "uploads/profile/",
        " uploads/profile/file.pdf",
    ]
    for bad in bad_keys:
        with pytest.raises(StorageError):
            storage.resolve(bad)
        with pytest.raises(StorageError):
            storage.delete_key(bad)
        if bad:
            with pytest.raises(InvalidProfileDataError):
                validate_storage_key(bad)

    # Cannot delete root, upload_root or profile directory
    for non_file_key in ("uploads", f"uploads/{uuid.uuid4()}", f"temporary/{uuid.uuid4()}.part"):
        with pytest.raises(StorageError):
            storage.delete_key(non_file_key)


def test_storage_rejects_symlinks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = ResumeStorage(tmp_path)
    profile_a = uuid.uuid4()
    profile_b = uuid.uuid4()
    doc_a = uuid.uuid4()
    doc_b = uuid.uuid4()

    staged = storage.stage(io.BytesIO(b"%PDF-1.4 target"), max_bytes=1024)
    target_key = storage.commit(staged, profile_id=profile_b, document_id=doc_b, extension=".pdf")
    target_path = storage.resolve(target_key)

    symlink_dir = storage.upload_root / str(profile_a)
    symlink_dir.mkdir(parents=True, exist_ok=True)
    symlink_path = symlink_dir / f"{doc_a}.pdf"
    symlink_key = f"uploads/{profile_a}/{doc_a}.pdf"

    symlink_created = False
    try:
        os.symlink(target_path, symlink_path)
        symlink_created = True
    except (OSError, NotImplementedError):
        symlink_created = False

    if symlink_created:
        with pytest.raises(StorageError):
            storage.resolve(symlink_key)
        with pytest.raises(StorageError):
            storage.delete_key(symlink_key)
        assert target_path.exists()
    else:
        # Fallback when OS denies symlink creation privilege
        monkeypatch.setattr(
            Path,
            "is_symlink",
            lambda self: self.name == f"{doc_a}.pdf",
        )
        with pytest.raises(StorageError):
            storage.resolve(symlink_key)
        with pytest.raises(StorageError):
            storage.delete_key(symlink_key)
        assert target_path.exists()


def test_delete_manual_record_cannot_delete_other_profile_upload_or_extraction(
    db_session: Session,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    profile_a = _create_profile(db_session, "Ana")
    profile_b = _create_profile(db_session, "Bruno")
    storage = ResumeStorage(tmp_path)
    service = ResumeImportService(db_session, storage)

    doc_b, ext_b = service.upload(
        profile_b.id,
        filename="bruno.pdf",
        media_type="application/pdf",
        stream=io.BytesIO(_pdf_bytes("Bruno Secret CV")),
    )
    assert ext_b is not None
    assert ext_b.extracted_storage_key is not None

    # Test A: manual record in profile A pointing to profile B's upload file
    forged_upload_doc = ResumeDocument(
        candidate_profile_id=profile_a.id,
        original_filename="forged.pdf",
        media_type="application/pdf",
        file_size=123,
        sha256_hash="a" * 64,
        storage_key=doc_b.storage_key,
        parsing_status=ParsingStatus.PENDING,
    )
    # Test B: manual/tampered record in profile A pointing to profile B's extracted text
    forged_extracted_doc = ResumeDocument(
        candidate_profile_id=profile_a.id,
        original_filename="forged_ext.pdf",
        media_type="application/pdf",
        file_size=123,
        sha256_hash="b" * 64,
        storage_key=f"uploads/{profile_a.id}/manual-only.pdf",
        parsing_status=ParsingStatus.COMPLETED,
    )
    # Note: uq_resume_documents_storage_key prevents duplicate storage_key, so we
    # simulate a cross-profile extracted_storage_key on forged_extracted_doc
    db_session.add(forged_extracted_doc)
    db_session.flush()
    forged_extraction = ResumeExtraction(
        resume_document_id=forged_extracted_doc.id,
        extracted_text="dummy",
        page_count=1,
        word_count=1,
        character_count=5,
        parser_name="manual",
        parser_version="1.0",
        warnings=[],
        extracted_storage_key=ext_b.extracted_storage_key,
    )
    db_session.add(forged_extraction)
    db_session.commit()

    with caplog.at_level(logging.WARNING):
        service.delete_document(profile_a.id, forged_extracted_doc.id)

    assert db_session.get(ResumeDocument, forged_extracted_doc.id) is None
    assert storage.exists(doc_b.storage_key)
    assert storage.exists(ext_b.extracted_storage_key)
    assert "skipping physical deletion" in caplog.text

    # Also test deleting a document whose storage_key points to another profile's upload
    # (e.g. if unique constraint didn't block or if pointing to an arbitrary file)
    arbitrary_file = storage.upload_root / "manual.pdf"
    arbitrary_file.parent.mkdir(parents=True, exist_ok=True)
    arbitrary_file.write_bytes(b"keep-me")
    forged_upload_doc.storage_key = "uploads/manual.pdf"
    db_session.add(forged_upload_doc)
    db_session.commit()

    service.delete_document(profile_a.id, forged_upload_doc.id)
    assert db_session.get(ResumeDocument, forged_upload_doc.id) is None
    assert arbitrary_file.exists()
