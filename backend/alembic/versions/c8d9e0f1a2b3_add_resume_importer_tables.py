"""add_resume_importer_tables

Revision ID: c8d9e0f1a2b3
Revises: bdd3fb3a0174
Create Date: 2026-11-26 15:09:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c8d9e0f1a2b3"
down_revision: str | Sequence[str] | None = "bdd3fb3a0174"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "resume_documents",
        sa.Column("failure_reason", sa.String(length=200), nullable=True),
    )
    op.alter_column(
        "resume_documents",
        "parsing_status",
        existing_type=sa.VARCHAR(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
        existing_server_default=sa.text("'pending'::character varying"),
    )
    op.drop_constraint(
        op.f("ck_resume_documents_parsing_status"),
        "resume_documents",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_resume_documents_parsing_status"),
        "resume_documents",
        (
            "parsing_status IN ('pending', 'processing', 'parsed', "
            "'completed', 'completed_with_warnings', 'failed')"
        ),
    )

    op.create_table(
        "resume_extractions",
        sa.Column("resume_document_id", sa.Uuid(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("character_count", sa.BigInteger(), nullable=False),
        sa.Column("parser_name", sa.String(length=60), nullable=False),
        sa.Column("parser_version", sa.String(length=40), nullable=False),
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("extracted_storage_key", sa.String(length=500), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "page_count >= 0",
            name=op.f("ck_resume_extractions_page_count_non_negative"),
        ),
        sa.CheckConstraint(
            "word_count >= 0",
            name=op.f("ck_resume_extractions_word_count_non_negative"),
        ),
        sa.CheckConstraint(
            "character_count >= 0",
            name=op.f("ck_resume_extractions_character_count_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["resume_document_id"],
            ["resume_documents.id"],
            name=op.f("fk_resume_extractions_resume_document_id_resume_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resume_extractions")),
        sa.UniqueConstraint(
            "resume_document_id",
            name="uq_resume_extractions_resume_document_id",
        ),
    )
    op.create_index(
        "ix_resume_extractions_resume_document_id",
        "resume_extractions",
        ["resume_document_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_resume_documents_parsing_status"),
        "resume_documents",
        type_="check",
    )
    op.execute(
        "UPDATE resume_documents "
        "SET parsing_status = 'parsed' "
        "WHERE parsing_status IN ('completed', 'completed_with_warnings')"
    )
    op.create_check_constraint(
        op.f("ck_resume_documents_parsing_status"),
        "resume_documents",
        "parsing_status IN ('pending', 'processing', 'parsed', 'failed')",
    )
    op.alter_column(
        "resume_documents",
        "parsing_status",
        existing_type=sa.String(length=32),
        type_=sa.VARCHAR(length=16),
        existing_nullable=False,
        existing_server_default=sa.text("'pending'::character varying"),
    )

    op.drop_index("ix_resume_extractions_resume_document_id", table_name="resume_extractions")
    op.drop_table("resume_extractions")
    op.drop_column("resume_documents", "failure_reason")
