"""Transactional email outbox service with FOR UPDATE SKIP LOCKED leasing and retries."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.email_provider import EmailDeliveryError, EmailProvider, render_verification_email
from app.auth.exceptions import OutboxEncryptionError
from app.auth.outbox_crypto import OutboxCrypto
from app.core.config import Settings, get_settings
from app.models.email_outbox import EmailOutbox
from app.models.enums import EmailOutboxStatus

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
    ) -> None:
        now = _utcnow()
        entry.locked_at = None
        entry.lock_expires_at = None
        entry.last_error = error[:500]
        if entry.attempts >= max_attempts:
            entry.status = EmailOutboxStatus.FAILED.value
            entry.encrypted_payload = None
            entry.payload_key_version = None
        else:
            backoff_seconds = min(300, 10 * (2 ** max(0, entry.attempts - 1)))
            entry.status = EmailOutboxStatus.PENDING.value
            entry.available_at = now + timedelta(seconds=backoff_seconds)
        session.commit()

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
        if not entry.encrypted_payload or entry.payload_key_version is None:
            cls._mark_failed(
                session,
                entry=entry,
                error="missing encrypted payload",
                max_attempts=settings.email_outbox_max_attempts,
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
        entry.status = EmailOutboxStatus.SENT.value
        entry.sent_at = now
        entry.locked_at = None
        entry.lock_expires_at = None
        entry.last_error = None
        entry.encrypted_payload = None
        entry.payload_key_version = None
        session.commit()
        logger.info("Email outbox message %s delivered", entry.id)
        return True
