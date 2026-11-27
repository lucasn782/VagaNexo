"""add_account_lifecycle_and_outbox

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-11-27 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2f3a4b5c6d7"
down_revision: str | Sequence[str] | None = "d1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Extend users with canonical status and email_verified_at.
    # Existing active accounts become status='active' with email_verified_at=NULL
    # (never fabricated as verified), preserving backward compatibility.
    op.add_column(
        "users",
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(sa.text("UPDATE users SET status = 'disabled' WHERE is_active = false"))
    op.create_check_constraint(
        op.f("ck_users_valid_status"),
        "users",
        "status IN ('pending_verification', 'active', 'suspended', 'disabled')",
    )
    op.create_check_constraint(
        op.f("ck_users_status_matches_is_active"),
        "users",
        "(status = 'active' AND is_active = true) OR (status <> 'active' AND is_active = false)",
    )

    # 2. Single-use purpose-scoped tokens (only SHA-256 hashes persisted).
    op.create_table(
        "account_action_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_account_action_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_action_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_account_action_tokens_token_hash")),
    )
    op.create_index(
        op.f("ix_account_action_tokens_user_id_purpose"),
        "account_action_tokens",
        ["user_id", "purpose"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_action_tokens_expires_at"),
        "account_action_tokens",
        ["expires_at"],
        unique=False,
    )

    # 3. Transactional email outbox with AEAD-encrypted temporary payload.
    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("template_name", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lock_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("encrypted_payload", sa.Text(), nullable=True),
        sa.Column("payload_key_version", sa.SmallInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_email_outbox_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_outbox")),
    )
    op.create_index(
        op.f("ix_email_outbox_status_available_at"),
        "email_outbox",
        ["status", "available_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_outbox_lock_expires_at"),
        "email_outbox",
        ["lock_expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_outbox_user_id"),
        "email_outbox",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_email_outbox_user_id"), table_name="email_outbox")
    op.drop_index(op.f("ix_email_outbox_lock_expires_at"), table_name="email_outbox")
    op.drop_index(op.f("ix_email_outbox_status_available_at"), table_name="email_outbox")
    op.drop_table("email_outbox")

    op.drop_index(op.f("ix_account_action_tokens_expires_at"), table_name="account_action_tokens")
    op.drop_index(
        op.f("ix_account_action_tokens_user_id_purpose"),
        table_name="account_action_tokens",
    )
    op.drop_table("account_action_tokens")

    op.drop_constraint(op.f("ck_users_status_matches_is_active"), "users", type_="check")
    op.drop_constraint(op.f("ck_users_valid_status"), "users", type_="check")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "status")
