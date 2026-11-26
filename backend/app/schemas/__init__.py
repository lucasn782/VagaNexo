"""Pydantic schemas for the Profile Engine."""

from app.schemas.certification import (
    CertificationCreate,
    CertificationResponse,
    CertificationUpdate,
)
from app.schemas.common import (
    MessageResponse,
    ProvenanceCreate,
    ProvenanceResponse,
    ProvenanceUpdate,
    ValidationStatusResponse,
)
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
from app.schemas.resume_document import (
    ResumeDocumentCreate,
    ResumeDocumentResponse,
    ResumeDocumentUpdate,
)
from app.schemas.skill import SkillCreate, SkillResponse, SkillUpdate

__all__ = [
    "CandidateProfileCreate",
    "CandidateProfileResponse",
    "CandidateProfileUpdate",
    "CertificationCreate",
    "CertificationResponse",
    "CertificationUpdate",
    "EducationCreate",
    "EducationResponse",
    "EducationUpdate",
    "ExperienceCreate",
    "ExperienceResponse",
    "ExperienceUpdate",
    "JobPreferencesResponse",
    "JobPreferencesUpsert",
    "LanguageCreate",
    "LanguageResponse",
    "LanguageUpdate",
    "MessageResponse",
    "ProjectCreate",
    "ProjectResponse",
    "ProjectUpdate",
    "ProvenanceCreate",
    "ProvenanceResponse",
    "ProvenanceUpdate",
    "ResumeDocumentCreate",
    "ResumeDocumentResponse",
    "ResumeDocumentUpdate",
    "SkillCreate",
    "SkillResponse",
    "SkillUpdate",
    "ValidationStatusResponse",
]
