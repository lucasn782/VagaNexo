from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.candidate_profile import CandidateProfile
from app.models.certification import Certification
from app.models.education import Education
from app.models.enums import (
    EmploymentType,
    ParsingStatus,
    ProjectType,
    SkillCategory,
    SourceType,
    ValidationStatus,
)
from app.models.experience import WorkExperience
from app.models.language import Language
from app.models.preference import JobPreferences
from app.models.project import Project
from app.models.resume_document import ResumeDocument
from app.models.skill import Skill


def make_profile(session: Session, full_name: str = "Ana Souza") -> CandidateProfile:
    profile = CandidateProfile(full_name=full_name)
    session.add(profile)
    session.commit()
    return profile


def test_profile_relationships_and_timestamps(db_session: Session) -> None:
    profile = make_profile(db_session)
    education = Education(
        candidate_profile_id=profile.id,
        institution="Universidade de Sao Paulo",
        degree="Bacharelado em Ciencia da Computacao",
        start_date=date(2018, 2, 1),
        end_date=date(2022, 12, 15),
    )
    experience = WorkExperience(
        candidate_profile_id=profile.id,
        company="VagaNexo",
        job_title="Backend Engineer",
        employment_type=EmploymentType.FULL_TIME,
        start_date=date(2022, 1, 10),
        achievements=["Reduced latency by 30%"],
    )
    skill = Skill(
        candidate_profile_id=profile.id,
        name="Python",
        normalized_name="python",
        category=SkillCategory.TECHNICAL,
        years_experience=Decimal("4.5"),
    )
    db_session.add_all([education, experience, skill])
    db_session.commit()
    db_session.refresh(profile)

    assert profile.created_at.tzinfo is not None
    assert profile.updated_at.tzinfo is not None
    assert len(profile.educations) == 1
    assert len(profile.experiences) == 1
    assert len(profile.skills) == 1
    assert education.candidate_profile_id == profile.id
    assert experience.achievements == ["Reduced latency by 30%"]


def test_profile_delete_cascades_child_records(db_session: Session) -> None:
    profile = make_profile(db_session)
    profile_id = profile.id
    db_session.add_all(
        [
            Education(
                candidate_profile_id=profile_id,
                institution="USP",
                degree="Computacao",
                start_date=date(2018, 2, 1),
            ),
            Skill(
                candidate_profile_id=profile_id,
                name="Go",
                normalized_name="go",
                category=SkillCategory.TECHNICAL,
            ),
            Certification(
                candidate_profile_id=profile_id,
                name="AWS Solutions Architect",
                issuing_organization="Amazon Web Services",
            ),
            Language(candidate_profile_id=profile_id, language="Portugues"),
            Project(
                candidate_profile_id=profile_id, name="VagaNexo", project_type=ProjectType.PERSONAL
            ),
            JobPreferences(candidate_profile_id=profile_id),
        ]
    )
    db_session.commit()

    db_session.delete(profile)
    db_session.commit()

    for model in (Education, Skill, Certification, Language, Project, JobPreferences):
        assert db_session.scalars(select(model)).all() == []


def test_education_rejects_end_date_before_start(db_session: Session) -> None:
    profile = make_profile(db_session)
    db_session.add(
        Education(
            candidate_profile_id=profile.id,
            institution="USP",
            degree="Computacao",
            start_date=date(2022, 1, 1),
            end_date=date(2021, 1, 1),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_current_education_requires_open_end(db_session: Session) -> None:
    profile = make_profile(db_session)
    db_session.add(
        Education(
            candidate_profile_id=profile.id,
            institution="USP",
            degree="Computacao",
            start_date=date(2022, 1, 1),
            end_date=date(2024, 1, 1),
            is_current=True,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_skill_unique_per_profile(db_session: Session) -> None:
    profile = make_profile(db_session)
    db_session.add_all(
        [
            Skill(candidate_profile_id=profile.id, name="Python", normalized_name="python"),
            Skill(candidate_profile_id=profile.id, name="python ", normalized_name="python"),
        ]
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_confidence_score_must_be_between_zero_and_one(db_session: Session) -> None:
    profile = make_profile(db_session)
    db_session.add(
        Skill(
            candidate_profile_id=profile.id,
            name="Python",
            normalized_name="python",
            confidence_score=1.5,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_salary_range_constraint(db_session: Session) -> None:
    profile = make_profile(db_session)
    db_session.add(
        JobPreferences(
            candidate_profile_id=profile.id,
            minimum_salary=Decimal("9000"),
            maximum_salary=Decimal("5000"),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_resume_document_metadata_and_source_set_null(db_session: Session) -> None:
    profile = make_profile(db_session)
    document = ResumeDocument(
        candidate_profile_id=profile.id,
        original_filename="curriculo.pdf",
        media_type="application/pdf",
        file_size=1024,
        sha256_hash="a" * 64,
        storage_key="uploads/curriculo.pdf",
        parsing_status=ParsingStatus.PENDING,
    )
    db_session.add(document)
    db_session.commit()

    education = Education(
        candidate_profile_id=profile.id,
        institution="USP",
        degree="Computacao",
        start_date=date(2018, 2, 1),
        source_type=SourceType.DOCUMENT,
        validation_status=ValidationStatus.PENDING,
        source_document_id=document.id,
        confidence_score=0.82,
    )
    db_session.add(education)
    db_session.commit()

    db_session.delete(document)
    db_session.commit()
    db_session.refresh(education)

    assert education.source_document_id is None
    assert education.validation_status is ValidationStatus.PENDING


def test_profile_full_name_cannot_be_blank(db_session: Session) -> None:
    db_session.add(CandidateProfile(full_name="   "))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_candidate_profile_uses_uuid_identifier(db_session: Session) -> None:
    profile = make_profile(db_session)
    assert isinstance(profile.id, uuid.UUID)
    assert profile.created_at <= datetime.now(UTC)
