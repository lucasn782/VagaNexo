from __future__ import annotations

import io
import logging
import os
import subprocess
import uuid
from pathlib import Path

import docx
import pymupdf
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.service import AuthService
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


def _create_user_id(session: Session) -> uuid.UUID:
    user = AuthService(session).create_user(
        email=f"user-{uuid.uuid4().hex[:8]}@example.com",
        password="TestPassword123!",
    )
    return user.id


def _create_profile(
    session: Session, name: str = "Ana Souza", *, user_id: uuid.UUID | None = None
) -> CandidateProfile:
    owner_id = user_id if user_id is not None else _create_user_id(session)
    profile = CandidateProfile(full_name=name, user_id=owner_id)
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
    owner_id = _create_user_id(db_session)
    profile_a = _create_profile(db_session, "Ana", user_id=owner_id)
    profile_b = _create_profile(db_session, "Bruno", user_id=owner_id)
    storage = ResumeStorage(tmp_path)
    service = ResumeImportService(db_session, storage, user_id=owner_id)
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
    assert profile.user_id is not None
    storage = ResumeStorage(tmp_path)
    service = ResumeImportService(
        db_session, storage, max_text_characters=10, user_id=profile.user_id
    )

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
    assert profile.user_id is not None
    storage = ResumeStorage(tmp_path)
    service = ResumeImportService(db_session, storage, user_id=profile.user_id)

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
    owner_id = _create_user_id(db_session)
    profile_a = _create_profile(db_session, "Ana", user_id=owner_id)
    profile_b = _create_profile(db_session, "Bruno", user_id=owner_id)
    storage = ResumeStorage(tmp_path)
    service = ResumeImportService(db_session, storage, user_id=owner_id)

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


def _try_symlink(link: Path, target: Path, *, is_dir: bool) -> bool:
    try:
        os.symlink(target, link, target_is_directory=is_dir)
        return True
    except (OSError, NotImplementedError):
        return False


def _try_windows_junction(link: Path, target: Path) -> bool:
    if os.name != "nt":
        return False
    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0 and link.exists()


@pytest.mark.parametrize("dir_name", ["uploads", "extracted", "temporary"])
def test_storage_rejects_symlink_and_broken_symlink_in_main_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dir_name: str,
) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    external_dir = tmp_path / "external_target"
    external_dir.mkdir()
    sentinel = external_dir / "keep.txt"
    sentinel.write_text("do-not-touch", encoding="utf-8")

    link_path = storage_root / dir_name
    if not _try_symlink(link_path, external_dir, is_dir=True):
        link_path.mkdir()
        monkeypatch.setattr(
            Path,
            "is_symlink",
            lambda self: self == link_path,
        )

    storage = ResumeStorage(storage_root)
    with pytest.raises(StorageError):
        storage.ensure_ready()

    if dir_name == "temporary":
        with pytest.raises(StorageError):
            storage.stage(io.BytesIO(b"%PDF-1.4 test"), max_bytes=1024)
    elif dir_name == "extracted":
        with pytest.raises(StorageError):
            storage.write_extracted_text(
                profile_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                text="hello",
            )
    else:
        # uploads as symlink: commit must fail and leave external_dir untouched
        # Create valid temporary and extracted dirs if not monkeypatched
        with pytest.raises(StorageError):
            storage.commit(
                staged=type(
                    "DummyStaged",
                    (),
                    {"path": storage.temp_root / "fake.part"},
                )(),
                profile_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                extension=".pdf",
            )

    assert [p.name for p in external_dir.iterdir()] == ["keep.txt"]
    assert sentinel.read_text(encoding="utf-8") == "do-not-touch"

    # Broken symlink check (Teste F)
    broken_storage_root = tmp_path / f"broken_{dir_name}"
    broken_storage_root.mkdir()
    broken_link = broken_storage_root / dir_name
    missing_target = tmp_path / "does_not_exist"
    if not _try_symlink(broken_link, missing_target, is_dir=True):
        broken_link.mkdir()
        monkeypatch.setattr(
            Path,
            "is_symlink",
            lambda self: self == broken_link,
        )
    broken_storage = ResumeStorage(broken_storage_root)
    with pytest.raises(StorageError):
        broken_storage.ensure_ready()


@pytest.mark.parametrize("dir_name", ["uploads", "extracted", "temporary"])
def test_storage_rejects_windows_junctions_in_main_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dir_name: str,
) -> None:
    storage_root = tmp_path / "j_storage"
    storage_root.mkdir()
    external_dir = tmp_path / "j_external"
    external_dir.mkdir()
    link_path = storage_root / dir_name

    if not _try_windows_junction(link_path, external_dir):
        link_path.mkdir()
        monkeypatch.setattr(
            "app.resume_import.storage._is_link_or_reparse_point",
            lambda p: p == link_path,
        )

    storage = ResumeStorage(storage_root)
    with pytest.raises(StorageError):
        storage.ensure_ready()
    assert list(external_dir.iterdir()) == []


def test_storage_rejects_symlink_in_root_profile_dir_and_regular_file_dirs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    external_dir = tmp_path / "ext"
    external_dir.mkdir()

    # Root itself as symlink/junction
    root_link = tmp_path / "root_link"
    if not _try_windows_junction(root_link, external_dir) and not _try_symlink(
        root_link, external_dir, is_dir=True
    ):
        root_link.mkdir()
        monkeypatch.setattr(
            "app.resume_import.storage._is_link_or_reparse_point",
            lambda p: p == root_link,
        )
    with pytest.raises(StorageError):
        ResumeStorage(root_link)

    # Regular file occupying uploads/
    monkeypatch.undo()
    file_root = tmp_path / "file_root"
    file_root.mkdir()
    (file_root / "uploads").write_text("not a dir", encoding="utf-8")
    with pytest.raises(StorageError):
        ResumeStorage(file_root).ensure_ready()

    # Profile subdirectory as junction/symlink inside uploads/{profile_id}
    clean_root = tmp_path / "clean_root"
    storage = ResumeStorage(clean_root)
    storage.ensure_ready()
    profile_id = uuid.uuid4()
    document_id = uuid.uuid4()
    staged = storage.stage(io.BytesIO(b"%PDF-1.4 payload"), max_bytes=1024)

    profile_dir = storage.upload_root / str(profile_id)
    if not _try_windows_junction(profile_dir, external_dir) and not _try_symlink(
        profile_dir, external_dir, is_dir=True
    ):
        profile_dir.mkdir()
        monkeypatch.setattr(
            "app.resume_import.storage._is_link_or_reparse_point",
            lambda p: p == profile_dir,
        )

    with pytest.raises(StorageError):
        storage.commit(
            staged,
            profile_id=profile_id,
            document_id=document_id,
            extension=".pdf",
        )
    assert list(external_dir.iterdir()) == []
    storage.discard(staged)
    assert list(storage.temp_root.iterdir()) == []


def test_service_upload_leaves_no_orphan_files_when_uploads_or_extracted_is_symlink(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id = _create_user_id(db_session)
    profile = _create_profile(db_session, "Clara", user_id=owner_id)
    storage_root = tmp_path / "svc_storage"
    storage_root.mkdir()
    external_dir = tmp_path / "svc_ext"
    external_dir.mkdir()

    # First, create a legitimate document to ensure existing files are preserved
    storage = ResumeStorage(storage_root)
    service = ResumeImportService(db_session, storage, user_id=owner_id)
    legit_doc, legit_ext = service.upload(
        profile.id,
        filename="legit.pdf",
        media_type="application/pdf",
        stream=io.BytesIO(_pdf_bytes("Legit CV")),
    )
    assert legit_ext is not None and legit_ext.extracted_storage_key is not None

    # Now make extracted/{other_profile} or extracted_root fail during a second upload
    other_profile = _create_profile(db_session, "Diego", user_id=owner_id)
    bad_ext_dir = storage.extracted_root / str(other_profile.id)
    if not _try_windows_junction(bad_ext_dir, external_dir) and not _try_symlink(
        bad_ext_dir, external_dir, is_dir=True
    ):
        bad_ext_dir.mkdir()
        monkeypatch.setattr(
            "app.resume_import.storage._is_link_or_reparse_point",
            lambda p: p == bad_ext_dir,
        )

    with pytest.raises(StorageError):
        service.upload(
            other_profile.id,
            filename="evil.pdf",
            media_type="application/pdf",
            stream=io.BytesIO(_pdf_bytes("Diego CV")),
        )

    # No orphan files in external_dir, temporary/, or other_profile's uploads/
    assert list(external_dir.iterdir()) == []
    assert list(storage.temp_root.iterdir()) == []
    other_upload_dir = storage.upload_root / str(other_profile.id)
    assert not other_upload_dir.exists() or list(other_upload_dir.iterdir()) == []

    # Legitimate existing files remain intact
    assert storage.exists(legit_doc.storage_key)
    assert storage.exists(legit_ext.extracted_storage_key)
