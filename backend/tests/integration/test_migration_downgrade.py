"""Isolated integration tests for Alembic upgrade/downgrade of c8d9e0f1a2b3.

These tests run exclusively against a dedicated disposable *_test database
(vaganexo_migration_test) and never touch the principal vaganexo database or
vaganexo_test.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import IntegrityError
from tests.conftest import _test_database_url

MIGRATION_TEST_DATABASE = "vaganexo_migration_test"
BASE_REVISION = "bdd3fb3a0174"
HEAD_REVISION = "c8d9e0f1a2b3"


def _migration_test_url() -> URL:
    base = _test_database_url()
    url = base.set(database=MIGRATION_TEST_DATABASE)
    assert url.database is not None and url.database.endswith("_test")
    assert url.database != "vaganexo"
    return url


def _recreate_isolated_db(url: URL) -> None:
    admin_url = make_url(url).set(drivername="postgresql", database="postgres")
    with psycopg.connect(
        admin_url.render_as_string(hide_password=False),
        autocommit=True,
    ) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{url.database}"')


def _drop_isolated_db(url: URL) -> None:
    admin_url = make_url(url).set(drivername="postgresql", database="postgres")
    with psycopg.connect(
        admin_url.render_as_string(hide_password=False),
        autocommit=True,
    ) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)')


@pytest.fixture()
def isolated_migration_engine() -> Iterator[Engine]:
    url = _migration_test_url()
    _recreate_isolated_db(url)
    engine = create_engine(url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()
        _drop_isolated_db(url)


def _alembic_config() -> Config:
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    return Config(str(alembic_ini))


def test_downgrade_converts_new_statuses_and_re_upgrade_restores_schema(
    isolated_migration_engine: Engine,
) -> None:
    config = _alembic_config()

    # 1. Upgrade from scratch to head
    with isolated_migration_engine.begin() as conn:
        config.attributes["connection"] = conn
        command.upgrade(config, HEAD_REVISION)

    # 2. Insert a profile and resume_documents covering all 6 statuses
    profile_id = uuid.uuid4()
    statuses = [
        "pending",
        "processing",
        "parsed",
        "failed",
        "completed",
        "completed_with_warnings",
    ]
    doc_ids: dict[str, uuid.UUID] = {}

    with isolated_migration_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO candidate_profiles (id, full_name) VALUES (:id, :name)"),
            {"id": profile_id, "name": "Migration Test User"},
        )
        for index, status_value in enumerate(statuses):
            doc_id = uuid.uuid4()
            doc_ids[status_value] = doc_id
            conn.execute(
                text(
                    "INSERT INTO resume_documents "
                    "(id, candidate_profile_id, original_filename, media_type, "
                    "file_size, sha256_hash, storage_key, parsing_status, failure_reason) "
                    "VALUES (:id, :pid, :fname, 'application/pdf', 100, :sha, :skey, "
                    ":status, :reason)"
                ),
                {
                    "id": doc_id,
                    "pid": profile_id,
                    "fname": f"cv_{index}.pdf",
                    "sha": f"{index}" * 64,
                    "skey": f"uploads/{profile_id}/{doc_id}.pdf",
                    "status": status_value,
                    "reason": "text_extraction_failed" if status_value == "failed" else None,
                },
            )
            if status_value in ("completed", "completed_with_warnings"):
                conn.execute(
                    text(
                        "INSERT INTO resume_extractions "
                        "(id, resume_document_id, extracted_text, page_count, word_count, "
                        "character_count, parser_name, parser_version, warnings, "
                        "extracted_storage_key) "
                        "VALUES (:id, :doc_id, 'Sample text', 1, 2, 11, 'pymupdf', '1.0', "
                        "'[]'::jsonb, :ekey)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "doc_id": doc_id,
                        "ekey": f"extracted/{profile_id}/{doc_id}.txt",
                    },
                )

    # 3. Downgrade from c8d9e0f1a2b3 to bdd3fb3a0174
    with isolated_migration_engine.begin() as conn:
        config.attributes["connection"] = conn
        command.downgrade(config, BASE_REVISION)

    # 4. Verify downgraded state
    with isolated_migration_engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == BASE_REVISION

        rows = conn.execute(text("SELECT id, parsing_status FROM resume_documents")).fetchall()
        status_by_id = {row[0]: row[1] for row in rows}
        assert len(status_by_id) == 6
        assert status_by_id[doc_ids["pending"]] == "pending"
        assert status_by_id[doc_ids["processing"]] == "processing"
        assert status_by_id[doc_ids["parsed"]] == "parsed"
        assert status_by_id[doc_ids["failed"]] == "failed"
        assert status_by_id[doc_ids["completed"]] == "parsed"
        assert status_by_id[doc_ids["completed_with_warnings"]] == "parsed"

    inspector = inspect(isolated_migration_engine)
    assert "resume_extractions" not in inspector.get_table_names(schema="public")
    doc_columns = {col["name"]: col for col in inspector.get_columns("resume_documents")}
    assert "failure_reason" not in doc_columns
    assert doc_columns["parsing_status"]["type"].length == 16

    # Legacy constraint rejects 'completed'
    with pytest.raises(IntegrityError), isolated_migration_engine.begin() as conn:
        bad_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO resume_documents "
                "(id, candidate_profile_id, original_filename, media_type, "
                "file_size, sha256_hash, storage_key, parsing_status) "
                "VALUES (:id, :pid, 'bad.pdf', 'application/pdf', 10, :sha, :skey, 'completed')"
            ),
            {
                "id": bad_id,
                "pid": profile_id,
                "sha": "f" * 64,
                "skey": f"uploads/{profile_id}/{bad_id}.pdf",
            },
        )

    # 5. Re-upgrade back to head
    with isolated_migration_engine.begin() as conn:
        config.attributes["connection"] = conn
        command.upgrade(config, HEAD_REVISION)

    with isolated_migration_engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == HEAD_REVISION

    inspector = inspect(isolated_migration_engine)
    assert "resume_extractions" in inspector.get_table_names(schema="public")
    doc_columns = {col["name"]: col for col in inspector.get_columns("resume_documents")}
    assert "failure_reason" in doc_columns
    assert doc_columns["parsing_status"]["type"].length == 32
