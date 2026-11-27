from __future__ import annotations

import uuid
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL
from tests.conftest import _test_database_url

MIGRATION_DB_NAME = "vaganexo_migration_test"


def _migration_url() -> URL:
    base = _test_database_url()
    assert base.database != "vaganexo"
    return base.set(database=MIGRATION_DB_NAME)


def _recreate_disposable_db(url: URL) -> None:
    admin_url = url.set(drivername="postgresql", database="postgres")
    with psycopg.connect(
        admin_url.render_as_string(hide_password=False),
        autocommit=True,
    ) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (url.database,),
        )
        conn.execute(f'DROP DATABASE IF EXISTS "{url.database}"')
        conn.execute(f'CREATE DATABASE "{url.database}"')


def _drop_disposable_db(url: URL) -> None:
    admin_url = url.set(drivername="postgresql", database="postgres")
    with psycopg.connect(
        admin_url.render_as_string(hide_password=False),
        autocommit=True,
    ) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (url.database,),
        )
        conn.execute(f'DROP DATABASE IF EXISTS "{url.database}"')


def test_auth_migration_preserves_legacy_profiles_and_downgrades_cleanly() -> None:
    url = _migration_url()
    _recreate_disposable_db(url)
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(alembic_ini))
    engine = create_engine(url, pool_pre_ping=True)

    try:
        # 1. Upgrade to pre-auth revision and insert a legacy unowned profile
        with engine.begin() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "c8d9e0f1a2b3")

        legacy_id = uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO candidate_profiles (id, full_name) "
                    "VALUES (:id, 'Legacy Candidate')"
                ),
                {"id": legacy_id},
            )

        # 2. Upgrade to head (d1e2f3a4b5c6)
        with engine.begin() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "head")

        tables = set(inspect(engine).get_table_names(schema="public"))
        assert {"users", "auth_sessions", "candidate_profiles"}.issubset(tables)

        # Legacy profile preserved with user_id = NULL
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT full_name, user_id FROM candidate_profiles WHERE id = :id"),
                {"id": legacy_id},
            ).fetchone()
            assert row is not None
            assert row[0] == "Legacy Candidate"
            assert row[1] is None

        # 3. Create a user, claim the legacy profile, and create a session
        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, is_active) "
                    "VALUES (:id, 'owner@example.com', 'hash', true)"
                ),
                {"id": user_id},
            )
            conn.execute(
                text("UPDATE candidate_profiles SET user_id = :uid WHERE id = :pid"),
                {"uid": user_id, "pid": legacy_id},
            )
            conn.execute(
                text(
                    "INSERT INTO auth_sessions "
                    "(id, user_id, token_hash, csrf_token_hash, expires_at) "
                    "VALUES (:sid, :uid, :th, :ch, now() + interval '1 day')"
                ),
                {"sid": session_id, "uid": user_id, "th": "a" * 64, "ch": "b" * 64},
            )

        # 4. Downgrade back to c8d9e0f1a2b3: users/auth_sessions removed, legacy profile preserved
        with engine.begin() as conn:
            config.attributes["connection"] = conn
            command.downgrade(config, "c8d9e0f1a2b3")

        tables_after_down = set(inspect(engine).get_table_names(schema="public"))
        assert "users" not in tables_after_down
        assert "auth_sessions" not in tables_after_down
        assert "candidate_profiles" in tables_after_down

        with engine.connect() as conn:
            preserved = conn.execute(
                text("SELECT full_name FROM candidate_profiles WHERE id = :id"),
                {"id": legacy_id},
            ).scalar_one()
            assert preserved == "Legacy Candidate"

        # 5. Re-upgrade to head
        with engine.begin() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "head")
    finally:
        engine.dispose()
        _drop_disposable_db(url)
