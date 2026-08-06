from __future__ import annotations

import json
import logging
import re

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


def configuration(
    *,
    base_url: str = "https://ai.example.test/root",
    model: str = "fixture-model",
) -> AiConfigurationSnapshot:
    return AiConfigurationSnapshot(
        base_url=base_url,
        api_key="private-fixture-key",
        model=model,
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
    }
    value.update(overrides)
    return value


def chat_response(
    content: object,
    *,
    finish_reason: str = "stop",
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "finish_reason": finish_reason,
                    "message": {"content": json.dumps(content)},
                }
            ]
        },
        headers=headers,
    )


def timeout_response(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("fixture timeout", request=request)


def network_response(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("fixture network failure", request=request)


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
    assert PROMPT_VERSION == "sakuraplayer-zh-v3"
    assert len(seen) == 1
    outbound = seen[0]
    assert str(outbound.url) == "https://ai.example.test/root/v1/chat/completions"
    assert outbound.headers["Authorization"] == "Bearer private-fixture-key"
    body = json.loads(outbound.content)
    assert body["model"] == "fixture-model"
    assert body["temperature"] == 0
    assert body["response_format"] == {"type": "json_object"}
    assert body["max_tokens"] == 128
    assert "enable_thinking" not in body
    assert body["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert '"schema_version":1' in SYSTEM_PROMPT
    assert '"translated_text":"..."' in SYSTEM_PROMPT
    assert "placeholder" in SYSTEM_PROMPT
    assert "kind/source_text" in SYSTEM_PROMPT
    assert "Markdown" in SYSTEM_PROMPT
    user = json.loads(body["messages"][1]["content"])
    assert user == {
        "schema_version": 1,
        "kind": "movie_title",
        "source_text": "Fixture Original Title",
    }
    assert b"ABP-123" not in outbound.content
    assert b"Actor One" not in outbound.content
    assert b"Fixture Maker" not in outbound.content
    assert b"Drama" not in outbound.content


def test_protected_values_are_replaced_locally_and_restored_after_translation() -> None:
    seen_user: dict[str, object] = {}

    def handler(outbound: httpx.Request) -> httpx.Response:
        body = json.loads(outbound.content)
        user = json.loads(body["messages"][1]["content"])
        seen_user.update(user)
        sanitized = user["source_text"]
        assert isinstance(sanitized, str)
        assert "ABP-123" not in sanitized
        assert "Actor One" not in sanitized
        assert "Fixture Maker" not in sanitized
        assert "Drama" not in sanitized
        assert len(re.findall(r"\[\[SP_[A-F0-9]{8}_[0-9]{4}\]\]", sanitized)) == 4
        return chat_response(
            response_content(
                translated_text=sanitized.replace("Original Title", "中文标题")
            )
        )

    protected_request = TranslationRequest(
        kind="movie_title",
        source_text="ABP-123 Actor One Fixture Maker Drama Original Title",
        protected=request().protected,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        result = OpenAiTranslationAdapter(client).translate(
            protected_request,
            configuration(),
        )
    finally:
        client.close()

    assert set(seen_user) == {"schema_version", "kind", "source_text"}
    assert result.translated_text == ("ABP-123 Actor One Fixture Maker Drama 中文标题")


def test_siliconflow_qwen35_profile_disables_thinking() -> None:
    seen: list[httpx.Request] = []

    def handler(outbound: httpx.Request) -> httpx.Response:
        seen.append(outbound)
        return chat_response(response_content())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        OpenAiTranslationAdapter(client).translate(
            request(),
            configuration(
                base_url="https://API.SILICONFLOW.CN",
                model="Qwen/Qwen3.5-35B-A3B",
            ),
        )
    finally:
        client.close()

    body = json.loads(seen[0].content)
    assert body["enable_thinking"] is False


@pytest.mark.parametrize(
    ("base_url", "model"),
    [
        ("https://api.siliconflow.cn", "fixture-model"),
        ("https://api.siliconflow.cn.evil.test", "Qwen/Qwen3.5-35B-A3B"),
        ("https://ai.example.test", "Qwen/Qwen3.5-35B-A3B"),
    ],
)
def test_generic_provider_does_not_receive_siliconflow_extension(
    base_url: str,
    model: str,
) -> None:
    seen: list[httpx.Request] = []

    def handler(outbound: httpx.Request) -> httpx.Response:
        seen.append(outbound)
        return chat_response(response_content())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        OpenAiTranslationAdapter(client).translate(
            request(),
            configuration(base_url=base_url, model=model),
        )
    finally:
        client.close()

    assert "enable_thinking" not in json.loads(seen[0].content)


def test_output_token_limit_grows_for_long_descriptions() -> None:
    seen: list[httpx.Request] = []

    def handler(outbound: httpx.Request) -> httpx.Response:
        seen.append(outbound)
        return chat_response(response_content())

    short_description = TranslationRequest(
        kind="movie_description",
        source_text="Short fixture description",
        protected=request().protected,
    )
    long_description = TranslationRequest(
        kind="movie_description",
        source_text="\u65e5" * 32_000,
        protected=request().protected,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        adapter = OpenAiTranslationAdapter(client)
        adapter.translate(short_description, configuration())
        adapter.translate(long_description, configuration())
    finally:
        client.close()

    short_body, long_body = (json.loads(item.content) for item in seen)
    assert short_body["max_tokens"] == 256
    assert 32_000 < long_body["max_tokens"] <= 65_536


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (200, None),
        (401, "translation_credentials_invalid"),
        (403, "translation_credentials_invalid"),
        (503, "translation_upstream_error"),
    ],
)
def test_connection_probe_only_reads_models(status: int, expected: str | None) -> None:
    seen: list[httpx.Request] = []

    def handler(outbound: httpx.Request) -> httpx.Response:
        seen.append(outbound)
        return httpx.Response(status)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        adapter = OpenAiTranslationAdapter(client)
        if expected is None:
            assert adapter.probe(configuration()) is None
        else:
            with pytest.raises(TranslationAdapterError) as error:
                adapter.probe(configuration())
            assert error.value.code == expected
    finally:
        client.close()

    assert len(seen) == 1
    assert str(seen[0].url) == "https://ai.example.test/root/v1/models"
    assert seen[0].method == "GET"
    assert seen[0].headers["Authorization"] == "Bearer private-fixture-key"


@pytest.mark.parametrize(
    ("handler", "code", "category"),
    [
        (
            lambda request: httpx.Response(401),
            "translation_upstream_error",
            "http_status",
        ),
        (timeout_response, "translation_upstream_error", "timeout"),
        (network_response, "translation_upstream_error", "network"),
        (
            lambda request: httpx.Response(200, content=b"not-json"),
            "translation_guardrail_failed",
            "response_envelope",
        ),
        (
            lambda request: httpx.Response(200, json={"choices": []}),
            "translation_guardrail_failed",
            "response_envelope",
        ),
        (
            lambda request: httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": "{"},
                        }
                    ]
                },
            ),
            "translation_guardrail_failed",
            "content_json",
        ),
        (
            lambda request: chat_response("not-an-object"),
            "translation_guardrail_failed",
            "output_schema",
        ),
        (
            lambda request: chat_response(
                {
                    "schema_version": 1,
                    "kind": "movie_title",
                    "source_text": "夹具中文标题",
                }
            ),
            "translation_guardrail_failed",
            "output_schema",
        ),
        (
            lambda request: chat_response(response_content(extra=True)),
            "translation_guardrail_failed",
            "output_schema",
        ),
        (
            lambda request: chat_response(response_content(translated_text="")),
            "translation_guardrail_failed",
            "output_schema",
        ),
        (
            lambda request: chat_response(response_content(translated_text="   \t")),
            "translation_guardrail_failed",
            "output_schema",
        ),
        (
            lambda request: chat_response(
                response_content(translated_text="x" * 32001)
            ),
            "translation_guardrail_failed",
            "output_schema",
        ),
        (
            lambda request: chat_response(response_content(protected={})),
            "translation_guardrail_failed",
            "output_schema",
        ),
        (
            lambda request: httpx.Response(
                200, content=b"x" * (MAX_RESPONSE_BYTES + 1)
            ),
            "translation_guardrail_failed",
            "response_too_large",
        ),
        (
            lambda request: chat_response(response_content(), finish_reason="length"),
            "translation_guardrail_failed",
            "finish_reason",
        ),
    ],
)
def test_adapter_maps_http_and_schema_failures_to_stable_codes(
    handler, code: str, category: str
) -> None:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(TranslationAdapterError) as error:
            OpenAiTranslationAdapter(client).translate(request(), configuration())
    finally:
        client.close()

    assert error.value.code == code
    assert error.value.category == category
    assert str(error.value) == code


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "forged", "changed"])
def test_protected_placeholder_mismatch_has_a_distinct_safe_category(
    mutation: str,
) -> None:
    protected_request = TranslationRequest(
        kind="movie_title",
        source_text="ABP-123 Fixture title",
        protected=request().protected,
    )

    def handler(outbound: httpx.Request) -> httpx.Response:
        body = json.loads(outbound.content)
        user = json.loads(body["messages"][1]["content"])
        sanitized = user["source_text"]
        token = re.search(r"\[\[SP_[A-F0-9]{8}_[0-9]{4}\]\]", sanitized)
        assert token is not None
        translated = sanitized
        if mutation == "missing":
            translated = translated.replace(token.group(), "")
        elif mutation == "duplicate":
            translated = f"{translated} {token.group()}"
        elif mutation == "forged":
            translated = f"{translated} [[SP_DEADBEEF_9999]]"
        else:
            translated = translated.replace(token.group(), token.group().lower())
        return chat_response(response_content(translated_text=translated))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(TranslationAdapterError) as error:
            OpenAiTranslationAdapter(client).translate(
                protected_request,
                configuration(),
            )
    finally:
        client.close()

    assert error.value.code == "translation_guardrail_failed"
    assert error.value.category == "protected_mismatch"


def test_failure_log_contains_only_safe_diagnostics(caplog) -> None:
    trace_id = "safe-trace-123"
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                503,
                headers={"x-siliconcloud-trace-id": trace_id},
                text="do-not-log-response",
            )
        )
    )
    sensitive_request = TranslationRequest(
        kind="movie_title",
        source_text="do-not-log-source",
        protected=request().protected,
    )
    try:
        with caplog.at_level(logging.WARNING):
            with pytest.raises(TranslationAdapterError):
                OpenAiTranslationAdapter(client).translate(
                    sensitive_request,
                    configuration(),
                )
    finally:
        client.close()

    assert "translation_provider_failed" in caplog.text
    assert "category=http_status" in caplog.text
    assert "http_status=503" in caplog.text
    assert f"trace_id={trace_id}" in caplog.text
    assert "do-not-log-source" not in caplog.text
    assert "do-not-log-response" not in caplog.text
    assert "private-fixture-key" not in caplog.text


def test_unsafe_trace_id_is_not_logged(caplog) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                503,
                headers={"x-siliconcloud-trace-id": "unsafe\nsecret"},
            )
        )
    )
    try:
        with caplog.at_level(logging.WARNING):
            with pytest.raises(TranslationAdapterError):
                OpenAiTranslationAdapter(client).translate(request(), configuration())
    finally:
        client.close()

    assert "unsafe" not in caplog.text
    assert "secret" not in caplog.text


def test_reasoning_content_is_never_logged(caplog) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": "not-json",
                                "reasoning_content": "do-not-log-reasoning",
                            },
                        }
                    ]
                },
            )
        )
    )
    try:
        with caplog.at_level(logging.WARNING):
            with pytest.raises(TranslationAdapterError):
                OpenAiTranslationAdapter(client).translate(request(), configuration())
    finally:
        client.close()

    assert "category=content_json" in caplog.text
    assert "do-not-log-reasoning" not in caplog.text


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


def test_unused_large_protected_payload_is_not_sent_to_provider() -> None:
    calls = 0

    def handler(outbound: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert b"x" * 1024 not in outbound.content
        return chat_response(response_content())

    oversized = TranslationRequest(
        kind="movie_title",
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
        result = OpenAiTranslationAdapter(client).translate(
            oversized,
            configuration(),
        )
    finally:
        client.close()

    assert result.translated_text == "夹具中文标题"
    assert calls == 1
