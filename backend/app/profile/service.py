"""Business rules for the VagaNexo Profile Engine.

The service owns transactions and integrity checks. Routes only translate HTTP
requests and responses, which keeps the module ready for a future authenticated
multi-user version.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.base import Base
from app.models.candidate_profile import CandidateProfile
from app.models.certification import Certification
from app.models.education import Education
from app.models.enums import SourceType, ValidationResource, ValidationStatus
from app.models.experience import WorkExperience
from app.models.language import Language
from app.models.preference import JobPreferences
from app.models.project import Project
from app.models.resume_document import ResumeDocument
from app.models.skill import Skill
from app.profile import validators
from app.profile.exceptions import (
    ConflictError,
    InvalidProfileDataError,
    ProfileNotFoundError,
    RecordNotFoundError,
)
from app.schemas.certification import CertificationCreate, CertificationUpdate
from app.schemas.education import EducationCreate, EducationUpdate
from app.schemas.experience import ExperienceCreate, ExperienceUpdate
from app.schemas.language import LanguageCreate, LanguageUpdate
from app.schemas.preference import JobPreferencesUpsert
from app.schemas.profile import CandidateProfileCreate, CandidateProfileUpdate
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.schemas.resume_document import ResumeDocumentCreate, ResumeDocumentUpdate
from app.schemas.skill import SkillCreate, SkillUpdate

CHILD_MODELS: dict[ValidationResource, type[Base]] = {
    ValidationResource.EDUCATIONS: Education,
    ValidationResource.EXPERIENCES: WorkExperience,
    ValidationResource.SKILLS: Skill,
    ValidationResource.CERTIFICATIONS: Certification,
    ValidationResource.LANGUAGES: Language,
    ValidationResource.PROJECTS: Project,
}

REQUIRED_FIELDS: dict[type[Base], tuple[str, ...]] = {
    Education: ("institution", "degree", "start_date", "is_current"),
    WorkExperience: ("company", "job_title", "employment_type", "start_date", "is_current"),
    Skill: ("name", "category", "proficiency_level"),
    Certification: ("name", "issuing_organization"),
    Language: ("language", "proficiency_level"),
    Project: ("name", "project_type"),
}


class ProfileService:
    """Profile aggregate service bound to a single SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def _commit(self, conflict_detail: str) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError(conflict_detail) from exc

    def _ensure_profile(self, profile_id: uuid.UUID) -> None:
        exists = self.session.scalar(
            select(CandidateProfile.id).where(CandidateProfile.id == profile_id)
        )
        if exists is None:
            raise ProfileNotFoundError("profile not found")

    def _get_child(self, profile_id: uuid.UUID, model: Any, item_id: uuid.UUID) -> Any:
        item = self.session.scalar(
            select(model).where(model.id == item_id, model.candidate_profile_id == profile_id)
        )
        if item is None:
            raise RecordNotFoundError("record not found for this profile")
        return item

    def _list_children(
        self,
        profile_id: uuid.UUID,
        model: Any,
        order_column: Any | None = None,
    ) -> list[Any]:
        self._ensure_profile(profile_id)
        order = order_column if order_column is not None else model.created_at
        return list(
            self.session.scalars(
                select(model).where(model.candidate_profile_id == profile_id).order_by(order.asc())
            )
        )

    def _validate_source_document(
        self,
        profile_id: uuid.UUID,
        document_id: uuid.UUID | None,
    ) -> None:
        if document_id is None:
            return
        document = self.session.scalar(
            select(ResumeDocument.id).where(
                ResumeDocument.id == document_id,
                ResumeDocument.candidate_profile_id == profile_id,
            )
        )
        if document is None:
            raise InvalidProfileDataError("source_document_id does not belong to this profile")

    def _prepare_create_data(self, profile_id: uuid.UUID, payload: Any) -> dict[str, Any]:
        data: dict[str, Any] = payload.model_dump()
        source_type: SourceType = data.get("source_type", SourceType.MANUAL)
        document_id = data.get("source_document_id")
        if document_id is not None:
            self._validate_source_document(profile_id, document_id)
            if "source_type" not in payload.model_fields_set:
                source_type = SourceType.DOCUMENT
        requested = data.pop("validation_status", None)
        data["source_type"] = source_type
        data["validation_status"] = validators.resolve_validation_status(source_type, requested)
        return data

    def _apply_provenance_update(
        self,
        profile_id: uuid.UUID,
        item: Any,
        data: dict[str, Any],
    ) -> None:
        source_type = data.pop("source_type", None)
        document_provided = "source_document_id" in data
        document_id = data.pop("source_document_id", None) if document_provided else None
        if source_type is not None:
            item.source_type = source_type
            if source_type in (SourceType.DOCUMENT, SourceType.AI):
                item.validation_status = ValidationStatus.PENDING
        if document_provided:
            self._validate_source_document(profile_id, document_id)
            if document_id is not None and source_type is None:
                item.source_type = SourceType.DOCUMENT
                item.validation_status = ValidationStatus.PENDING
            item.source_document_id = document_id
        if "confidence_score" in data:
            item.confidence_score = data.pop("confidence_score")

    def _ensure_required_fields(self, item: Any) -> None:
        for field in REQUIRED_FIELDS.get(type(item), ()):
            if getattr(item, field) is None:
                raise InvalidProfileDataError(f"{field} cannot be null")

    def _create_child(
        self,
        profile_id: uuid.UUID,
        model: Any,
        payload: Any,
        validate: Callable[[Any], None],
    ) -> Any:
        self._ensure_profile(profile_id)
        data = self._prepare_create_data(profile_id, payload)
        item = model(candidate_profile_id=profile_id, **data)
        self._ensure_required_fields(item)
        validate(item)
        self.session.add(item)
        self._commit(f"{model.__tablename__} record could not be created")
        self.session.refresh(item)
        return item

    def _update_child(
        self,
        profile_id: uuid.UUID,
        model: Any,
        item_id: uuid.UUID,
        payload: Any,
        validate: Callable[[Any], None],
    ) -> Any:
        item = self._get_child(profile_id, model, item_id)
        data: dict[str, Any] = payload.model_dump(exclude_unset=True)
        self._apply_provenance_update(profile_id, item, data)
        for field, value in data.items():
            setattr(item, field, value)
        self._ensure_required_fields(item)
        validate(item)
        self._commit(f"{model.__tablename__} record could not be updated")
        self.session.refresh(item)
        return item

    def _delete_child(self, profile_id: uuid.UUID, model: Any, item_id: uuid.UUID) -> None:
        item = self._get_child(profile_id, model, item_id)
        self.session.delete(item)
        self._commit(f"{model.__tablename__} record could not be deleted")

    # ------------------------------------------------------------------
    # Candidate profile
    # ------------------------------------------------------------------
    def create_profile(self, payload: CandidateProfileCreate) -> CandidateProfile:
        profile = CandidateProfile(**payload.model_dump())
        self.session.add(profile)
        self._commit("candidate profile could not be created")
        return self.get_profile(profile.id)

    def get_profile(self, profile_id: uuid.UUID) -> CandidateProfile:
        profile = self.session.scalar(
            select(CandidateProfile)
            .where(CandidateProfile.id == profile_id)
            .options(
                selectinload(CandidateProfile.educations),
                selectinload(CandidateProfile.experiences),
                selectinload(CandidateProfile.skills),
                selectinload(CandidateProfile.certifications),
                selectinload(CandidateProfile.languages),
                selectinload(CandidateProfile.projects),
                selectinload(CandidateProfile.preferences),
                selectinload(CandidateProfile.resume_documents),
            )
        )
        if profile is None:
            raise ProfileNotFoundError("profile not found")
        return profile

    def update_profile(
        self,
        profile_id: uuid.UUID,
        payload: CandidateProfileUpdate,
    ) -> CandidateProfile:
        profile = self.get_profile(profile_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(profile, field, value)
        self._commit("candidate profile could not be updated")
        return self.get_profile(profile_id)

    # ------------------------------------------------------------------
    # Education
    # ------------------------------------------------------------------
    def list_educations(self, profile_id: uuid.UUID) -> list[Education]:
        return self._list_children(profile_id, Education)

    def create_education(self, profile_id: uuid.UUID, payload: EducationCreate) -> Education:
        return self._create_child(profile_id, Education, payload, self._validate_education)

    def update_education(
        self, profile_id: uuid.UUID, item_id: uuid.UUID, payload: EducationUpdate
    ) -> Education:
        return self._update_child(profile_id, Education, item_id, payload, self._validate_education)

    def delete_education(self, profile_id: uuid.UUID, item_id: uuid.UUID) -> None:
        self._delete_child(profile_id, Education, item_id)

    @staticmethod
    def _validate_education(item: Any) -> None:
        validators.validate_period(item.start_date, item.end_date, item.is_current)

    # ------------------------------------------------------------------
    # Work experience
    # ------------------------------------------------------------------
    def list_experiences(self, profile_id: uuid.UUID) -> list[WorkExperience]:
        return self._list_children(profile_id, WorkExperience)

    def create_experience(self, profile_id: uuid.UUID, payload: ExperienceCreate) -> WorkExperience:
        return self._create_child(profile_id, WorkExperience, payload, self._validate_experience)

    def update_experience(
        self, profile_id: uuid.UUID, item_id: uuid.UUID, payload: ExperienceUpdate
    ) -> WorkExperience:
        return self._update_child(
            profile_id, WorkExperience, item_id, payload, self._validate_experience
        )

    def delete_experience(self, profile_id: uuid.UUID, item_id: uuid.UUID) -> None:
        self._delete_child(profile_id, WorkExperience, item_id)

    @staticmethod
    def _validate_experience(item: Any) -> None:
        validators.validate_period(item.start_date, item.end_date, item.is_current)

    # ------------------------------------------------------------------
    # Skill
    # ------------------------------------------------------------------
    def list_skills(self, profile_id: uuid.UUID) -> list[Skill]:
        return self._list_children(profile_id, Skill)

    def create_skill(self, profile_id: uuid.UUID, payload: SkillCreate) -> Skill:
        return self._create_child(profile_id, Skill, payload, self._validate_skill)

    def update_skill(
        self, profile_id: uuid.UUID, item_id: uuid.UUID, payload: SkillUpdate
    ) -> Skill:
        return self._update_child(profile_id, Skill, item_id, payload, self._validate_skill)

    def delete_skill(self, profile_id: uuid.UUID, item_id: uuid.UUID) -> None:
        self._delete_child(profile_id, Skill, item_id)

    def _validate_skill(self, item: Any) -> None:
        item.normalized_name = validators.normalize_skill_name(item.name)
        validators.validate_years_experience(item.years_experience)
        statement = select(Skill.id).where(
            Skill.candidate_profile_id == item.candidate_profile_id,
            Skill.normalized_name == item.normalized_name,
        )
        if item.id is not None:
            statement = statement.where(Skill.id != item.id)
        if self.session.scalar(statement) is not None:
            raise ConflictError("skill already registered for this profile")

    # ------------------------------------------------------------------
    # Certification
    # ------------------------------------------------------------------
    def list_certifications(self, profile_id: uuid.UUID) -> list[Certification]:
        return self._list_children(profile_id, Certification)

    def create_certification(
        self, profile_id: uuid.UUID, payload: CertificationCreate
    ) -> Certification:
        return self._create_child(profile_id, Certification, payload, self._validate_certification)

    def update_certification(
        self, profile_id: uuid.UUID, item_id: uuid.UUID, payload: CertificationUpdate
    ) -> Certification:
        return self._update_child(
            profile_id, Certification, item_id, payload, self._validate_certification
        )

    def delete_certification(self, profile_id: uuid.UUID, item_id: uuid.UUID) -> None:
        self._delete_child(profile_id, Certification, item_id)

    @staticmethod
    def _validate_certification(item: Any) -> None:
        validators.validate_certification_dates(item.issue_date, item.expiration_date)

    # ------------------------------------------------------------------
    # Language
    # ------------------------------------------------------------------
    def list_languages(self, profile_id: uuid.UUID) -> list[Language]:
        return self._list_children(profile_id, Language)

    def create_language(self, profile_id: uuid.UUID, payload: LanguageCreate) -> Language:
        return self._create_child(profile_id, Language, payload, self._validate_language)

    def update_language(
        self, profile_id: uuid.UUID, item_id: uuid.UUID, payload: LanguageUpdate
    ) -> Language:
        return self._update_child(profile_id, Language, item_id, payload, self._validate_language)

    def delete_language(self, profile_id: uuid.UUID, item_id: uuid.UUID) -> None:
        self._delete_child(profile_id, Language, item_id)

    def _validate_language(self, item: Any) -> None:
        validators.validate_language_profile(
            item.proficiency_framework,
            item.cefr_level,
        )
        statement = select(Language.id).where(
            Language.candidate_profile_id == item.candidate_profile_id,
            func.lower(Language.language) == item.language.casefold(),
        )
        if item.id is not None:
            statement = statement.where(Language.id != item.id)
        if self.session.scalar(statement) is not None:
            raise ConflictError("language already registered for this profile")

    # ------------------------------------------------------------------
    # Project
    # ------------------------------------------------------------------
    def list_projects(self, profile_id: uuid.UUID) -> list[Project]:
        return self._list_children(profile_id, Project)

    def create_project(self, profile_id: uuid.UUID, payload: ProjectCreate) -> Project:
        return self._create_child(profile_id, Project, payload, self._validate_project)

    def update_project(
        self, profile_id: uuid.UUID, item_id: uuid.UUID, payload: ProjectUpdate
    ) -> Project:
        return self._update_child(profile_id, Project, item_id, payload, self._validate_project)

    def delete_project(self, profile_id: uuid.UUID, item_id: uuid.UUID) -> None:
        self._delete_child(profile_id, Project, item_id)

    @staticmethod
    def _validate_project(item: Any) -> None:
        validators.validate_period(item.start_date, item.end_date, None)

    # ------------------------------------------------------------------
    # Job preferences
    # ------------------------------------------------------------------
    def get_preferences(self, profile_id: uuid.UUID) -> JobPreferences:
        self._ensure_profile(profile_id)
        preferences = self.session.scalar(
            select(JobPreferences).where(JobPreferences.candidate_profile_id == profile_id)
        )
        if preferences is None:
            raise RecordNotFoundError("job preferences not found for this profile")
        return preferences

    def upsert_preferences(
        self,
        profile_id: uuid.UUID,
        payload: JobPreferencesUpsert,
    ) -> JobPreferences:
        self._ensure_profile(profile_id)
        preferences = self.session.scalar(
            select(JobPreferences).where(JobPreferences.candidate_profile_id == profile_id)
        )
        data = payload.model_dump(exclude_unset=True)
        if preferences is None:
            preferences = JobPreferences(candidate_profile_id=profile_id, **data)
            self.session.add(preferences)
        else:
            for field, value in data.items():
                setattr(preferences, field, value)
        validators.validate_salary_range(
            preferences.minimum_salary,
            preferences.maximum_salary,
        )
        self._commit("job preferences could not be saved")
        self.session.refresh(preferences)
        return preferences

    # ------------------------------------------------------------------
    # Resume documents (metadata only)
    # ------------------------------------------------------------------
    def list_resume_documents(self, profile_id: uuid.UUID) -> list[ResumeDocument]:
        return self._list_children(
            profile_id,
            ResumeDocument,
            order_column=ResumeDocument.uploaded_at,
        )

    def create_resume_document(
        self,
        profile_id: uuid.UUID,
        payload: ResumeDocumentCreate,
    ) -> ResumeDocument:
        self._ensure_profile(profile_id)
        validators.validate_storage_key(payload.storage_key)
        document = ResumeDocument(candidate_profile_id=profile_id, **payload.model_dump())
        self.session.add(document)
        self._commit("resume document metadata could not be registered")
        self.session.refresh(document)
        return document

    def get_resume_document(
        self,
        profile_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> ResumeDocument:
        return self._get_child(profile_id, ResumeDocument, document_id)

    def update_resume_document(
        self,
        profile_id: uuid.UUID,
        document_id: uuid.UUID,
        payload: ResumeDocumentUpdate,
    ) -> ResumeDocument:
        document = self._get_child(profile_id, ResumeDocument, document_id)
        data = payload.model_dump(exclude_unset=True)
        for field, value in data.items():
            if value is None:
                raise InvalidProfileDataError(f"{field} cannot be null")
            setattr(document, field, value)
        self._commit("resume document metadata could not be updated")
        self.session.refresh(document)
        return document

    def delete_resume_document(self, profile_id: uuid.UUID, document_id: uuid.UUID) -> None:
        self._delete_child(profile_id, ResumeDocument, document_id)

    # ------------------------------------------------------------------
    # Provenance confirmation
    # ------------------------------------------------------------------
    def set_validation_status(
        self,
        profile_id: uuid.UUID,
        resource: ValidationResource,
        item_id: uuid.UUID,
        status: ValidationStatus,
    ) -> Any:
        model = CHILD_MODELS[resource]
        item = self._get_child(profile_id, model, item_id)
        item.validation_status = status
        self._commit("validation status could not be updated")
        self.session.refresh(item)
        return item
