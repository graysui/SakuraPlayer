from __future__ import annotations

import json

import httpx
import pytest

from sakuraplayer.catalog.translation.adapter import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    OpenAiTranslationAdapter,
    TranslationAdapterError,
    TranslationRequest,
)
from sakuraplayer.catalog.translation.config import AiConfigurationSnapshot
from sakuraplayer.catalog.translation.guard import ProtectedFields


def configuration() -> AiConfigurationSnapshot:
    return AiConfigurationSnapshot(
        base_url="https://ai.example.test/root",
        api_key="private-fixture-key",
        model="fixture-model",
        timeout_seconds=45,
        version=2,
    )


def request() -> TranslationRequest:
    return TranslationRequest(
        kind="movie_title",
        source_text="Fixture Original Title",
        protected=ProtectedFields(
            number="ABP-123",
            actors=("Actor One", "Actor Two"),
            maker="Fixture Maker",
            series=None,
            tags=("Drama", "Featured"),
        ),
    )


def response_content(**overrides) -> dict:
    value = {
        "schema_version": 1,
        "translated_text": "夹具中文标题",
        "protected": {
            "number": "abp-123",
            "actors": [" actor two ", "ACTOR ONE"],
            "maker": "fixture maker",
            "series": None,
            "tags": ["featured", "drama"],
        },
    }
    value.update(overrides)
    return value


def chat_response(content: object) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": json.dumps(content)}}]},
    )


def timeout_response(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("fixture timeout", request=request)


def test_adapter_uses_frozen_prompt_and_strict_single_field_json() -> None:
    seen: list[httpx.Request] = []

    def handler(outbound: httpx.Request) -> httpx.Response:
        seen.append(outbound)
        return chat_response(response_content())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        result = OpenAiTranslationAdapter(client).translate(
            request(),
            configuration(),
        )
    finally:
        client.close()

    assert result.translated_text == "夹具中文标题"
    assert PROMPT_VERSION == "sakuraplayer-zh-v1"
    assert len(seen) == 1
    outbound = seen[0]
    assert str(outbound.url) == "https://ai.example.test/root/v1/chat/completions"
    assert outbound.headers["Authorization"] == "Bearer private-fixture-key"
    body = json.loads(outbound.content)
    assert body["model"] == "fixture-model"
    assert body["temperature"] == 0
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    user = json.loads(body["messages"][1]["content"])
    assert user == {
        "schema_version": 1,
        "kind": "movie_title",
        "source_text": "Fixture Original Title",
        "protected": {
            "number": "ABP-123",
            "actors": ["Actor One", "Actor Two"],
            "maker": "Fixture Maker",
            "series": None,
            "tags": ["Drama", "Featured"],
        },
    }


@pytest.mark.parametrize(
    ("handler", "code"),
    [
        (lambda request: httpx.Response(401), "translation_upstream_error"),
        (timeout_response, "translation_upstream_error"),
        (
            lambda request: httpx.Response(200, content=b"not-json"),
            "translation_guardrail_failed",
        ),
        (
            lambda request: httpx.Response(200, json={"choices": []}),
            "translation_guardrail_failed",
        ),
        (
            lambda request: chat_response("not-an-object"),
            "translation_guardrail_failed",
        ),
        (
            lambda request: chat_response(response_content(extra=True)),
            "translation_guardrail_failed",
        ),
        (
            lambda request: chat_response(response_content(translated_text="")),
            "translation_guardrail_failed",
        ),
        (
            lambda request: chat_response(response_content(translated_text="   \t")),
            "translation_guardrail_failed",
        ),
        (
            lambda request: chat_response(
                response_content(translated_text="x" * 32001)
            ),
            "translation_guardrail_failed",
        ),
        (
            lambda request: chat_response(
                response_content(protected={"number": "ABP-123"})
            ),
            "translation_guardrail_failed",
        ),
        (
            lambda request: httpx.Response(
                200, content=b"x" * (MAX_RESPONSE_BYTES + 1)
            ),
            "translation_guardrail_failed",
        ),
    ],
)
def test_adapter_maps_http_and_schema_failures_to_stable_codes(
    handler, code: str
) -> None:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(TranslationAdapterError) as error:
            OpenAiTranslationAdapter(client).translate(request(), configuration())
    finally:
        client.close()

    assert error.value.code == code
    assert str(error.value) == code


def test_oversize_source_is_rejected_before_network() -> None:
    calls = 0

    def handler(outbound: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return chat_response(response_content())

    oversized = TranslationRequest(
        kind="movie_description",
        source_text="x" * 32001,
        protected=request().protected,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(TranslationAdapterError) as error:
            OpenAiTranslationAdapter(client).translate(oversized, configuration())
    finally:
        client.close()

    assert error.value.code == "translation_input_too_large"
    assert calls == 0


def test_oversize_protected_payload_is_rejected_before_network() -> None:
    calls = 0

    def handler(outbound: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return chat_response(response_content())

    oversized = TranslationRequest(
        kind="actor_bio",
        source_text="short source",
        protected=ProtectedFields(
            number="ABP-123",
            actors=("x" * MAX_REQUEST_BYTES,),
            maker=None,
            series=None,
            tags=(),
        ),
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(TranslationAdapterError) as error:
            OpenAiTranslationAdapter(client).translate(oversized, configuration())
    finally:
        client.close()

    assert error.value.code == "translation_input_too_large"
    assert calls == 0
