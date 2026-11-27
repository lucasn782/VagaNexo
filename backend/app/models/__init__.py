"""SQLAlchemy models for the VagaNexo Profile Engine.

Importing this package registers every table on ``Base.metadata`` so that
Alembic and the test fixtures see the complete schema.
"""

from app.models.auth_session import AuthSession
from app.models.base import Base
from app.models.candidate_profile import CandidateProfile
from app.models.certification import Certification
from app.models.education import Education
from app.models.experience import WorkExperience
from app.models.language import Language
from app.models.preference import JobPreferences
from app.models.project import Project
from app.models.resume_document import ResumeDocument
from app.models.resume_extraction import ResumeExtraction
from app.models.skill import Skill
from app.models.user import User

__all__ = [
    "AuthSession",
    "Base",
    "CandidateProfile",
    "Certification",
    "Education",
    "JobPreferences",
    "Language",
    "Project",
    "ResumeDocument",
    "ResumeExtraction",
    "Skill",
    "User",
    "WorkExperience",
]
