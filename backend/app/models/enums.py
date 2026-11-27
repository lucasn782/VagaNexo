from enum import StrEnum

from sqlalchemy import Enum


class SourceType(StrEnum):
    MANUAL = "manual"
    DOCUMENT = "document"
    AI = "ai"


class ValidationStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class SkillCategory(StrEnum):
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    TOOLS = "tools"
    DOMAIN = "domain"
    OTHER = "other"


class ProficiencyLevel(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"
    UNSPECIFIED = "unspecified"


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    INTERNSHIP = "internship"
    CONTRACT = "contract"
    TEMPORARY = "temporary"
    FREELANCE = "freelance"
    OTHER = "other"


class WorkMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


class LanguageProficiency(StrEnum):
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    FLUENT = "fluent"
    NATIVE = "native"
    UNSPECIFIED = "unspecified"


class ProficiencyFramework(StrEnum):
    CEFR = "cefr"
    ACTFL = "actfl"
    OTHER = "other"


class CefrLevel(StrEnum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


class ProjectType(StrEnum):
    PERSONAL = "personal"
    ACADEMIC = "academic"
    PROFESSIONAL = "professional"
    OPEN_SOURCE = "open_source"
    OTHER = "other"


class ParsingStatus(StrEnum):
    """Lifecycle of a resume document inside the importer.

    ``parsed`` is kept for documents registered before the importer existed;
    new imports use ``completed`` or ``completed_with_warnings``.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    PARSED = "parsed"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"


class SeniorityLevel(StrEnum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"
    DIRECTOR = "director"
    EXECUTIVE = "executive"
    UNSPECIFIED = "unspecified"


class ValidationResource(StrEnum):
    EDUCATIONS = "educations"
    EXPERIENCES = "experiences"
    SKILLS = "skills"
    CERTIFICATIONS = "certifications"
    LANGUAGES = "languages"
    PROJECTS = "projects"


def sa_enum(enum_cls: type[StrEnum], name: str, length: int = 32) -> Enum:
    """Build a portable VARCHAR-backed enum with a database check constraint."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        length=length,
        values_callable=lambda member_type: [member.value for member in member_type],
    )
