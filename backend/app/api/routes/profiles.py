"""REST endpoints for the VagaNexo Profile Engine.

Every route is scoped to a candidate profile. Records are always loaded with
both the item id and the profile id, so an item from another profile is never
returned or modified.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.database.dependencies import get_db
from app.models.candidate_profile import CandidateProfile
from app.models.certification import Certification
from app.models.education import Education
from app.models.enums import ValidationResource, ValidationStatus
from app.models.experience import WorkExperience
from app.models.language import Language
from app.models.preference import JobPreferences
from app.models.project import Project
from app.models.skill import Skill
from app.profile.service import ProfileService
from app.schemas.certification import (
    CertificationCreate,
    CertificationResponse,
    CertificationUpdate,
)
from app.schemas.common import ValidationStatusResponse
from app.schemas.education import EducationCreate, EducationResponse, EducationUpdate
from app.schemas.experience import ExperienceCreate, ExperienceResponse, ExperienceUpdate
from app.schemas.language import LanguageCreate, LanguageResponse, LanguageUpdate
from app.schemas.preference import JobPreferencesResponse, JobPreferencesUpsert
from app.schemas.profile import (
    CandidateProfileCreate,
    CandidateProfileResponse,
    CandidateProfileUpdate,
)
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.schemas.skill import SkillCreate, SkillResponse, SkillUpdate

SessionDep = Annotated[Session, Depends(get_db)]


def get_service(session: SessionDep) -> ProfileService:
    return ProfileService(session)


ServiceDep = Annotated[ProfileService, Depends(get_service)]

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


# ---------------------------------------------------------------------------
# Candidate profile
# ---------------------------------------------------------------------------
@router.post(
    "",
    response_model=CandidateProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a candidate profile",
)
def create_profile(
    payload: CandidateProfileCreate,
    service: ServiceDep,
) -> CandidateProfile:
    return service.create_profile(payload)


@router.get(
    "/{profile_id}",
    response_model=CandidateProfileResponse,
    summary="Get a candidate profile with all related records",
)
def read_profile(profile_id: uuid.UUID, service: ServiceDep) -> CandidateProfile:
    return service.get_profile(profile_id)


@router.patch(
    "/{profile_id}",
    response_model=CandidateProfileResponse,
    summary="Update a candidate profile",
)
def update_profile(
    profile_id: uuid.UUID,
    payload: CandidateProfileUpdate,
    service: ServiceDep,
) -> CandidateProfile:
    return service.update_profile(profile_id, payload)


# ---------------------------------------------------------------------------
# Education
# ---------------------------------------------------------------------------
@router.get(
    "/{profile_id}/educations",
    response_model=list[EducationResponse],
    summary="List academic background records",
)
def list_educations(profile_id: uuid.UUID, service: ServiceDep) -> list[Education]:
    return service.list_educations(profile_id)


@router.post(
    "/{profile_id}/educations",
    response_model=EducationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an academic background record",
)
def create_education(
    profile_id: uuid.UUID,
    payload: EducationCreate,
    service: ServiceDep,
) -> Education:
    return service.create_education(profile_id, payload)


@router.patch(
    "/{profile_id}/educations/{item_id}",
    response_model=EducationResponse,
    summary="Update an academic background record",
)
def update_education(
    profile_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: EducationUpdate,
    service: ServiceDep,
) -> Education:
    return service.update_education(profile_id, item_id, payload)


@router.delete(
    "/{profile_id}/educations/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete an academic background record",
)
def delete_education(
    profile_id: uuid.UUID,
    item_id: uuid.UUID,
    service: ServiceDep,
) -> Response:
    service.delete_education(profile_id, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Work experience
# ---------------------------------------------------------------------------
@router.get(
    "/{profile_id}/experiences",
    response_model=list[ExperienceResponse],
    summary="List work experiences",
)
def list_experiences(
    profile_id: uuid.UUID,
    service: ServiceDep,
) -> list[WorkExperience]:
    return service.list_experiences(profile_id)


@router.post(
    "/{profile_id}/experiences",
    response_model=ExperienceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a work experience",
)
def create_experience(
    profile_id: uuid.UUID,
    payload: ExperienceCreate,
    service: ServiceDep,
) -> WorkExperience:
    return service.create_experience(profile_id, payload)


@router.patch(
    "/{profile_id}/experiences/{item_id}",
    response_model=ExperienceResponse,
    summary="Update a work experience",
)
def update_experience(
    profile_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ExperienceUpdate,
    service: ServiceDep,
) -> WorkExperience:
    return service.update_experience(profile_id, item_id, payload)


@router.delete(
    "/{profile_id}/experiences/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a work experience",
)
def delete_experience(
    profile_id: uuid.UUID,
    item_id: uuid.UUID,
    service: ServiceDep,
) -> Response:
    service.delete_experience(profile_id, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Skill
# ---------------------------------------------------------------------------
@router.get(
    "/{profile_id}/skills",
    response_model=list[SkillResponse],
    summary="List skills",
)
def list_skills(profile_id: uuid.UUID, service: ServiceDep) -> list[Skill]:
    return service.list_skills(profile_id)


@router.post(
    "/{profile_id}/skills",
    response_model=SkillResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a skill",
)
def create_skill(
    profile_id: uuid.UUID,
    payload: SkillCreate,
    service: ServiceDep,
) -> Skill:
    return service.create_skill(profile_id, payload)


@router.patch(
    "/{profile_id}/skills/{item_id}",
    response_model=SkillResponse,
    summary="Update a skill",
)
def update_skill(
    profile_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: SkillUpdate,
    service: ServiceDep,
) -> Skill:
    return service.update_skill(profile_id, item_id, payload)


@router.delete(
    "/{profile_id}/skills/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a skill",
)
def delete_skill(
    profile_id: uuid.UUID,
    item_id: uuid.UUID,
    service: ServiceDep,
) -> Response:
    service.delete_skill(profile_id, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Certification
# ---------------------------------------------------------------------------
@router.get(
    "/{profile_id}/certifications",
    response_model=list[CertificationResponse],
    summary="List certifications",
)
def list_certifications(
    profile_id: uuid.UUID,
    service: ServiceDep,
) -> list[Certification]:
    return service.list_certifications(profile_id)


@router.post(
    "/{profile_id}/certifications",
    response_model=CertificationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a certification",
)
def create_certification(
    profile_id: uuid.UUID,
    payload: CertificationCreate,
    service: ServiceDep,
) -> Certification:
    return service.create_certification(profile_id, payload)


@router.patch(
    "/{profile_id}/certifications/{item_id}",
    response_model=CertificationResponse,
    summary="Update a certification",
)
def update_certification(
    profile_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: CertificationUpdate,
    service: ServiceDep,
) -> Certification:
    return service.update_certification(profile_id, item_id, payload)


@router.delete(
    "/{profile_id}/certifications/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a certification",
)
def delete_certification(
    profile_id: uuid.UUID,
    item_id: uuid.UUID,
    service: ServiceDep,
) -> Response:
    service.delete_certification(profile_id, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------
@router.get(
    "/{profile_id}/languages",
    response_model=list[LanguageResponse],
    summary="List languages",
)
def list_languages(profile_id: uuid.UUID, service: ServiceDep) -> list[Language]:
    return service.list_languages(profile_id)


@router.post(
    "/{profile_id}/languages",
    response_model=LanguageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a language",
)
def create_language(
    profile_id: uuid.UUID,
    payload: LanguageCreate,
    service: ServiceDep,
) -> Language:
    return service.create_language(profile_id, payload)


@router.patch(
    "/{profile_id}/languages/{item_id}",
    response_model=LanguageResponse,
    summary="Update a language",
)
def update_language(
    profile_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: LanguageUpdate,
    service: ServiceDep,
) -> Language:
    return service.update_language(profile_id, item_id, payload)


@router.delete(
    "/{profile_id}/languages/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a language",
)
def delete_language(
    profile_id: uuid.UUID,
    item_id: uuid.UUID,
    service: ServiceDep,
) -> Response:
    service.delete_language(profile_id, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------
@router.get(
    "/{profile_id}/projects",
    response_model=list[ProjectResponse],
    summary="List projects",
)
def list_projects(profile_id: uuid.UUID, service: ServiceDep) -> list[Project]:
    return service.list_projects(profile_id)


@router.post(
    "/{profile_id}/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project",
)
def create_project(
    profile_id: uuid.UUID,
    payload: ProjectCreate,
    service: ServiceDep,
) -> Project:
    return service.create_project(profile_id, payload)


@router.patch(
    "/{profile_id}/projects/{item_id}",
    response_model=ProjectResponse,
    summary="Update a project",
)
def update_project(
    profile_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ProjectUpdate,
    service: ServiceDep,
) -> Project:
    return service.update_project(profile_id, item_id, payload)


@router.delete(
    "/{profile_id}/projects/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a project",
)
def delete_project(
    profile_id: uuid.UUID,
    item_id: uuid.UUID,
    service: ServiceDep,
) -> Response:
    service.delete_project(profile_id, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Job preferences
# ---------------------------------------------------------------------------
@router.get(
    "/{profile_id}/preferences",
    response_model=JobPreferencesResponse,
    summary="Get job preferences",
)
def read_preferences(profile_id: uuid.UUID, service: ServiceDep) -> JobPreferences:
    return service.get_preferences(profile_id)


@router.put(
    "/{profile_id}/preferences",
    response_model=JobPreferencesResponse,
    summary="Create or update job preferences",
)
def upsert_preferences(
    profile_id: uuid.UUID,
    payload: JobPreferencesUpsert,
    service: ServiceDep,
) -> JobPreferences:
    return service.upsert_preferences(profile_id, payload)


# ---------------------------------------------------------------------------
# Provenance validation
# ---------------------------------------------------------------------------
@router.post(
    "/{profile_id}/validation/{resource}/{item_id}/confirm",
    response_model=ValidationStatusResponse,
    summary="Confirm an imported or AI-suggested record",
)
def confirm_record(
    profile_id: uuid.UUID,
    resource: ValidationResource,
    item_id: uuid.UUID,
    service: ServiceDep,
) -> ValidationStatusResponse:
    item = service.set_validation_status(
        profile_id,
        resource,
        item_id,
        ValidationStatus.CONFIRMED,
    )
    return ValidationStatusResponse(
        resource=resource.value,
        id=item.id,
        validation_status=item.validation_status,
        updated_at=item.updated_at,
    )


@router.post(
    "/{profile_id}/validation/{resource}/{item_id}/reject",
    response_model=ValidationStatusResponse,
    summary="Reject an imported or AI-suggested record",
)
def reject_record(
    profile_id: uuid.UUID,
    resource: ValidationResource,
    item_id: uuid.UUID,
    service: ServiceDep,
) -> ValidationStatusResponse:
    item = service.set_validation_status(
        profile_id,
        resource,
        item_id,
        ValidationStatus.REJECTED,
    )
    return ValidationStatusResponse(
        resource=resource.value,
        id=item.id,
        validation_status=item.validation_status,
        updated_at=item.updated_at,
    )
