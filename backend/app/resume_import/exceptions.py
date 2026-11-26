"""Domain errors for the Resume Importer.

They are translated into HTTP responses by the application exception handlers,
so filesystem paths, SQL statements and stack traces never reach the client.
"""

from __future__ import annotations


class ResumeImportError(Exception):
    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class InvalidResumeFileError(ResumeImportError):
    status_code = 422


class EncryptedResumeError(InvalidResumeFileError):
    status_code = 422


class ExtractionFailedError(ResumeImportError):
    """The file was accepted but its text could not be extracted."""

    status_code = 500

    def __init__(self) -> None:
        super().__init__("resume text could not be extracted")


class ResumeTooLargeError(ResumeImportError):
    status_code = 413


class DuplicateResumeError(ResumeImportError):
    status_code = 409


class ExtractionNotFoundError(ResumeImportError):
    status_code = 404


class StorageError(ResumeImportError):
    status_code = 500

    def __init__(self, detail: str = "resume storage operation failed") -> None:
        super().__init__(detail)
