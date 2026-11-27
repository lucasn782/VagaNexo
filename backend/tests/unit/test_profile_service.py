from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.auth.service import AuthService
from app.models.enums import SourceType, ValidationResource, ValidationStatus
from app.profile.exceptions import (
    ConflictError,
    InvalidProfileDataError,
    ProfileNotFoundError,
    RecordNotFoundError,
)
from app.profile.service import ProfileService
from app.schemas.certification import CertificationCreate
from app.schemas.education import EducationCreate, EducationUpdate
from app.schemas.experience import ExperienceCreate
from app.schemas.language import LanguageCreate
from app.schemas.preference import JobPreferencesUpsert
from app.schemas.profile import CandidateProfileCreate
from app.schemas.project import ProjectCreate
from app.schemas.skill import SkillCreate


def make_service(db_session: Session) -> ProfileService:
    user = AuthService(db_session).create_user(
        email=f"user-{uuid.uuid4().hex[:8]}@example.com",
        password="TestPassword123!",
    )
    return ProfileService(db_session, user_id=user.id)


def make_profile(service: ProfileService) -> uuid.UUID:
    profile = service.create_profile(CandidateProfileCreate(full_name="Ana Souza"))
    return profile.id


def education_payload() -> EducationCreate:
    return EducationCreate(
        institution="USP",
        degree="Computacao",
        start_date=date(2018, 2, 1),
        end_date=date(2022, 12, 1),
    )


def test_manual_record_is_confirmed_by_default(db_session: Session) -> None:
    service = make_service(db_session)
    profile_id = make_profile(service)
    education = service.create_education(profile_id, education_payload())
    assert education.source_type is SourceType.MANUAL
    assert education.validation_status is ValidationStatus.CONFIRMED


def test_document_record_starts_pending(db_session: Session) -> None:
    service = make_service(db_session)
    profile_id = make_profile(service)
    education = service.create_education(
        profile_id,
        EducationCreate(
            institution="USP",
            degree="Computacao",
            start_date=date(2018, 2, 1),
            source_type=SourceType.DOCUMENT,
            confidence_score=0.6,
        ),
    )
    assert education.validation_status is ValidationStatus.PENDING


def test_ai_record_cannot_start_confirmed(db_session: Session) -> None:
    service = make_service(db_session)
    profile_id = make_profile(service)
    with pytest.raises(InvalidProfileDataError):
        service.create_skill(
            profile_id,
            SkillCreate(
                name="Python",
                source_type=SourceType.AI,
                validation_status=ValidationStatus.CONFIRMED,
            ),
        )


def test_skill_normalization_and_duplicate_conflict(db_session: Session) -> None:
    service = make_service(db_session)
    profile_id = make_profile(service)
    skill = service.create_skill(profile_id, SkillCreate(name="Comunicação"))
    assert skill.normalized_name == "comunicacao"

    with pytest.raises(ConflictError):
        service.create_skill(profile_id, SkillCreate(name="comunicacao"))


def test_duplicate_language_conflict(db_session: Session) -> None:
    service = make_service(db_session)
    profile_id = make_profile(service)
    service.create_language(profile_id, LanguageCreate(language="Ingles"))
    with pytest.raises(ConflictError):
        service.create_language(profile_id, LanguageCreate(language="ingles"))


def test_records_are_scoped_to_the_profile(db_session: Session) -> None:
    service = make_service(db_session)
    first = make_profile(service)
    second = make_profile(service)
    education = service.create_education(first, education_payload())

    with pytest.raises(RecordNotFoundError):
        service.update_education(
            second,
            education.id,
            EducationUpdate(degree="Outro curso"),
        )
    with pytest.raises(RecordNotFoundError):
        service.delete_education(second, education.id)


def test_unknown_profile_raises_not_found(db_session: Session) -> None:
    service = make_service(db_session)
    with pytest.raises(ProfileNotFoundError):
        service.get_profile(uuid.uuid4())


def test_update_rejects_null_required_field(db_session: Session) -> None:
    service = make_service(db_session)
    profile_id = make_profile(service)
    education = service.create_education(profile_id, education_payload())

    with pytest.raises(InvalidProfileDataError):
        service.update_education(
            profile_id,
            education.id,
            EducationUpdate.model_validate({"degree": None}),
        )


def test_confirm_and_reject_validation_status(db_session: Session) -> None:
    service = make_service(db_session)
    profile_id = make_profile(service)
    skill = service.create_skill(
        profile_id,
        SkillCreate(name="Rust", source_type=SourceType.AI, confidence_score=0.4),
    )
    assert skill.validation_status is ValidationStatus.PENDING

    confirmed = service.set_validation_status(
        profile_id,
        ValidationResource.SKILLS,
        skill.id,
        ValidationStatus.CONFIRMED,
    )
    assert confirmed.validation_status is ValidationStatus.CONFIRMED

    rejected = service.set_validation_status(
        profile_id,
        ValidationResource.SKILLS,
        skill.id,
        ValidationStatus.REJECTED,
    )
    assert rejected.validation_status is ValidationStatus.REJECTED


def test_source_document_must_belong_to_profile(db_session: Session) -> None:
    service = make_service(db_session)
    first = make_profile(service)
    second = make_profile(service)
    from app.schemas.resume_document import ResumeDocumentCreate

    document = service.create_resume_document(
        first,
        ResumeDocumentCreate(
            original_filename="curriculo.pdf",
            media_type="application/pdf",
            file_size=1024,
            sha256_hash="c" * 64,
            storage_key="uploads/curriculo.pdf",
        ),
    )
    with pytest.raises(InvalidProfileDataError):
        service.create_education(
            second,
            EducationCreate(
                institution="USP",
                degree="Computacao",
                start_date=date(2018, 2, 1),
                source_type=SourceType.DOCUMENT,
                source_document_id=document.id,
            ),
        )


def test_preferences_upsert(db_session: Session) -> None:
    service = make_service(db_session)
    profile_id = make_profile(service)

    with pytest.raises(RecordNotFoundError):
        service.get_preferences(profile_id)

    created = service.upsert_preferences(
        profile_id,
        JobPreferencesUpsert(minimum_salary=5000, maximum_salary=9000, salary_currency="brl"),
    )
    assert created.minimum_salary is not None
    assert created.salary_currency == "BRL"

    updated = service.upsert_preferences(
        profile_id,
        JobPreferencesUpsert(minimum_salary=6000),
    )
    assert updated.minimum_salary == 6000
    assert updated.maximum_salary == 9000


def test_all_child_resources_can_be_created(db_session: Session) -> None:
    service = make_service(db_session)
    profile_id = make_profile(service)

    experience = service.create_experience(
        profile_id,
        ExperienceCreate(
            company="VagaNexo",
            job_title="Engineer",
            start_date=date(2024, 1, 1),
        ),
    )
    certification = service.create_certification(
        profile_id,
        CertificationCreate(name="AWS", issuing_organization="Amazon"),
    )
    project = service.create_project(
        profile_id,
        ProjectCreate(name="Profile Engine", project_type="professional"),
    )

    assert experience.id is not None
    assert certification.id is not None
    assert project.id is not None
    assert len(service.list_experiences(profile_id)) == 1
    assert len(service.list_certifications(profile_id)) == 1
    assert len(service.list_projects(profile_id)) == 1
