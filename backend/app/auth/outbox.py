"""Transactional email outbox service with FOR UPDATE SKIP LOCKED leasing and retries."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.auth.email_provider import EmailDeliveryError, EmailProvider, render_verification_email
from app.auth.exceptions import OutboxEncryptionError
from app.auth.outbox_crypto import OutboxCrypto
from app.auth.security import hash_token
from app.core.config import Settings, get_settings
from app.models.account_action_token import AccountActionToken
from app.models.email_outbox import EmailOutbox
from app.models.enums import AccountStatus, ActionTokenPurpose, EmailOutboxStatus
from app.models.user import User

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class EmailOutboxService:
    """Persist encrypted email jobs atomically and deliver them idempotently."""

    @staticmethod
    def enqueue_verification_email(
        session: Session,
        *,
        user_id: uuid.UUID,
        recipient_email: str,
        raw_token: str,
        settings: Settings | None = None,
    ) -> EmailOutbox:
        current = settings or get_settings()
        crypto = OutboxCrypto.from_settings(current)
        outbox_id = uuid.uuid4()
        template_name = "email_verification"
        encrypted = crypto.encrypt_payload(
            {"token": raw_token},
            outbox_id=str(outbox_id),
            template_name=template_name,
        )
        now = _utcnow()
        entry = EmailOutbox(
            id=outbox_id,
            user_id=user_id,
            recipient_email=recipient_email,
            template_name=template_name,
            status=EmailOutboxStatus.PENDING.value,
            attempts=0,
            created_at=now,
            available_at=now,
            encrypted_payload=encrypted.ciphertext_b64,
            payload_key_version=encrypted.key_version,
        )
        session.add(entry)
        return entry

    @staticmethod
    def claim_message(
        session: Session,
        *,
        outbox_id: uuid.UUID | None = None,
        settings: Settings | None = None,
    ) -> EmailOutbox | None:
        current = settings or get_settings()
        now = _utcnow()
        stmt = select(EmailOutbox).where(
            EmailOutbox.attempts < current.email_outbox_max_attempts,
            or_(
                (EmailOutbox.status == EmailOutboxStatus.PENDING.value)
                & (EmailOutbox.available_at <= now),
                (EmailOutbox.status == EmailOutboxStatus.SENDING.value)
                & (EmailOutbox.lock_expires_at.is_not(None))
                & (EmailOutbox.lock_expires_at <= now),
            ),
        )
        if outbox_id is not None:
            stmt = stmt.where(EmailOutbox.id == outbox_id)
        else:
            stmt = stmt.order_by(EmailOutbox.available_at.asc(), EmailOutbox.created_at.asc())

        stmt = stmt.limit(1).with_for_update(skip_locked=True)
        entry = session.scalar(stmt)
        if entry is None:
            return None

        entry.status = EmailOutboxStatus.SENDING.value
        entry.locked_at = now
        entry.claim_token = uuid.uuid4()
        entry.lock_expires_at = now + timedelta(seconds=current.email_outbox_lease_seconds)
        entry.attempts += 1
        session.commit()
        session.refresh(entry)
        return entry

    @classmethod
    def process_message(
        cls,
        session: Session,
        *,
        outbox_id: uuid.UUID | None,
        provider: EmailProvider,
        settings: Settings | None = None,
    ) -> bool:
        current = settings or get_settings()
        entry = cls.claim_message(session, outbox_id=outbox_id, settings=current)
        if entry is None:
            return False
        return cls._deliver_claimed_entry(
            session,
            entry=entry,
            provider=provider,
            settings=current,
        )

    @staticmethod
    def _mark_failed(
        session: Session,
        *,
        entry: EmailOutbox,
        error: str,
        max_attempts: int,
        claim_token: uuid.UUID,
    ) -> bool:
        now = _utcnow()
        values: dict[str, object] = {
            "locked_at": None,
            "lock_expires_at": None,
            "claim_token": None,
            "last_error": error[:500],
        }
        if entry.attempts >= max_attempts:
            values.update(
                status=EmailOutboxStatus.FAILED.value,
                encrypted_payload=None,
                payload_key_version=None,
            )
        else:
            backoff_seconds = min(300, 10 * (2 ** max(0, entry.attempts - 1)))
            values.update(
                status=EmailOutboxStatus.PENDING.value,
                available_at=now + timedelta(seconds=backoff_seconds),
            )
        result = session.execute(
            update(EmailOutbox)
            .where(
                EmailOutbox.id == entry.id,
                EmailOutbox.status == EmailOutboxStatus.SENDING.value,
                EmailOutbox.claim_token == claim_token,
            )
            .values(**values)
            .returning(EmailOutbox.id)
        )
        session.commit()
        return result.scalar_one_or_none() is not None

    @classmethod
    def sweep_pending(
        cls,
        session: Session,
        *,
        provider: EmailProvider,
        settings: Settings | None = None,
        batch_size: int = 50,
    ) -> int:
        delivered = 0
        for _ in range(batch_size):
            entry = cls.claim_message(session, outbox_id=None, settings=settings)
            if entry is None:
                break
            # Release claim? No — process directly using the already claimed entry!
            if cls._deliver_claimed_entry(
                session,
                entry=entry,
                provider=provider,
                settings=settings or get_settings(),
            ):
                delivered += 1
        return delivered

    @classmethod
    def _deliver_claimed_entry(
        cls,
        session: Session,
        *,
        entry: EmailOutbox,
        provider: EmailProvider,
        settings: Settings,
    ) -> bool:
        claim_token = entry.claim_token
        if claim_token is None:
            return False
        if not entry.encrypted_payload or entry.payload_key_version is None:
            cls._mark_failed(
                session,
                entry=entry,
                error="missing encrypted payload",
                max_attempts=settings.email_outbox_max_attempts,
                claim_token=claim_token,
            )
            return False

        try:
            crypto = OutboxCrypto.from_settings(settings)
            payload = crypto.decrypt_payload(
                entry.encrypted_payload,
                key_version=entry.payload_key_version,
                outbox_id=str(entry.id),
                template_name=entry.template_name,
            )
            raw_token = payload.get("token")
            if not raw_token:
                raise OutboxEncryptionError("missing token in decrypted outbox payload")

            # Hold the account row lock through delivery. Issuance and token
            # consumption use the same User -> ActionToken lock order, so a
            # revoked, consumed, expired, or no-longer-pending message cannot
            # be sent after its purpose has ended.
            user = session.scalar(
                select(User)
                .where(User.id == entry.user_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            token_is_current = False
            if user is not None and user.status == AccountStatus.PENDING_VERIFICATION.value:
                token_is_current = (
                    session.scalar(
                        select(AccountActionToken.id).where(
                            AccountActionToken.user_id == user.id,
                            AccountActionToken.purpose
                            == ActionTokenPurpose.EMAIL_VERIFICATION.value,
                            AccountActionToken.token_hash == hash_token(raw_token),
                            AccountActionToken.consumed_at.is_(None),
                            AccountActionToken.revoked_at.is_(None),
                            AccountActionToken.expires_at > _utcnow(),
                        )
                    )
                    is not None
                )
            if not token_is_current:
                result = session.execute(
                    update(EmailOutbox)
                    .where(
                        EmailOutbox.id == entry.id,
                        EmailOutbox.status == EmailOutboxStatus.SENDING.value,
                        EmailOutbox.claim_token == claim_token,
                    )
                    .values(
                        status=EmailOutboxStatus.FAILED.value,
                        locked_at=None,
                        lock_expires_at=None,
                        claim_token=None,
                        last_error="verification message is no longer eligible",
                        encrypted_payload=None,
                        payload_key_version=None,
                    )
                )
                session.commit()
                return False

            message = render_verification_email(
                recipient_email=entry.recipient_email,
                raw_token=raw_token,
                base_url=settings.app_public_base_url,
                ttl_hours=settings.email_verification_ttl_hours,
            )
            provider.send(message)
        except (EmailDeliveryError, OutboxEncryptionError) as exc:
            cls._mark_failed(
                session,
                entry=entry,
                error=str(exc),
                max_attempts=settings.email_outbox_max_attempts,
                claim_token=claim_token,
            )
            logger.warning(
                "Email outbox delivery failed for message %s (attempt %s/%s): %s",
                entry.id,
                entry.attempts,
                settings.email_outbox_max_attempts,
                str(exc),
            )
            return False

        now = _utcnow()
        result = session.execute(
            update(EmailOutbox)
            .where(
                EmailOutbox.id == entry.id,
                EmailOutbox.status == EmailOutboxStatus.SENDING.value,
                EmailOutbox.claim_token == claim_token,
            )
            .values(
                status=EmailOutboxStatus.SENT.value,
                sent_at=now,
                locked_at=None,
                lock_expires_at=None,
                claim_token=None,
                last_error=None,
                encrypted_payload=None,
                payload_key_version=None,
            )
            .returning(EmailOutbox.id)
        )
        session.commit()
        if result.scalar_one_or_none() is None:
            logger.info("Email outbox message %s was finalized by a newer lease", entry.id)
            return False
        logger.info("Email outbox message %s delivered", entry.id)
        return True
