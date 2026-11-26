from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text
from sqlalchemy.orm import Session
from tests.conftest import PROFILE_TABLES, _test_database_url

from app.models.candidate_profile import CandidateProfile


def test_database_url_requires_test_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "TEST_DATABASE_URL", "postgresql+psycopg://user:pass@127.0.0.1:5433/vaganexo"
    )
    with pytest.raises(RuntimeError, match="_test"):
        _test_database_url()


def test_engine_targets_test_database_only(test_engine: Engine) -> None:
    assert test_engine.url.database is not None
    assert test_engine.url.database.endswith("_test")
    assert test_engine.url.database != "vaganexo"


def test_alembic_migrations_applied_and_all_tables_exist(test_engine: Engine) -> None:
    existing_tables = set(inspect(test_engine).get_table_names(schema="public"))
    expected_tables = set(PROFILE_TABLES) | {"alembic_version"}
    assert expected_tables.issubset(existing_tables)

    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    script = ScriptDirectory.from_config(Config(str(alembic_ini)))
    head_revision = script.get_current_head()

    with test_engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == head_revision


def test_db_session_truncates_data_without_touching_alembic_version(
    test_engine: Engine,
    db_session: Session,
) -> None:
    profile = CandidateProfile(full_name="Isolated Test User")
    db_session.add(profile)
    db_session.commit()

    assert db_session.query(CandidateProfile).count() == 1

    with test_engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version is not None
