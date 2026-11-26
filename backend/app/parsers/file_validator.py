"""Binary validation for uploaded resumes.

The client-provided extension and media type are never trusted on their own.
Every file is inspected by content before it is stored or parsed.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import pymupdf

from app.parsers.base import ResumeFileKind
from app.resume_import.exceptions import EncryptedResumeError, InvalidResumeFileError

PDF_MAGIC = b"%PDF-"
ZIP_MAGICS = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
DOCX_REQUIRED_ENTRIES = frozenset({"[Content_Types].xml", "word/document.xml"})
HEADER_SIZE = 1024

CANONICAL_MEDIA_TYPE = {
    ResumeFileKind.PDF: "application/pdf",
    ResumeFileKind.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

ALLOWED_MEDIA_TYPES = {
    ResumeFileKind.PDF: {
        "application/pdf",
        "application/x-pdf",
        "application/octet-stream",
        "binary/octet-stream",
    },
    ResumeFileKind.DOCX: {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
        "binary/octet-stream",
    },
}

EXTENSIONS = {
    ".pdf": ResumeFileKind.PDF,
    ".docx": ResumeFileKind.DOCX,
}


@dataclass(frozen=True)
class ValidatedUpload:
    kind: ResumeFileKind
    media_type: str
    extension: str


def normalize_media_type(value: str | None) -> str:
    if not value:
        return ""
    return value.split(";", 1)[0].strip().lower()


def detect_extension(filename: str) -> tuple[ResumeFileKind, str]:
    suffix = Path(filename or "").suffix.lower()
    kind = EXTENSIONS.get(suffix)
    if kind is None:
        raise InvalidResumeFileError("only PDF and DOCX files are accepted")
    return kind, suffix


def validate_resume_file(
    *,
    filename: str,
    declared_media_type: str | None,
    path: Path,
    max_archive_entries: int,
    max_uncompressed_bytes: int,
) -> ValidatedUpload:
    """Validate extension, declared media type and binary structure."""
    kind, suffix = detect_extension(filename)

    media_type = normalize_media_type(declared_media_type)
    if media_type and media_type not in ALLOWED_MEDIA_TYPES[kind]:
        raise InvalidResumeFileError("declared media type does not match the file extension")

    size = path.stat().st_size
    if size <= 0:
        raise InvalidResumeFileError("file is empty")

    if kind is ResumeFileKind.PDF:
        _validate_pdf(path)
    else:
        _validate_docx(
            path,
            max_archive_entries=max_archive_entries,
            max_uncompressed_bytes=max_uncompressed_bytes,
        )

    return ValidatedUpload(kind=kind, media_type=CANONICAL_MEDIA_TYPE[kind], extension=suffix)


def _validate_pdf(path: Path) -> None:
    with path.open("rb") as handle:
        header = handle.read(HEADER_SIZE)
    if PDF_MAGIC not in header:
        raise InvalidResumeFileError("file content is not a valid PDF")

    try:
        document = pymupdf.open(path)
    except Exception as exc:  # noqa: BLE001 - library raises several error types
        raise InvalidResumeFileError("file content is not a valid PDF") from exc

    try:
        if document.needs_pass:
            raise EncryptedResumeError("encrypted PDF documents are not supported")
        if not document.is_pdf:
            raise InvalidResumeFileError("file content is not a valid PDF")
        if document.page_count < 1:
            raise InvalidResumeFileError("PDF document has no pages")
    finally:
        document.close()


def _validate_docx(
    path: Path,
    *,
    max_archive_entries: int,
    max_uncompressed_bytes: int,
) -> None:
    with path.open("rb") as handle:
        header = handle.read(8)
    if not header.startswith(ZIP_MAGICS):
        raise InvalidResumeFileError("file content is not a valid DOCX document")

    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > max_archive_entries:
                raise InvalidResumeFileError("DOCX archive contains too many entries")

            uncompressed = sum(entry.file_size for entry in entries)
            if uncompressed > max_uncompressed_bytes:
                raise InvalidResumeFileError("DOCX archive expands beyond the allowed size")

            names = set()
            for entry in entries:
                name = entry.filename
                if name.startswith(("/", "\\")) or ".." in PurePosixPath(name).parts:
                    raise InvalidResumeFileError("DOCX archive contains an unsafe path")
                names.add(name)

            if not DOCX_REQUIRED_ENTRIES.issubset(names):
                raise InvalidResumeFileError("DOCX archive is missing required components")
    except zipfile.BadZipFile as exc:
        raise InvalidResumeFileError("file content is not a valid DOCX document") from exc
    except zipfile.LargeZipFile as exc:
        raise InvalidResumeFileError("DOCX archive is not supported") from exc
