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
        # 1. Upgrade to the auth base and insert pre-lifecycle records.
        with engine.begin() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "d1e2f3a4b5c6")

        legacy_id = uuid.uuid4()
        user_id = uuid.uuid4()
        inactive_user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO candidate_profiles (id, full_name) "
                    "VALUES (:id, 'Legacy Candidate')"
                ),
                {"id": legacy_id},
            )
            conn.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, is_active) "
                    "VALUES (:id, 'owner@example.com', 'hash', true), "
                    "(:inactive_id, 'disabled@example.com', 'hash', false)"
                ),
                {"id": user_id, "inactive_id": inactive_user_id},
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

        # 2. Upgrade through account lifecycle and verify the legacy mapping.
        with engine.begin() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "head")

        tables = set(inspect(engine).get_table_names(schema="public"))
        assert {
            "users",
            "auth_sessions",
            "candidate_profiles",
            "account_action_tokens",
            "email_outbox",
        }.issubset(tables)

        with engine.connect() as conn:
            status_map = dict(conn.execute(text("SELECT email, status FROM users")).fetchall())
            assert status_map == {
                "owner@example.com": "active",
                "disabled@example.com": "disabled",
            }
            assert (
                conn.execute(
                    text("SELECT count(*) FROM users WHERE email_verified_at IS NOT NULL")
                ).scalar_one()
                == 0
            )

        # Legacy profile preserved with user_id = NULL
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT full_name, user_id FROM candidate_profiles WHERE id = :id"),
                {"id": legacy_id},
            ).fetchone()
            assert row is not None
            assert row[0] == "Legacy Candidate"
            assert row[1] == user_id

        # 3. Downgrade only the new revision; legacy users, sessions and profiles remain.
        with engine.begin() as conn:
            config.attributes["connection"] = conn
            command.downgrade(config, "d1e2f3a4b5c6")

        tables_after_down = set(inspect(engine).get_table_names(schema="public"))
        assert "users" in tables_after_down
        assert "auth_sessions" in tables_after_down
        assert "account_action_tokens" not in tables_after_down
        assert "email_outbox" not in tables_after_down
        assert "candidate_profiles" in tables_after_down

        with engine.connect() as conn:
            preserved = conn.execute(
                text("SELECT full_name FROM candidate_profiles WHERE id = :id"),
                {"id": legacy_id},
            ).scalar_one()
            assert preserved == "Legacy Candidate"
            assert (
                conn.execute(
                    text("SELECT count(*) FROM auth_sessions WHERE id = :sid"),
                    {"sid": session_id},
                ).scalar_one()
                == 1
            )
            assert (
                conn.execute(
                    text("SELECT count(*) FROM users WHERE id IN (:uid, :inactive_id)"),
                    {"uid": user_id, "inactive_id": inactive_user_id},
                ).scalar_one()
                == 2
            )

        # 4. Re-upgrade maps the same legacy users while preserving existing data.
        with engine.begin() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "head")

        with engine.connect() as conn:
            assert dict(conn.execute(text("SELECT email, status FROM users")).fetchall()) == {
                "owner@example.com": "active",
                "disabled@example.com": "disabled",
            }

        # 5. Downgrade the older auth revision and keep the legacy profile.
        with engine.begin() as conn:
            config.attributes["connection"] = conn
            command.downgrade(config, "c8d9e0f1a2b3")
        assert "users" not in set(inspect(engine).get_table_names(schema="public"))
        assert "candidate_profiles" in set(inspect(engine).get_table_names(schema="public"))
    finally:
        engine.dispose()
        _drop_disposable_db(url)
