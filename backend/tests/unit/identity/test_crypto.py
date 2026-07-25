from __future__ import annotations

from dataclasses import replace

import pytest

from sakuraplayer.identity.crypto import (
    EncryptedEnvelope,
    InMemorySecretKeyProvider,
    SecretCipher,
    SecretDecryptionError,
    SecretKeyConfigurationError,
    SettingsSecretKeyProvider,
)


def provider(key: bytes = b"k" * 32) -> InMemorySecretKeyProvider:
    return InMemorySecretKeyProvider(active_key_id="v1", keys={"v1": key})


def test_encrypts_with_a_random_96_bit_nonce_and_authenticated_context() -> None:
    cipher = SecretCipher(provider())

    first = cipher.encrypt(b"sensitive-cookie", context=b"cloud115.cookie")
    second = cipher.encrypt(b"sensitive-cookie", context=b"cloud115.cookie")

    assert first.key_id == "v1"
    assert len(first.nonce) == 12
    assert first.nonce != second.nonce
    assert first.ciphertext != second.ciphertext
    assert b"sensitive-cookie" not in first.ciphertext
    assert cipher.decrypt(first, context=b"cloud115.cookie") == b"sensitive-cookie"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda envelope: replace(
            envelope,
            ciphertext=envelope.ciphertext[:-1]
            + bytes([envelope.ciphertext[-1] ^ 1]),
        ),
        lambda envelope: replace(envelope, nonce=b"n" * 12),
        lambda envelope: replace(envelope, key_id="retired"),
        lambda envelope: replace(envelope, ciphertext=b""),
    ],
)
def test_rejects_tampered_or_incomplete_envelopes(mutate) -> None:
    cipher = SecretCipher(provider())
    plaintext = b"private-ai-value"
    envelope = cipher.encrypt(plaintext, context=b"ai.api_key")

    with pytest.raises(SecretDecryptionError) as error:
        cipher.decrypt(mutate(envelope), context=b"ai.api_key")

    assert error.value.code == "secret_decryption_failed"
    assert plaintext.decode("ascii") not in str(error.value)


def test_rejects_wrong_key_and_wrong_setting_context() -> None:
    envelope = SecretCipher(provider()).encrypt(
        b"secret",
        context=b"javdb.password",
    )

    with pytest.raises(SecretDecryptionError):
        SecretCipher(provider(b"z" * 32)).decrypt(
            envelope,
            context=b"javdb.password",
        )
    with pytest.raises(SecretDecryptionError):
        SecretCipher(provider()).decrypt(envelope, context=b"ai.api_key")


@pytest.mark.parametrize("key", [None, b"short", b"x" * 31, b"x" * 33])
def test_production_settings_provider_requires_one_32_byte_key(key) -> None:
    with pytest.raises(SecretKeyConfigurationError) as error:
        SettingsSecretKeyProvider(key_id="v1", key=key)

    assert error.value.code == "secret_key_configuration_invalid"


def test_envelope_rejects_invalid_nonce_without_exposing_ciphertext() -> None:
    envelope = EncryptedEnvelope(key_id="v1", nonce=b"short", ciphertext=b"secret")

    assert "secret" not in repr(envelope)
    with pytest.raises(SecretDecryptionError):
        SecretCipher(provider()).decrypt(envelope, context=b"setting")
