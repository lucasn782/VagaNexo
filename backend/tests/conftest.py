from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.core.config import get_settings
from app.database.dependencies import get_db
from app.main import app
from app.models.base import Base

TEST_DATABASE_NAME = "vaganexo_test"

PROFILE_TABLES = (
    "resume_documents",
    "job_preferences",
    "projects",
    "languages",
    "certifications",
    "skills",
    "work_experiences",
    "educations",
    "candidate_profiles",
)


def _test_database_url() -> URL:
    override = os.getenv("TEST_DATABASE_URL")
    if override:
        url = make_url(override)
    else:
        url = make_url(get_settings().database_url).set(database=TEST_DATABASE_NAME)
    if not url.database or not url.database.endswith("_test"):
        raise RuntimeError("refusing to run tests against a database that is not a *_test database")
    return url


def _ensure_database(url: URL) -> None:
    admin_url = url.set(drivername="postgresql", database="postgres")
    with psycopg.connect(
        admin_url.render_as_string(hide_password=False),
        autocommit=True,
    ) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (url.database,),
        ).fetchone()
        if exists is None:
            connection.execute(f'CREATE DATABASE "{url.database}"')


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    url = _test_database_url()
    _ensure_database(url)
    engine = create_engine(url, pool_pre_ping=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def db_session(test_engine: Engine) -> Iterator[Session]:
    with test_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {', '.join(PROFILE_TABLES)} CASCADE"))
    factory = sessionmaker(
        bind=test_engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )
    with factory() as session:
        yield session
        session.rollback()


@pytest.fixture()
def client(db_session: Session) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def profile_payload() -> dict[str, object]:
    return {
        "full_name": "Ana Souza",
        "professional_headline": "Backend Engineer",
        "professional_summary": "Python and PostgreSQL developer.",
        "email": "ana.souza@example.com",
        "phone": "+55 11 90000-0000",
        "city": "Sao Paulo",
        "state": "SP",
        "country": "Brasil",
        "linkedin_url": "https://www.linkedin.com/in/ana-souza",
        "github_url": "https://github.com/ana-souza",
        "portfolio_url": "https://ana-souza.example.com",
    }
