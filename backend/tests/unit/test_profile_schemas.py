from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.models.enums import (
    EmploymentType,
    ProficiencyFramework,
    SkillCategory,
    SourceType,
    ValidationStatus,
    WorkMode,
)
from app.schemas.certification import CertificationCreate
from app.schemas.education import EducationCreate
from app.schemas.experience import ExperienceCreate
from app.schemas.language import LanguageCreate
from app.schemas.preference import JobPreferencesUpsert
from app.schemas.profile import CandidateProfileCreate, CandidateProfileUpdate
from app.schemas.project import ProjectCreate
from app.schemas.resume_document import ResumeDocumentCreate
from app.schemas.skill import SkillCreate


def test_valid_profile_payload() -> None:
    profile = CandidateProfileCreate(
        full_name="  Ana Souza  ",
        email="ana@example.com",
        linkedin_url="https://www.linkedin.com/in/ana-souza",
    )
    assert profile.full_name == "Ana Souza"
    assert profile.email == "ana@example.com"


def test_profile_rejects_blank_name() -> None:
    with pytest.raises(ValidationError):
        CandidateProfileCreate(full_name="   ")


def test_profile_rejects_invalid_url() -> None:
    with pytest.raises(ValidationError):
        CandidateProfileCreate(full_name="Ana", github_url="not-a-url")


def test_profile_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        CandidateProfileCreate(full_name="Ana", email="ana.example.com")


def test_profile_update_forbids_internal_fields() -> None:
    with pytest.raises(ValidationError):
        CandidateProfileUpdate.model_validate({"created_at": "2026-01-01T00:00:00Z"})


def test_profile_update_rejects_null_name() -> None:
    with pytest.raises(ValidationError):
        CandidateProfileUpdate.model_validate({"full_name": None})


def test_education_rejects_invalid_period() -> None:
    with pytest.raises(ValidationError):
        EducationCreate(
            institution="USP",
            degree="Computacao",
            start_date=date(2022, 1, 1),
            end_date=date(2021, 1, 1),
        )


def test_education_current_cannot_have_end_date() -> None:
    with pytest.raises(ValidationError):
        EducationCreate(
            institution="USP",
            degree="Computacao",
            start_date=date(2022, 1, 1),
            end_date=date(2024, 1, 1),
            is_current=True,
        )


def test_experience_accepts_supported_employment_type() -> None:
    experience = ExperienceCreate(
        company="VagaNexo",
        job_title="Engineer",
        employment_type=EmploymentType.CONTRACT,
        start_date=date(2024, 1, 1),
        achievements=["Shipped the profile engine"],
    )
    assert experience.employment_type is EmploymentType.CONTRACT


def test_skill_rejects_out_of_range_years() -> None:
    with pytest.raises(ValidationError):
        SkillCreate(name="Python", years_experience=120)


def test_skill_accepts_supported_category() -> None:
    skill = SkillCreate(name="Python", category=SkillCategory.TECHNICAL, confidence_score=0.5)
    assert skill.category is SkillCategory.TECHNICAL


def test_skill_rejects_invalid_category() -> None:
    with pytest.raises(ValidationError):
        SkillCreate.model_validate({"name": "Python", "category": "magic"})


def test_certification_rejects_expiration_before_issue() -> None:
    with pytest.raises(ValidationError):
        CertificationCreate(
            name="AWS",
            issuing_organization="Amazon",
            issue_date=date(2024, 1, 1),
            expiration_date=date(2023, 1, 1),
        )


def test_language_cefr_requires_framework() -> None:
    with pytest.raises(ValidationError):
        LanguageCreate(language="Ingles", cefr_level="B2")


def test_language_accepts_cefr_level() -> None:
    language = LanguageCreate(
        language="Ingles",
        proficiency_framework=ProficiencyFramework.CEFR,
        cefr_level="B2",
    )
    assert language.cefr_level is not None
    assert language.cefr_level.value == "B2"


def test_project_rejects_invalid_period() -> None:
    with pytest.raises(ValidationError):
        ProjectCreate(
            name="VagaNexo",
            start_date=date(2024, 1, 1),
            end_date=date(2023, 1, 1),
        )


def test_preferences_reject_inverted_salary_range() -> None:
    with pytest.raises(ValidationError):
        JobPreferencesUpsert(minimum_salary=10000, maximum_salary=5000)


def test_preferences_normalize_currency_and_accept_work_modes() -> None:
    preferences = JobPreferencesUpsert(
        work_modes=[WorkMode.REMOTE, WorkMode.HYBRID],
        salary_currency="brl",
        minimum_salary=5000,
        maximum_salary=9000,
    )
    assert preferences.salary_currency == "BRL"
    assert preferences.work_modes == [WorkMode.REMOTE, WorkMode.HYBRID]


def test_preferences_reject_invalid_work_mode() -> None:
    with pytest.raises(ValidationError):
        JobPreferencesUpsert.model_validate({"work_modes": ["teleport"]})


def test_provenance_confidence_out_of_range() -> None:
    with pytest.raises(ValidationError):
        SkillCreate(name="Python", confidence_score=1.2)


def test_provenance_accepts_document_source() -> None:
    skill = SkillCreate(
        name="Python",
        source_type=SourceType.DOCUMENT,
        validation_status=ValidationStatus.PENDING,
        confidence_score=0.75,
    )
    assert skill.source_type is SourceType.DOCUMENT
    assert skill.validation_status is ValidationStatus.PENDING


def test_resume_document_rejects_invalid_hash() -> None:
    with pytest.raises(ValidationError):
        ResumeDocumentCreate(
            original_filename="curriculo.pdf",
            media_type="application/pdf",
            file_size=1024,
            sha256_hash="xyz",
            storage_key="uploads/curriculo.pdf",
        )


def test_resume_document_accepts_valid_metadata() -> None:
    document = ResumeDocumentCreate(
        original_filename="curriculo.pdf",
        media_type="application/pdf",
        file_size=2048,
        sha256_hash="b" * 64,
        storage_key="uploads/curriculo.pdf",
    )
    assert document.file_size == 2048
