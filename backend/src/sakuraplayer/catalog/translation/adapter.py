from __future__ import annotations

import json
import logging
import re
import secrets
import time
from collections import Counter
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from sakuraplayer.catalog.translation.config import AiConfigurationSnapshot
from sakuraplayer.catalog.translation.guard import (
    ProtectedFields,
    TranslationGuardrailError,
)

PROMPT_VERSION = "sakuraplayer-zh-v3"
_OUTPUT_SCHEMA_EXAMPLE = '{"schema_version":1,"translated_text":"..."}'
SYSTEM_PROMPT = (
    "Translate only the source_text value into Simplified Chinese. Return exactly "
    f"one JSON object with this only allowed shape: {_OUTPUT_SCHEMA_EXAMPLE}. "
    "Preserve every placeholder token matching [[SP_XXXXXXXX_0000]] exactly, "
    "including brackets, spelling, and count. Do not return kind/source_text, "
    "Markdown, code fences, explanations, or any extra fields."
)
MAX_TEXT_CHARACTERS = 32_000
MAX_REQUEST_BYTES = 512 * 1024
MAX_RESPONSE_BYTES = 256 * 1024
MAX_OUTPUT_TOKENS = 65_536
_OUTPUT_TOKEN_RESERVE = 64
_MIN_OUTPUT_TOKENS: dict[str, int] = {
    "movie_title": 128,
    "movie_description": 256,
}
_PLACEHOLDER_PATTERN = re.compile(r"\[\[SP_[A-F0-9]{8}_[0-9]{4}\]\]")
_SAFE_TRACE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SILICONFLOW_HOST = "api.siliconflow.cn"
_SILICONFLOW_QWEN35_PREFIX = "qwen/qwen3.5-"
_LOGGER = logging.getLogger(__name__)
TranslationKind = Literal["movie_title", "movie_description"]


class TranslationAdapterError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        category: str = "unspecified",
        http_status: int | None = None,
        trace_id: str | None = None,
        elapsed_ms: int | None = None,
    ) -> None:
        self.code = code
        self.category = category
        self.http_status = http_status
        self.trace_id = trace_id
        self.elapsed_ms = elapsed_ms
        super().__init__(code)


@dataclass(frozen=True)
class TranslationRequest:
    kind: TranslationKind
    source_text: str
    protected: ProtectedFields


@dataclass(frozen=True)
class TranslationResult:
    translated_text: str


@dataclass(frozen=True)
class _RawResponse:
    content: bytes
    trace_id: str | None


@dataclass(frozen=True)
class _ProtectedSource:
    text: str
    replacements: tuple[tuple[str, str], ...]


class _OutputPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1]
    translated_text: str = Field(min_length=1, max_length=MAX_TEXT_CHARACTERS)

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

    finish_reason: str
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
                _endpoint(configuration.base_url, "models"),
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
        protected_source = _protect_source(request.source_text, request.protected)
        body = self._body(request, configuration, protected_source.text)
        encoded = json.dumps(
            body,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(encoded) > MAX_REQUEST_BYTES:
            raise TranslationAdapterError("translation_input_too_large")
        started = time.monotonic()
        raw: _RawResponse | None = None
        try:
            raw = self._post(encoded, configuration)
            output = self._parse(raw)
            translated_text = _restore_protected(
                output.translated_text,
                protected_source.replacements,
            )
        except TranslationGuardrailError:
            error = TranslationAdapterError(
                "translation_guardrail_failed",
                category="protected_mismatch",
                trace_id=raw.trace_id if raw is not None else None,
            )
            self._log_failure(error, started)
            raise error from None
        except httpx.TimeoutException:
            error = TranslationAdapterError(
                "translation_upstream_error",
                category="timeout",
            )
            self._log_failure(error, started)
            raise error from None
        except httpx.HTTPError:
            error = TranslationAdapterError(
                "translation_upstream_error",
                category="network",
            )
            self._log_failure(error, started)
            raise error from None
        except TranslationAdapterError as error:
            self._log_failure(error, started)
            raise
        return TranslationResult(translated_text=translated_text)

    def _post(
        self,
        body: bytes,
        configuration: AiConfigurationSnapshot,
    ) -> _RawResponse:
        endpoint = _endpoint(configuration.base_url, "chat/completions")
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
            trace_id = _safe_trace_id(response.headers.get("x-siliconcloud-trace-id"))
            if response.status_code != 200:
                raise TranslationAdapterError(
                    "translation_upstream_error",
                    category="http_status",
                    http_status=response.status_code,
                    trace_id=trace_id,
                )
            content = bytearray()
            for chunk in response.iter_bytes():
                if len(chunk) > MAX_RESPONSE_BYTES - len(content):
                    raise TranslationAdapterError(
                        "translation_guardrail_failed",
                        category="response_too_large",
                        trace_id=trace_id,
                    )
                content.extend(chunk)
        return _RawResponse(content=bytes(content), trace_id=trace_id)

    @staticmethod
    def _body(
        request: TranslationRequest,
        configuration: AiConfigurationSnapshot,
        source_text: str,
    ) -> dict[str, object]:
        user_payload = {
            "schema_version": 1,
            "kind": request.kind,
            "source_text": source_text,
        }
        body: dict[str, object] = {
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
            "max_tokens": _output_token_limit(request.kind, source_text),
        }
        if _uses_siliconflow_qwen35_profile(configuration):
            body["enable_thinking"] = False
        return body

    @staticmethod
    def _parse(raw: _RawResponse) -> _OutputPayload:
        try:
            envelope = _ChatResponse.model_validate_json(raw.content)
        except (ValidationError, UnicodeDecodeError):
            raise TranslationAdapterError(
                "translation_guardrail_failed",
                category="response_envelope",
                trace_id=raw.trace_id,
            ) from None
        choice = envelope.choices[0]
        if choice.finish_reason != "stop":
            raise TranslationAdapterError(
                "translation_guardrail_failed",
                category="finish_reason",
                trace_id=raw.trace_id,
            )
        try:
            content = json.loads(choice.message.content)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
            raise TranslationAdapterError(
                "translation_guardrail_failed",
                category="content_json",
                trace_id=raw.trace_id,
            ) from None
        try:
            return _OutputPayload.model_validate(content)
        except ValidationError:
            raise TranslationAdapterError(
                "translation_guardrail_failed",
                category="output_schema",
                trace_id=raw.trace_id,
            ) from None

    @staticmethod
    def _log_failure(error: TranslationAdapterError, started: float) -> None:
        error.elapsed_ms = max(0, round((time.monotonic() - started) * 1000))
        parts = [
            "translation_provider_failed",
            f"category={error.category}",
            f"elapsed_ms={error.elapsed_ms}",
        ]
        if error.http_status is not None:
            parts.append(f"http_status={error.http_status}")
        if error.trace_id is not None:
            parts.append(f"trace_id={error.trace_id}")
        _LOGGER.warning(" ".join(parts))


def _endpoint(base_url: str, path: str) -> str:
    normalized = base_url.rstrip("/")
    if urlsplit(normalized).path.rstrip("/").endswith("/v1"):
        return f"{normalized}/{path}"
    return f"{normalized}/v1/{path}"


def _uses_siliconflow_qwen35_profile(
    configuration: AiConfigurationSnapshot,
) -> bool:
    try:
        hostname = urlsplit(configuration.base_url).hostname
    except ValueError:
        return False
    return (
        hostname is not None
        and hostname.casefold() == _SILICONFLOW_HOST
        and configuration.model.strip()
        .casefold()
        .startswith(_SILICONFLOW_QWEN35_PREFIX)
    )


def _output_token_limit(kind: TranslationKind, source_text: str) -> int:
    estimated = ((len(source_text) * 5 + 3) // 4) + _OUTPUT_TOKEN_RESERVE
    return min(
        MAX_OUTPUT_TOKENS,
        max(_MIN_OUTPUT_TOKENS[kind], estimated),
    )


def _protect_source(source_text: str, protected: ProtectedFields) -> _ProtectedSource:
    values = (
        protected.number,
        *protected.actors,
        protected.maker,
        protected.series,
        *protected.tags,
    )
    candidates: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        stripped = value.strip()
        if not stripped or len(stripped) > len(source_text):
            continue
        key = " ".join(stripped.split()).casefold()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(stripped)
    if not candidates:
        return _ProtectedSource(source_text, ())

    candidates.sort(key=len, reverse=True)
    patterns = [
        r"\s+".join(re.escape(part) for part in re.split(r"\s+", value))
        for value in candidates
    ]
    matcher = re.compile("|".join(f"(?:{part})" for part in patterns), re.IGNORECASE)
    nonce = secrets.token_hex(4).upper()
    while f"[[SP_{nonce}_" in source_text:
        nonce = secrets.token_hex(4).upper()
    replacements: list[tuple[str, str]] = []

    def replace(match: re.Match[str]) -> str:
        token = f"[[SP_{nonce}_{len(replacements):04d}]]"
        replacements.append((token, match.group(0)))
        return token

    text = matcher.sub(replace, source_text)
    return _ProtectedSource(text, tuple(replacements))


def _restore_protected(
    translated_text: str,
    replacements: tuple[tuple[str, str], ...],
) -> str:
    expected = Counter(token for token, _ in replacements)
    returned = Counter(_PLACEHOLDER_PATTERN.findall(translated_text))
    if returned != expected:
        raise TranslationGuardrailError
    restored = translated_text
    for token, value in replacements:
        restored = restored.replace(token, value)
    if len(restored) > MAX_TEXT_CHARACTERS:
        raise TranslationGuardrailError
    return restored


def _safe_trace_id(value: str | None) -> str | None:
    if value is None or _SAFE_TRACE_ID.fullmatch(value) is None:
        return None
    return value


__all__ = [
    "MAX_RESPONSE_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_TEXT_CHARACTERS",
    "MAX_OUTPUT_TOKENS",
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "OpenAiTranslationAdapter",
    "TranslationAdapterError",
    "TranslationRequest",
    "TranslationResult",
]
