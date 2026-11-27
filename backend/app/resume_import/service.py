"""Resume Importer service: validation, storage, extraction and persistence.

The service owns the transaction and keeps the database and the private
filesystem consistent: files are only committed after the binary validation,
and they are removed when persistence fails.
"""

from __future__ import annotations

import logging
import uuid
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.enums import ParsingStatus
from app.models.resume_document import ResumeDocument
from app.models.resume_extraction import ResumeExtraction
from app.parsers import PARSERS
from app.parsers.file_validator import validate_resume_file
from app.parsers.text_normalizer import count_characters, count_words
from app.profile.service import ProfileService
from app.resume_import.exceptions import (
    DuplicateResumeError,
    ExtractionFailedError,
    ExtractionNotFoundError,
    StorageError,
)
from app.resume_import.storage import ResumeStorage
from app.resume_import.validators import sanitize_original_filename

logger = logging.getLogger(__name__)

EXTRACTION_FAILED_REASON = "text_extraction_failed"
TRUNCATED_WARNING = "content_truncated"


class ResumeImportService:
    """Import a PDF or DOCX resume into a candidate profile."""

    def __init__(
        self,
        session: Session,
        storage: ResumeStorage,
        *,
        max_upload_bytes: int | None = None,
        max_archive_entries: int | None = None,
        max_uncompressed_bytes: int | None = None,
        max_text_characters: int | None = None,
    ) -> None:
        settings = get_settings()
        self.session = session
        self.storage = storage
        self.profiles = ProfileService(session)
        self.max_upload_bytes = (
            max_upload_bytes if max_upload_bytes is not None else settings.max_resume_upload_bytes
        )
        self.max_archive_entries = (
            max_archive_entries
            if max_archive_entries is not None
            else settings.max_resume_archive_entries
        )
        self.max_uncompressed_bytes = (
            max_uncompressed_bytes
            if max_uncompressed_bytes is not None
            else settings.max_resume_uncompressed_bytes
        )
        self.max_text_characters = (
            max_text_characters
            if max_text_characters is not None
            else settings.max_resume_text_characters
        )

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------
    def upload(
        self,
        profile_id: uuid.UUID,
        *,
        filename: str | None,
        media_type: str | None,
        stream: BinaryIO,
    ) -> tuple[ResumeDocument, ResumeExtraction | None]:
        self.profiles.get_profile(profile_id)
        original_filename = sanitize_original_filename(filename)

        staged = self.storage.stage(stream, max_bytes=self.max_upload_bytes)
        stored_keys: list[str] = []
        try:
            validated = validate_resume_file(
                filename=original_filename,
                declared_media_type=media_type,
                path=staged.path,
                max_archive_entries=self.max_archive_entries,
                max_uncompressed_bytes=self.max_uncompressed_bytes,
            )
            if self._duplicate_exists(profile_id, staged.sha256):
                raise DuplicateResumeError("this resume was already imported for this profile")

            document_id = uuid.uuid4()
            try:
                parsed = PARSERS[validated.kind].parse(staged.path)
            except ExtractionFailedError:
                storage_key = self.storage.commit(
                    staged,
                    profile_id=profile_id,
                    document_id=document_id,
                    extension=validated.extension,
                )
                stored_keys.append(storage_key)
                document = ResumeDocument(
                    id=document_id,
                    candidate_profile_id=profile_id,
                    original_filename=original_filename,
                    media_type=validated.media_type,
                    file_size=staged.size,
                    sha256_hash=staged.sha256,
                    storage_key=storage_key,
                    parsing_status=ParsingStatus.FAILED,
                    failure_reason=EXTRACTION_FAILED_REASON,
                )
                self.session.add(document)
                self._commit()
                self.session.refresh(document)
                return document, None

            text, warnings = self._apply_text_limits(parsed.text, list(parsed.warnings))
            storage_key = self.storage.commit(
                staged,
                profile_id=profile_id,
                document_id=document_id,
                extension=validated.extension,
            )
            stored_keys.append(storage_key)

            status = ParsingStatus.COMPLETED_WITH_WARNINGS if warnings else ParsingStatus.COMPLETED
            document = ResumeDocument(
                id=document_id,
                candidate_profile_id=profile_id,
                original_filename=original_filename,
                media_type=validated.media_type,
                file_size=staged.size,
                sha256_hash=staged.sha256,
                storage_key=storage_key,
                parsing_status=status,
            )
            extraction = ResumeExtraction(
                resume_document_id=document_id,
                extracted_text=text,
                page_count=parsed.page_count,
                word_count=count_words(text),
                character_count=count_characters(text),
                parser_name=parsed.parser_name,
                parser_version=parsed.parser_version,
                warnings=warnings,
            )
            extracted_key = self.storage.write_extracted_text(
                profile_id=profile_id,
                document_id=document_id,
                text=text,
            )
            stored_keys.append(extracted_key)
            extraction.extracted_storage_key = extracted_key

            self.session.add_all([document, extraction])
            self._commit()
        except BaseException:
            self.storage.discard(staged)
            for key in stored_keys:
                self._safe_delete(key)
            raise

        self.session.refresh(document)
        self.session.refresh(extraction)
        return document, extraction

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    def get_extraction(
        self,
        profile_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> ResumeExtraction:
        document = self.profiles.get_resume_document(profile_id, document_id)
        extraction = self.session.scalar(
            select(ResumeExtraction).where(ResumeExtraction.resume_document_id == document.id)
        )
        if extraction is None:
            raise ExtractionNotFoundError("extraction is not available for this document")
        return extraction

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------
    def delete_document(self, profile_id: uuid.UUID, document_id: uuid.UUID) -> None:
        self.profiles.get_profile(profile_id)
        document = self.profiles.get_resume_document(profile_id, document_id)

        keys_to_delete: list[str] = []
        owned_upload = self.storage.owned_upload_key(
            storage_key=document.storage_key,
            profile_id=profile_id,
            document_id=document.id,
            media_type=document.media_type,
        )
        if owned_upload is not None:
            keys_to_delete.append(owned_upload)
        else:
            logger.warning(
                "skipping physical deletion for non-canonical upload key on document %s",
                document.id,
            )

        extraction = document.extraction
        if extraction is not None and extraction.extracted_storage_key:
            owned_extracted = self.storage.owned_extracted_key(
                storage_key=extraction.extracted_storage_key,
                profile_id=profile_id,
                document_id=document.id,
            )
            if owned_extracted is not None:
                keys_to_delete.append(owned_extracted)
            else:
                logger.warning(
                    "skipping physical deletion for non-canonical extracted key on document %s",
                    document.id,
                )

        self.session.delete(document)
        try:
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            raise StorageError("resume document could not be deleted") from exc

        for key in keys_to_delete:
            self._safe_delete(key)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _duplicate_exists(self, profile_id: uuid.UUID, sha256_hash: str) -> bool:
        existing = self.session.scalar(
            select(ResumeDocument.id).where(
                ResumeDocument.candidate_profile_id == profile_id,
                ResumeDocument.sha256_hash == sha256_hash,
            )
        )
        return existing is not None

    def _apply_text_limits(self, text: str, warnings: list[str]) -> tuple[str, list[str]]:
        if len(text) > self.max_text_characters:
            text = text[: self.max_text_characters]
            warnings.append(TRUNCATED_WARNING)
        return text, list(dict.fromkeys(warnings))

    def _commit(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateResumeError("this resume was already imported for this profile") from exc
        except SQLAlchemyError as exc:
            self.session.rollback()
            raise StorageError("resume import could not be saved") from exc

    def _safe_delete(self, storage_key: str) -> None:
        try:
            self.storage.delete_key(storage_key)
        except StorageError:
            logger.warning("resume file could not be removed from private storage")
