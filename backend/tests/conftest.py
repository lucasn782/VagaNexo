from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.auth.dependencies import get_rate_limiter
from app.auth.rate_limit import InMemoryRateLimiter
from app.auth.service import AuthService
from app.core.config import get_settings
from app.database.dependencies import get_db
from app.main import app

TEST_DATABASE_NAME = "vaganexo_test"
ALLOWED_TEST_DATABASES = {"vaganexo_test", "vaganexo_migration_test"}

PROFILE_TABLES = (
    "resume_extractions",
    "resume_documents",
    "job_preferences",
    "projects",
    "languages",
    "certifications",
    "skills",
    "work_experiences",
    "educations",
    "candidate_profiles",
    "email_outbox",
    "account_action_tokens",
    "auth_sessions",
    "users",
)


def _test_database_url() -> URL:
    override = os.getenv("TEST_DATABASE_URL")
    if override:
        url = make_url(override)
    else:
        url = make_url(get_settings().database_url).set(database=TEST_DATABASE_NAME)
    if url.database not in ALLOWED_TEST_DATABASES:
        raise RuntimeError("refusing to run tests against a database outside the test allowlist")
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


def _run_test_migrations(engine: Engine) -> None:
    if engine.url.database not in ALLOWED_TEST_DATABASES:
        raise RuntimeError("refusing to run migrations outside the test database allowlist")
    alembic_ini = Path(__file__).resolve().parents[1] / "alembic.ini"
    config = Config(str(alembic_ini))
    with engine.begin() as connection:
        actual_database = connection.execute(text("SELECT current_database()")).scalar_one()
        if actual_database not in ALLOWED_TEST_DATABASES:
            raise RuntimeError("refusing to run migrations against an unauthorized database")
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    url = _test_database_url()
    if url.database != TEST_DATABASE_NAME:
        raise RuntimeError("the general test suite may use only vaganexo_test")
    _ensure_database(url)
    engine = create_engine(url, pool_pre_ping=True)
    _run_test_migrations(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def db_session(test_engine: Engine) -> Iterator[Session]:
    if test_engine.url.database != TEST_DATABASE_NAME:
        raise RuntimeError("refusing to truncate outside vaganexo_test")
    with test_engine.connect() as connection:
        actual_database = connection.execute(text("SELECT current_database()")).scalar_one()
    if actual_database != TEST_DATABASE_NAME:
        raise RuntimeError("refusing to truncate tables in an unauthorized database")
    existing_tables = set(inspect(test_engine).get_table_names(schema="public"))
    missing_tables = set(PROFILE_TABLES) - existing_tables
    if missing_tables:
        raise RuntimeError(
            f"test database is missing expected tables: {', '.join(sorted(missing_tables))}"
        )
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
def unauthenticated_client(db_session: Session) -> Iterator[TestClient]:
    limiter = InMemoryRateLimiter(max_attempts=50, window_seconds=300)

    def override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def client(unauthenticated_client: TestClient, db_session: Session) -> Iterator[TestClient]:
    auth_service = AuthService(db_session)
    auth_service.create_user(email="default-test@example.com", password="TestPassword123!")
    login_resp = unauthenticated_client.post(
        "/api/v1/auth/login",
        json={"email": "default-test@example.com", "password": "TestPassword123!"},
    )
    assert login_resp.status_code == 200, login_resp.text
    csrf_token = login_resp.json()["csrf_token"]
    unauthenticated_client.headers.update({"X-CSRF-Token": csrf_token})
    yield unauthenticated_client


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
