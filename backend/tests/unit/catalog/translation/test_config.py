from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.translation.config import (
    AiConfiguration,
    EncryptedAiConfigurationStore,
    TranslationConfigurationError,
)
from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.identity.models import Base, EncryptedSetting
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.resources.models import Movie


def store_context():
    assert Movie.__tablename__ == "movie"
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repository = EncryptedSettingRepository(
        factory,
        SecretCipher(
            InMemorySecretKeyProvider(
                active_key_id="v1",
                keys={"v1": b"k" * 32},
            )
        ),
    )
    return engine, factory, repository, EncryptedAiConfigurationStore(repository)


def test_ai_configuration_round_trip_is_atomic_and_secret_safe() -> None:
    engine, factory, _, store = store_context()
    try:
        assert store.load() is None
        saved = store.save(
            AiConfiguration(
                base_url="https://ai.example.test/root/",
                api_key="private-fixture-key",
                model=" fixture-model ",
                timeout_seconds=45,
            ),
            expected_version=0,
        )

        assert saved.version == 1
        assert saved.base_url == "https://ai.example.test/root"
        assert saved.model == "fixture-model"
        assert saved.api_key == "private-fixture-key"
        assert "private-fixture-key" not in repr(saved)
        loaded = store.load()
        assert loaded == saved
        with factory() as session:
            rows = list(session.scalars(select(EncryptedSetting)))
        assert [row.key for row in rows] == ["ai.configuration"]
        assert rows[0].public_value is None
        assert b"private-fixture-key" not in (rows[0].ciphertext or b"")
        assert b"ai.example.test" not in (rows[0].ciphertext or b"")
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "configuration",
    [
        AiConfiguration("relative", "key", "model", 60),
        AiConfiguration("ftp://ai.example.test", "key", "model", 60),
        AiConfiguration("https://user@ai.example.test", "key", "model", 60),
        AiConfiguration("https://ai.example.test?q=1", "key", "model", 60),
        AiConfiguration("https://ai.example.test/v1", "key", "model", 60),
        AiConfiguration("https://ai.example.test", "", "model", 60),
        AiConfiguration("https://ai.example.test", "key", "", 60),
        AiConfiguration("https://ai.example.test", "key", "model", 0),
        AiConfiguration("https://ai.example.test", "key", "model", 601),
    ],
)
def test_invalid_ai_configuration_is_rejected_without_network(
    configuration: AiConfiguration,
) -> None:
    engine, _, _, store = store_context()
    try:
        with pytest.raises(TranslationConfigurationError) as error:
            store.save(configuration, expected_version=0)
        assert error.value.code == "translation_not_configured"
        assert str(error.value) == "translation_not_configured"
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "payload",
    [
        b"\xff",
        json.dumps({"base_url": "https://ai.example.test"}).encode(),
        json.dumps(
            {
                "base_url": "https://ai.example.test",
                "api_key": "key",
                "model": "model",
                "timeout_seconds": 60,
                "extra": True,
            }
        ).encode(),
    ],
)
def test_malformed_encrypted_ai_payload_maps_to_stable_error(payload: bytes) -> None:
    engine, _, repository, store = store_context()
    try:
        repository.create_secret("ai.configuration", payload)
        with pytest.raises(TranslationConfigurationError) as error:
            store.load()
        assert error.value.code == "translation_not_configured"
        assert str(error.value) == "translation_not_configured"
    finally:
        engine.dispose()
