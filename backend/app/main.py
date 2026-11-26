import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.routes.health import router as health_router
from app.api.routes.profiles import router as profiles_router
from app.api.routes.resume_documents import router as resume_documents_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.profile.exceptions import ProfileEngineError
from app.resume_import.exceptions import ResumeImportError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging()
    logger.info("Starting %s", settings.app_name)
    yield
    logger.info("Stopping %s", settings.app_name)


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health_router)
    application.include_router(profiles_router)
    application.include_router(resume_documents_router)

    @application.exception_handler(ProfileEngineError)
    async def handle_profile_error(
        _request: Request,
        exc: ProfileEngineError,
    ) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @application.exception_handler(ResumeImportError)
    async def handle_resume_import_error(
        _request: Request,
        exc: ResumeImportError,
    ) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @application.exception_handler(IntegrityError)
    async def handle_integrity_error(
        _request: Request,
        _exc: IntegrityError,
    ) -> JSONResponse:
        logger.warning("Integrity error while handling a request")
        return JSONResponse(
            status_code=409,
            content={"detail": "request conflicts with existing data"},
        )

    @application.exception_handler(SQLAlchemyError)
    async def handle_database_error(
        _request: Request,
        _exc: SQLAlchemyError,
    ) -> JSONResponse:
        logger.exception("Database error while handling a request")
        return JSONResponse(
            status_code=500,
            content={"detail": "database operation failed"},
        )

    return application


app = create_app()
