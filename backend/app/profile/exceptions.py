"""Domain errors for the Profile Engine.

They are translated into HTTP responses by the application exception handlers,
so internal database details never reach the client.
"""

from __future__ import annotations


class ProfileEngineError(Exception):
    """Base class for expected profile domain errors."""

    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class ProfileNotFoundError(ProfileEngineError):
    status_code = 404


class RecordNotFoundError(ProfileEngineError):
    status_code = 404


class ConflictError(ProfileEngineError):
    status_code = 409


class InvalidProfileDataError(ProfileEngineError):
    status_code = 422
