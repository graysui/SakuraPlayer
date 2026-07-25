from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import re
import secrets
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SecretKeyConfigurationError(ValueError):
    code = "secret_key_configuration_invalid"

    def __init__(self, reason: str) -> None:
        super().__init__(self.code)
        self.reason = reason


class SecretDecryptionError(ValueError):
    code = "secret_decryption_failed"

    def __init__(self) -> None:
        super().__init__(self.code)


class SecretKeyProvider(Protocol):
    @property
    def active_key_id(self) -> str: ...

    def get_key(self, key_id: str) -> bytes: ...


_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _validate_key_id(key_id: str) -> str:
    if not _KEY_ID.fullmatch(key_id):
        raise SecretKeyConfigurationError("key id must be 1..64 stable characters")
    return key_id


def _validate_key(key: bytes | None) -> bytes:
    if not isinstance(key, bytes) or len(key) != 32:
        raise SecretKeyConfigurationError("settings key must be exactly 32 bytes")
    return key


class InMemorySecretKeyProvider:
    def __init__(self, *, active_key_id: str, keys: Mapping[str, bytes]) -> None:
        self._active_key_id = _validate_key_id(active_key_id)
        self._keys = {
            _validate_key_id(key_id): _validate_key(key)
            for key_id, key in keys.items()
        }
        if self._active_key_id not in self._keys:
            raise SecretKeyConfigurationError("active key id is not configured")

    @property
    def active_key_id(self) -> str:
        return self._active_key_id

    def get_key(self, key_id: str) -> bytes:
        try:
            return self._keys[key_id]
        except KeyError:
            raise SecretDecryptionError from None


class SettingsSecretKeyProvider(InMemorySecretKeyProvider):
    def __init__(self, *, key_id: str, key: bytes | None) -> None:
        super().__init__(active_key_id=key_id, keys={key_id: _validate_key(key)})


@dataclass(frozen=True)
class EncryptedEnvelope:
    key_id: str
    nonce: bytes = field(repr=False)
    ciphertext: bytes = field(repr=False)


class SecretCipher:
    nonce_size = 12

    def __init__(self, key_provider: SecretKeyProvider) -> None:
        self._key_provider = key_provider

    def encrypt(self, plaintext: bytes, *, context: bytes) -> EncryptedEnvelope:
        if not isinstance(plaintext, bytes) or not isinstance(context, bytes):
            raise TypeError("plaintext and context must be bytes")
        nonce = secrets.token_bytes(self.nonce_size)
        key_id = self._key_provider.active_key_id
        ciphertext = AESGCM(self._key_provider.get_key(key_id)).encrypt(
            nonce,
            plaintext,
            context,
        )
        return EncryptedEnvelope(key_id=key_id, nonce=nonce, ciphertext=ciphertext)

    def decrypt(self, envelope: EncryptedEnvelope, *, context: bytes) -> bytes:
        if (
            not isinstance(envelope.nonce, bytes)
            or len(envelope.nonce) != self.nonce_size
            or not isinstance(envelope.ciphertext, bytes)
            or len(envelope.ciphertext) < 16
            or not isinstance(context, bytes)
        ):
            raise SecretDecryptionError
        try:
            key = self._key_provider.get_key(envelope.key_id)
            return AESGCM(key).decrypt(envelope.nonce, envelope.ciphertext, context)
        except (SecretDecryptionError, InvalidTag, ValueError, TypeError):
            raise SecretDecryptionError from None
