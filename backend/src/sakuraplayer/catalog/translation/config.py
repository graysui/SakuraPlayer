from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from sakuraplayer.identity.secrets import EncryptedSettingRepository

_CONFIGURATION_KEY = "ai.configuration"


class TranslationConfigurationError(RuntimeError):
    code = "translation_not_configured"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True)
class AiConfiguration:
    base_url: str
    api_key: str = field(repr=False)
    model: str
    timeout_seconds: int


@dataclass(frozen=True)
class AiConfigurationSnapshot:
    base_url: str
    api_key: str = field(repr=False)
    model: str
    timeout_seconds: int
    version: int


class _ConfigurationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    base_url: str
    api_key: str
    model: str
    timeout_seconds: int

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized or len(normalized) > 2048:
            raise ValueError("invalid AI base URL")
        parsed = urlsplit(normalized)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("invalid AI base URL")
        return normalized

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str) -> str:
        if not value or len(value.encode("utf-8")) > 8192:
            raise ValueError("invalid AI API key")
        return value

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        normalized = value.strip()
        if not 1 <= len(normalized) <= 255:
            raise ValueError("invalid AI model")
        return normalized

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: int) -> int:
        if not 1 <= value <= 600:
            raise ValueError("invalid AI timeout")
        return value


class EncryptedAiConfigurationStore:
    def __init__(self, repository: EncryptedSettingRepository) -> None:
        self._repository = repository

    def save(
        self,
        configuration: AiConfiguration,
        *,
        expected_version: int,
    ) -> AiConfigurationSnapshot:
        payload = self._validate(configuration.__dict__)
        encoded = json.dumps(
            payload.model_dump(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        saved = self._repository.create_or_compare_and_set_secret(
            _CONFIGURATION_KEY,
            expected_version=expected_version,
            value=encoded,
        )
        return self._snapshot(payload, version=saved.version)

    def load(self) -> AiConfigurationSnapshot | None:
        setting = self._repository.get_secret(_CONFIGURATION_KEY)
        if setting is None:
            return None
        try:
            raw = json.loads(setting.value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise TranslationConfigurationError from None
        payload = self._validate(raw)
        return self._snapshot(payload, version=setting.version)

    def clear(self, *, expected_version: int) -> None:
        self._repository.delete_secret(
            _CONFIGURATION_KEY,
            expected_version=expected_version,
        )

    @staticmethod
    def _validate(value: object) -> _ConfigurationPayload:
        try:
            return _ConfigurationPayload.model_validate(value)
        except ValidationError:
            raise TranslationConfigurationError from None

    @staticmethod
    def _snapshot(
        payload: _ConfigurationPayload,
        *,
        version: int,
    ) -> AiConfigurationSnapshot:
        return AiConfigurationSnapshot(
            base_url=payload.base_url,
            api_key=payload.api_key,
            model=payload.model,
            timeout_seconds=payload.timeout_seconds,
            version=version,
        )


__all__ = [
    "AiConfiguration",
    "AiConfigurationSnapshot",
    "EncryptedAiConfigurationStore",
    "TranslationConfigurationError",
]
