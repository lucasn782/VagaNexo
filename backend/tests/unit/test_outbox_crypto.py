from __future__ import annotations

import base64
import secrets

import pytest
from pydantic import SecretStr

from app.auth.exceptions import OutboxEncryptionError
from app.auth.outbox_crypto import OutboxCrypto
from app.core.config import Settings


def _settings(key: bytes | None = None, *, value: str | None = None) -> Settings:
    encoded = (
        value
        if value is not None
        else base64.urlsafe_b64encode(key or secrets.token_bytes(32)).decode()
    )
    return Settings(email_outbox_encryption_keys=SecretStr(encoded))


def test_outbox_crypto_requires_explicit_valid_key() -> None:
    with pytest.raises(OutboxEncryptionError, match="must be configured"):
        OutboxCrypto.from_settings(Settings(email_outbox_encryption_keys=SecretStr("")))
    with pytest.raises(OutboxEncryptionError, match="32 bytes"):
        OutboxCrypto.from_settings(_settings(value="dG9vLXNob3J0"))


def test_outbox_crypto_authenticates_ciphertext_nonce_aad_and_key() -> None:
    key = secrets.token_bytes(32)
    crypto = OutboxCrypto.from_settings(_settings(key))
    encrypted = crypto.encrypt_payload(
        {"token": "secret"}, outbox_id="outbox-a", template_name="email_verification"
    )
    assert crypto.decrypt_payload(
        encrypted.ciphertext_b64,
        key_version=encrypted.key_version,
        outbox_id="outbox-a",
        template_name="email_verification",
    ) == {"token": "secret"}

    raw = bytearray(base64.urlsafe_b64decode(encrypted.ciphertext_b64))
    for index in (0, 12):
        tampered = raw.copy()
        tampered[index] ^= 1
        encoded = base64.urlsafe_b64encode(tampered).decode()
        with pytest.raises(OutboxEncryptionError, match="authentication failed"):
            crypto.decrypt_payload(
                encoded,
                key_version=encrypted.key_version,
                outbox_id="outbox-a",
                template_name="email_verification",
            )

    with pytest.raises(OutboxEncryptionError, match="authentication failed"):
        crypto.decrypt_payload(
            encrypted.ciphertext_b64,
            key_version=encrypted.key_version,
            outbox_id="outbox-b",
            template_name="email_verification",
        )
    wrong_key = OutboxCrypto.from_settings(_settings())
    with pytest.raises(OutboxEncryptionError, match="authentication failed"):
        wrong_key.decrypt_payload(
            encrypted.ciphertext_b64,
            key_version=encrypted.key_version,
            outbox_id="outbox-a",
            template_name="email_verification",
        )
    with pytest.raises(OutboxEncryptionError, match="unknown outbox encryption key version"):
        crypto.decrypt_payload(
            encrypted.ciphertext_b64,
            key_version=99,
            outbox_id="outbox-a",
            template_name="email_verification",
        )
