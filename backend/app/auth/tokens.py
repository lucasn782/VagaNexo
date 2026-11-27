"""Single-use purpose-scoped token creation and atomic consumption."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.auth.exceptions import InvalidActionTokenError
from app.auth.security import hash_token
from app.models.account_action_token import AccountActionToken
from app.models.enums import ActionTokenPurpose


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ActionTokenService:
    """Manage high-entropy single-use tokens stored exclusively as SHA-256 hashes."""

    @staticmethod
    def issue_token(
        session: Session,
        *,
        user_id: uuid.UUID,
        purpose: ActionTokenPurpose,
        ttl: timedelta,
    ) -> tuple[AccountActionToken, str]:
        now = _utcnow()
        # Revoke any prior active tokens for the same user and purpose.
        session.execute(
            update(AccountActionToken)
            .where(
                AccountActionToken.user_id == user_id,
                AccountActionToken.purpose == purpose.value,
                AccountActionToken.consumed_at.is_(None),
                AccountActionToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

        raw_token = secrets.token_urlsafe(32)
        record = AccountActionToken(
            user_id=user_id,
            purpose=purpose.value,
            token_hash=hash_token(raw_token),
            created_at=now,
            expires_at=now + ttl,
        )
        session.add(record)
        return record, raw_token

    @staticmethod
    def consume_token(
        session: Session,
        *,
        raw_token: str,
        purpose: ActionTokenPurpose,
    ) -> tuple[uuid.UUID, uuid.UUID]:
        if not raw_token or not isinstance(raw_token, str):
            raise InvalidActionTokenError()

        now = _utcnow()
        token_digest = hash_token(raw_token)
        row = session.execute(
            update(AccountActionToken)
            .where(
                AccountActionToken.token_hash == token_digest,
                AccountActionToken.purpose == purpose.value,
                AccountActionToken.consumed_at.is_(None),
                AccountActionToken.revoked_at.is_(None),
                AccountActionToken.expires_at > now,
            )
            .values(consumed_at=now)
            .returning(AccountActionToken.id, AccountActionToken.user_id)
        ).fetchone()
        if row is None:
            raise InvalidActionTokenError()
        return row[0], row[1]
