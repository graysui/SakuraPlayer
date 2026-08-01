from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from sakuraplayer.catalog.translation.config import AiConfigurationSnapshot
from sakuraplayer.catalog.translation.guard import (
    ProtectedFields,
    TranslationGuardrailError,
    require_unchanged_protected,
)

PROMPT_VERSION = "sakuraplayer-zh-v1"
SYSTEM_PROMPT = (
    "Translate only source_text into Simplified Chinese. Return exactly one JSON "
    "object matching schema_version 1. Copy protected without changing, omitting, "
    "or adding values. Never translate identifiers, actor names, maker, series, "
    "or tags."
)
MAX_TEXT_CHARACTERS = 32_000
MAX_REQUEST_BYTES = 512 * 1024
MAX_RESPONSE_BYTES = 256 * 1024
TranslationKind = Literal["movie_title", "movie_description", "actor_bio"]


class TranslationAdapterError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class TranslationRequest:
    kind: TranslationKind
    source_text: str
    protected: ProtectedFields


@dataclass(frozen=True)
class TranslationResult:
    translated_text: str


class _ProtectedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    number: str
    actors: list[str]
    maker: str | None
    series: str | None
    tags: list[str]


class _OutputPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1]
    translated_text: str = Field(min_length=1, max_length=MAX_TEXT_CHARACTERS)
    protected: _ProtectedPayload

    @field_validator("translated_text")
    @classmethod
    def reject_blank_translation(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("blank translation")
        return value


class _Message(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    content: str


class _Choice(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    message: _Message


class _ChatResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    choices: list[_Choice] = Field(min_length=1)


class OpenAiTranslationAdapter:
    def __init__(self, http_client: httpx.Client) -> None:
        self._http_client = http_client

    def probe(self, configuration: AiConfigurationSnapshot) -> None:
        try:
            with self._http_client.stream(
                "GET",
                f"{configuration.base_url}/v1/models",
                headers={"Authorization": f"Bearer {configuration.api_key}"},
                timeout=min(configuration.timeout_seconds, 30),
            ) as response:
                if response.status_code in {401, 403}:
                    raise TranslationAdapterError("translation_credentials_invalid")
                if response.status_code != 200:
                    raise TranslationAdapterError("translation_upstream_error")
        except TranslationAdapterError:
            raise
        except httpx.HTTPError:
            raise TranslationAdapterError("translation_upstream_error") from None

    def translate(
        self,
        request: TranslationRequest,
        configuration: AiConfigurationSnapshot,
    ) -> TranslationResult:
        if not request.source_text or len(request.source_text) > MAX_TEXT_CHARACTERS:
            raise TranslationAdapterError("translation_input_too_large")
        body = self._body(request, configuration)
        encoded = json.dumps(
            body,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(encoded) > MAX_REQUEST_BYTES:
            raise TranslationAdapterError("translation_input_too_large")
        try:
            raw = self._post(encoded, configuration)
        except httpx.HTTPError:
            raise TranslationAdapterError("translation_upstream_error") from None
        output = self._parse(raw)
        try:
            require_unchanged_protected(
                request.protected,
                ProtectedFields(
                    number=output.protected.number,
                    actors=tuple(output.protected.actors),
                    maker=output.protected.maker,
                    series=output.protected.series,
                    tags=tuple(output.protected.tags),
                ),
            )
        except TranslationGuardrailError:
            raise TranslationAdapterError("translation_guardrail_failed") from None
        return TranslationResult(translated_text=output.translated_text)

    def _post(
        self,
        body: bytes,
        configuration: AiConfigurationSnapshot,
    ) -> bytes:
        endpoint = f"{configuration.base_url}/v1/chat/completions"
        with self._http_client.stream(
            "POST",
            endpoint,
            headers={
                "Authorization": f"Bearer {configuration.api_key}",
                "Content-Type": "application/json",
            },
            content=body,
            timeout=configuration.timeout_seconds,
        ) as response:
            if response.status_code != 200:
                raise TranslationAdapterError("translation_upstream_error")
            content = bytearray()
            for chunk in response.iter_bytes():
                if len(chunk) > MAX_RESPONSE_BYTES - len(content):
                    raise TranslationAdapterError("translation_guardrail_failed")
                content.extend(chunk)
        return bytes(content)

    @staticmethod
    def _body(
        request: TranslationRequest,
        configuration: AiConfigurationSnapshot,
    ) -> dict[str, object]:
        user_payload = {
            "schema_version": 1,
            "kind": request.kind,
            "source_text": request.source_text,
            "protected": {
                "number": request.protected.number,
                "actors": list(request.protected.actors),
                "maker": request.protected.maker,
                "series": request.protected.series,
                "tags": list(request.protected.tags),
            },
        }
        return {
            "model": configuration.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        user_payload,
                        ensure_ascii=True,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                },
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

    @staticmethod
    def _parse(raw: bytes) -> _OutputPayload:
        try:
            envelope = _ChatResponse.model_validate_json(raw)
            content = json.loads(envelope.choices[0].message.content)
            return _OutputPayload.model_validate(content)
        except (ValidationError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
            raise TranslationAdapterError("translation_guardrail_failed") from None


__all__ = [
    "MAX_RESPONSE_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_TEXT_CHARACTERS",
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "OpenAiTranslationAdapter",
    "TranslationAdapterError",
    "TranslationRequest",
    "TranslationResult",
]
