"""Resume Importer REST endpoints.

All routes are scoped to a candidate profile. A document from another profile
is never returned, modified or deleted.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    ActiveUserDep,
    CSRFProtectedUserDep,
    require_owned_profile,
)
from app.database.dependencies import get_db
from app.models.candidate_profile import CandidateProfile
from app.models.resume_document import ResumeDocument
from app.models.resume_extraction import ResumeExtraction
from app.profile.service import ProfileService
from app.resume_import.service import ResumeImportService
from app.resume_import.storage import ResumeStorage
from app.schemas.resume_document import (
    ResumeDocumentCreate,
    ResumeDocumentResponse,
    ResumeDocumentUpdate,
)
from app.schemas.resume_import import (
    ResumeDocumentDetailResponse,
    ResumeExtractionResponse,
    ResumeExtractionSummary,
    ResumeUploadResponse,
)

SessionDep = Annotated[Session, Depends(get_db)]
OwnedProfileDep = Annotated[CandidateProfile, Depends(require_owned_profile)]


def get_read_profile_service(
    session: SessionDep,
    current_user: ActiveUserDep,
) -> ProfileService:
    return ProfileService(session, user_id=current_user.id)


def get_write_profile_service(
    session: SessionDep,
    current_user: CSRFProtectedUserDep,
) -> ProfileService:
    return ProfileService(session, user_id=current_user.id)


def get_resume_storage() -> ResumeStorage:
    return ResumeStorage.from_settings()


def get_read_resume_import_service(
    session: SessionDep,
    current_user: ActiveUserDep,
    storage: Annotated[ResumeStorage, Depends(get_resume_storage)],
) -> ResumeImportService:
    return ResumeImportService(session, storage, user_id=current_user.id)


def get_write_resume_import_service(
    session: SessionDep,
    current_user: CSRFProtectedUserDep,
    storage: Annotated[ResumeStorage, Depends(get_resume_storage)],
) -> ResumeImportService:
    return ResumeImportService(session, storage, user_id=current_user.id)


ReadProfileServiceDep = Annotated[ProfileService, Depends(get_read_profile_service)]
WriteProfileServiceDep = Annotated[ProfileService, Depends(get_write_profile_service)]
ReadImportServiceDep = Annotated[ResumeImportService, Depends(get_read_resume_import_service)]
WriteImportServiceDep = Annotated[ResumeImportService, Depends(get_write_resume_import_service)]

router = APIRouter(prefix="/api/v1/profiles", tags=["resume-documents"])


def _summary(extraction: ResumeExtraction | None) -> ResumeExtractionSummary | None:
    if extraction is None:
        return None
    return ResumeExtractionSummary.model_validate(extraction)


def _upload_response(
    document: ResumeDocument,
    extraction: ResumeExtraction | None,
) -> ResumeUploadResponse:
    return ResumeUploadResponse(
        id=document.id,
        candidate_profile_id=document.candidate_profile_id,
        original_filename=document.original_filename,
        media_type=document.media_type,
        file_size=document.file_size,
        sha256_hash=document.sha256_hash,
        parsing_status=document.parsing_status,
        page_count=extraction.page_count if extraction is not None else None,
        word_count=extraction.word_count if extraction is not None else None,
        character_count=extraction.character_count if extraction is not None else None,
        warnings=list(extraction.warnings) if extraction is not None else [],
        uploaded_at=document.uploaded_at,
    )


@router.get(
    "/{profile_id}/resume-documents",
    response_model=list[ResumeDocumentResponse],
    summary="List resume document metadata",
)
def list_resume_documents(
    profile_id: uuid.UUID,
    _owned_profile: OwnedProfileDep,
    service: ReadProfileServiceDep,
) -> list[ResumeDocument]:
    return service.list_resume_documents(profile_id)


@router.post(
    "/{profile_id}/resume-documents",
    response_model=ResumeDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register resume document metadata without a file",
)
def create_resume_document(
    profile_id: uuid.UUID,
    payload: ResumeDocumentCreate,
    _owned_profile: OwnedProfileDep,
    service: WriteProfileServiceDep,
) -> ResumeDocument:
    return service.create_resume_document(profile_id, payload)


@router.post(
    "/{profile_id}/resume-documents/upload",
    response_model=ResumeUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload, validate, store and extract a PDF or DOCX resume",
)
def upload_resume_document(
    profile_id: uuid.UUID,
    file: Annotated[UploadFile, File(description="Resume file in PDF or DOCX format")],
    _owned_profile: OwnedProfileDep,
    service: WriteImportServiceDep,
) -> ResumeUploadResponse:
    document, extraction = service.upload(
        profile_id,
        filename=file.filename,
        media_type=file.content_type,
        stream=file.file,
    )
    return _upload_response(document, extraction)


@router.get(
    "/{profile_id}/resume-documents/{document_id}",
    response_model=ResumeDocumentDetailResponse,
    summary="Get resume document metadata and extraction summary",
)
def read_resume_document(
    profile_id: uuid.UUID,
    document_id: uuid.UUID,
    _owned_profile: OwnedProfileDep,
    service: ReadProfileServiceDep,
) -> ResumeDocumentDetailResponse:
    document = service.get_resume_document(profile_id, document_id)
    return ResumeDocumentDetailResponse.model_validate(document)


@router.get(
    "/{profile_id}/resume-documents/{document_id}/extraction",
    response_model=ResumeExtractionResponse,
    summary="Get the extracted text of a resume document",
)
def read_resume_extraction(
    profile_id: uuid.UUID,
    document_id: uuid.UUID,
    _owned_profile: OwnedProfileDep,
    service: ReadImportServiceDep,
) -> ResumeExtractionResponse:
    extraction = service.get_extraction(profile_id, document_id)
    return ResumeExtractionResponse.model_validate(extraction)


@router.patch(
    "/{profile_id}/resume-documents/{document_id}",
    response_model=ResumeDocumentResponse,
    summary="Update resume document metadata",
)
def update_resume_document(
    profile_id: uuid.UUID,
    document_id: uuid.UUID,
    payload: ResumeDocumentUpdate,
    _owned_profile: OwnedProfileDep,
    service: WriteProfileServiceDep,
) -> ResumeDocument:
    return service.update_resume_document(profile_id, document_id, payload)


@router.delete(
    "/{profile_id}/resume-documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a resume document, its extraction and stored files",
)
def delete_resume_document(
    profile_id: uuid.UUID,
    document_id: uuid.UUID,
    _owned_profile: OwnedProfileDep,
    service: WriteImportServiceDep,
) -> Response:
    service.delete_document(profile_id, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
