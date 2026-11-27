"""Authenticated AEAD encryption for temporary EmailOutbox payloads."""

from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.auth.exceptions import OutboxEncryptionError
from app.core.config import Settings, get_settings

_NONCE_BYTES = 12


@dataclass(frozen=True)
class EncryptedPayload:
    ciphertext_b64: str
    key_version: int


def _decode_key(raw_b64: str) -> bytes:
    try:
        decoded = base64.urlsafe_b64decode(raw_b64.encode("ascii"))
    except (ValueError, binascii.Error) as exc:
        raise OutboxEncryptionError("invalid outbox encryption key encoding") from exc
    if len(decoded) != 32:
        raise OutboxEncryptionError("outbox encryption key must decode to 32 bytes")
    return decoded


def _parse_keyring(raw_keys: str) -> dict[int, bytes]:
    cleaned = raw_keys.strip()
    if not cleaned:
        raise OutboxEncryptionError("EMAIL_OUTBOX_ENCRYPTION_KEYS must be configured")

    keyring: dict[int, bytes] = {}
    for entry in cleaned.split(","):
        item = entry.strip()
        if not item:
            continue
        if ":" in item:
            version_str, _, key_b64 = item.partition(":")
            try:
                version = int(version_str.strip())
            except ValueError as exc:
                raise OutboxEncryptionError("invalid outbox key version") from exc
            if version < 1:
                raise OutboxEncryptionError("outbox key version must be >= 1")
            keyring[version] = _decode_key(key_b64.strip())
        else:
            if 1 in keyring:
                raise OutboxEncryptionError("duplicate unversioned outbox encryption key")
            keyring[1] = _decode_key(item)

    if not keyring:
        raise OutboxEncryptionError("no valid outbox encryption keys configured")
    return keyring


class OutboxCrypto:
    """AES-256-GCM keyring supporting key versioning and AAD binding."""

    def __init__(self, keyring: dict[int, bytes]) -> None:
        if not keyring:
            raise OutboxEncryptionError("empty outbox keyring")
        self._keyring = dict(keyring)
        self._active_version = max(self._keyring.keys())

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> OutboxCrypto:
        current = settings or get_settings()
        keyring = _parse_keyring(current.email_outbox_encryption_keys.get_secret_value())
        return cls(keyring)

    @staticmethod
    def _build_aad(outbox_id: str, template_name: str) -> bytes:
        return f"email_outbox:{outbox_id}:{template_name}".encode()

    def encrypt_payload(
        self,
        payload: dict[str, str],
        *,
        outbox_id: str,
        template_name: str,
    ) -> EncryptedPayload:
        key = self._keyring[self._active_version]
        nonce = os.urandom(_NONCE_BYTES)
        plaintext = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        aad = self._build_aad(outbox_id, template_name)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
        encoded = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
        return EncryptedPayload(ciphertext_b64=encoded, key_version=self._active_version)

    def decrypt_payload(
        self,
        ciphertext_b64: str,
        *,
        key_version: int,
        outbox_id: str,
        template_name: str,
    ) -> dict[str, str]:
        key = self._keyring.get(key_version)
        if key is None:
            raise OutboxEncryptionError("unknown outbox encryption key version")
        try:
            raw = base64.urlsafe_b64decode(ciphertext_b64.encode("ascii"))
        except (ValueError, binascii.Error) as exc:
            raise OutboxEncryptionError("corrupted outbox payload encoding") from exc
        if len(raw) <= _NONCE_BYTES:
            raise OutboxEncryptionError("corrupted outbox payload length")
        nonce, ciphertext = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
        aad = self._build_aad(outbox_id, template_name)
        try:
            plaintext = AESGCM(key).decrypt(nonce, ciphertext, aad)
        except InvalidTag as exc:
            raise OutboxEncryptionError("outbox payload authentication failed") from exc
        try:
            data = json.loads(plaintext.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OutboxEncryptionError("corrupted outbox payload JSON") from exc
        if not isinstance(data, dict):
            raise OutboxEncryptionError("invalid outbox payload structure")
        return {str(k): str(v) for k, v in data.items()}
