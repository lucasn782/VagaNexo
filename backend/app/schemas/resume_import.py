from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.models.enums import ParsingStatus
from app.schemas.common import APIModel
from app.schemas.resume_document import ResumeDocumentResponse


class ResumeExtractionSummary(APIModel):
    """Extraction statistics without the document text."""

    id: UUID
    resume_document_id: UUID
    page_count: int
    word_count: int
    character_count: int
    parser_name: str
    parser_version: str
    warnings: list[str]
    created_at: datetime


class ResumeExtractionResponse(ResumeExtractionSummary):
    """Full extraction content. Only exposed by the dedicated endpoint."""

    extracted_text: str = Field(description="Normalized text extracted from the resume.")


class ResumeDocumentDetailResponse(ResumeDocumentResponse):
    extraction: ResumeExtractionSummary | None = None


class ResumeUploadResponse(APIModel):
    """Result of a resume upload, including the extraction summary."""

    id: UUID
    candidate_profile_id: UUID
    original_filename: str
    media_type: str
    file_size: int
    sha256_hash: str
    parsing_status: ParsingStatus
    page_count: int | None = None
    word_count: int | None = None
    character_count: int | None = None
    warnings: list[str] = Field(default_factory=list)
    uploaded_at: datetime
