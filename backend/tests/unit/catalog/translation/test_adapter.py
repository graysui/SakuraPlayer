from __future__ import annotations

import json
import logging

import httpx
import pytest

from sakuraplayer.catalog.translation.adapter import (
    MAX_RESPONSE_BYTES,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    OpenAiTranslationAdapter,
    TranslationAdapterError,
    TranslationRequest,
)
from sakuraplayer.catalog.translation.config import AiConfigurationSnapshot


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
    assert PROMPT_VERSION == "sakuraplayer-zh-v4"
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
    assert "thinking" not in body
    assert body["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert '"schema_version":1' in SYSTEM_PROMPT
    assert '"translated_text":"..."' in SYSTEM_PROMPT
    assert "[[SP_" not in SYSTEM_PROMPT
    assert "kind/source_text" in SYSTEM_PROMPT
    assert "Markdown" in SYSTEM_PROMPT
    user = json.loads(body["messages"][1]["content"])
    assert user == {
        "schema_version": 1,
        "kind": "movie_title",
        "source_text": "Fixture Original Title",
    }


def test_source_text_is_sent_verbatim_without_protection() -> None:
    seen_user: dict[str, object] = {}

    def handler(outbound: httpx.Request) -> httpx.Response:
        body = json.loads(outbound.content)
        user = json.loads(body["messages"][1]["content"])
        seen_user.update(user)
        sanitized = user["source_text"]
        assert isinstance(sanitized, str)
        assert "ABP-123" in sanitized
        assert "Actor One" in sanitized
        assert "Fixture Maker" in sanitized
        assert "Drama" in sanitized
        assert "[[SP_" not in sanitized
        return chat_response(
            response_content(
                translated_text=sanitized.replace("Original Title", "中文标题")
            )
        )

    raw_request = TranslationRequest(
        kind="movie_title",
        source_text="ABP-123 Actor One Fixture Maker Drama Original Title",
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        result = OpenAiTranslationAdapter(client).translate(
            raw_request,
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
    assert "thinking" not in body


@pytest.mark.parametrize(
    ("base_url", "model"),
    [
        ("https://opencode.ai/zen/go/v1", "deepseek-v4-flash"),
        ("https://opencode.ai/zen/go/v1", "DEEPSEEK-V4-PRO"),
        ("https://OPENCODE.AI/zen/v1", "deepseek-v4-flash"),
    ],
)
def test_opencode_deepseek_v4_profile_disables_thinking(
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

    body = json.loads(seen[0].content)
    assert body["thinking"] == {"type": "disabled"}
    assert "enable_thinking" not in body


@pytest.mark.parametrize(
    ("base_url", "model"),
    [
        ("https://opencode.ai/zen/go/v1", "kimi-k3"),
        ("https://opencode.ai.evil.test", "deepseek-v4-flash"),
        ("https://api.siliconflow.cn", "deepseek-v4-flash"),
        ("https://ai.example.test", "deepseek-v4-flash"),
    ],
)
def test_non_opencode_deepseek_v4_profile_gets_no_thinking_extension(
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

    body = json.loads(seen[0].content)
    assert "thinking" not in body
    assert "enable_thinking" not in body


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
    )
    long_description = TranslationRequest(
        kind="movie_description",
        source_text="\u65e5" * 32_000,
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


def test_v1_suffix_base_url_translates_without_duplicate_v1_prefix() -> None:
    seen: list[httpx.Request] = []

    def handler(outbound: httpx.Request) -> httpx.Response:
        seen.append(outbound)
        return chat_response(response_content())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        OpenAiTranslationAdapter(client).translate(
            request(),
            configuration(base_url="https://ai.example.test/zen/go/v1"),
        )
        OpenAiTranslationAdapter(client).probe(
            configuration(base_url="https://ai.example.test/zen/go/v1"),
        )
    finally:
        client.close()

    assert [str(item.url) for item in seen] == [
        "https://ai.example.test/zen/go/v1/chat/completions",
        "https://ai.example.test/zen/go/v1/models",
    ]


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
            lambda request: chat_response(response_content(extra_field=1)),
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
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(TranslationAdapterError) as error:
            OpenAiTranslationAdapter(client).translate(oversized, configuration())
    finally:
        client.close()

    assert error.value.code == "translation_input_too_large"
    assert calls == 0
