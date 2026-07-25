from __future__ import annotations

from io import StringIO
import logging

from sakuraplayer.shared.redaction import (
    REDACTED,
    RedactionFilter,
    redact_mapping,
    redact_text,
    redact_url,
    redact_value,
)


class CredentialError(RuntimeError):
    code = "cloud115_credentials_expired"


class MaliciousCodeError(RuntimeError):
    code = "cookie=private-cookie"


def test_redacts_sensitive_fields_recursively_without_changing_safe_values() -> None:
    data = {
        "cookie": "UID=private-cookie",
        "nested": {
            "api_key": "private-ai-key",
            "password": "private-password",
            "authorization": "Bearer private-token",
        },
        "safe": "ready",
        "items": [{"refresh_token": "private-refresh"}],
    }

    redacted = redact_mapping(data)

    assert redacted["cookie"] == REDACTED
    assert redacted["nested"]["api_key"] == REDACTED
    assert redacted["nested"]["password"] == REDACTED
    assert redacted["nested"]["authorization"] == REDACTED
    assert redacted["items"][0]["refresh_token"] == REDACTED
    assert redacted["safe"] == "ready"


def test_redacts_common_structured_field_aliases() -> None:
    data = {
        "cookies": "UID=private-cookie",
        "cookieHeader": "UID=private-cookie",
        "authorization_header": "Bearer private-token",
        "x-api-key": "private-ai-key",
        "openai_api_key": "private-ai-key",
        "cloud115_cookie": "UID=private-cookie",
        "client_secret": "private-client-secret",
        "signed_url": "https://example.test/play/private-capability",
        "credentials_configured": True,
        "key_id": "v1",
    }

    redacted = redact_mapping(data)

    for field in (
        "cookies",
        "cookieHeader",
        "authorization_header",
        "x-api-key",
        "openai_api_key",
        "cloud115_cookie",
        "client_secret",
        "signed_url",
    ):
        assert redacted[field] == REDACTED
    assert redacted["credentials_configured"] is True
    assert redacted["key_id"] == "v1"


def test_removes_all_query_and_fragment_data_from_logged_urls() -> None:
    signed = "https://cdn.example/video.m3u8?token=private&expires=123#fragment"

    assert redact_url(signed) == "https://cdn.example/video.m3u8"
    assert "private" not in redact_text(f"upstream={signed}")
    assert "expires" not in redact_text(f"upstream={signed}")


def test_redacts_magnets_cookie_headers_and_bearer_tokens_in_free_text() -> None:
    text = (
        "Cookie: UID=private-cookie "
        "Authorization: Bearer private-token "
        "magnet:?xt=urn:btih:private-hash"
    )

    result = redact_text(text)

    for secret in ("private-cookie", "private-token", "private-hash"):
        assert secret not in result
    assert REDACTED in result


def test_redacts_complete_cookie_and_api_key_header_values() -> None:
    text = (
        "Cookie: UID=private-uid; CID=private-cid; SEID=private-seid\n"
        "X-API-Key: private-header-key\n"
        "api_key: private-field-key client_secret=private-client-secret"
    )

    result = redact_text(text)

    for secret in (
        "private-uid",
        "private-cid",
        "private-seid",
        "private-header-key",
        "private-field-key",
        "private-client-secret",
    ):
        assert secret not in result


def test_exception_redaction_keeps_only_stable_code() -> None:
    error = CredentialError("cookie=private-cookie")

    assert redact_value(error) == {"code": "cloud115_credentials_expired"}
    assert "private-cookie" not in str(redact_value(error))


def test_exception_redaction_rejects_untrusted_code_text() -> None:
    error = MaliciousCodeError("private-message")

    assert redact_value(error) == {"code": "internal_error"}
    assert "private-cookie" not in str(redact_value(error))


def test_logging_filter_redacts_format_args_and_structured_extra_fields() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s api_key=%(api_key)s"))
    handler.addFilter(RedactionFilter())
    logger = logging.getLogger("test-redaction-filter")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    logger.info(
        "request url=%s cookie=%s",
        "https://example.test/path?signature=private-signature",
        "private-cookie",
        extra={"api_key": "private-ai-key"},
    )
    handler.flush()
    output = stream.getvalue()

    for secret in ("private-signature", "private-cookie", "private-ai-key"):
        assert secret not in output
    assert "api_key=[REDACTED]" in output


def test_plain_non_sensitive_values_are_preserved() -> None:
    assert redact_value(
        {
            "status": "ready",
            "elapsed_ms": 12,
            "credentials_configured": True,
            "key_id": "v1",
        }
    ) == {
        "status": "ready",
        "elapsed_ms": 12,
        "credentials_configured": True,
        "key_id": "v1",
    }


def test_redacts_database_dsn_and_relative_access_log_query() -> None:
    message = (
        "dsn=postgresql+psycopg://user:private-password@db/app "
        'GET /play/stream?signature=private-signature&token=private-token HTTP/1.1'
    )

    result = redact_text(message)

    assert "private-password" not in result
    assert "private-signature" not in result
    assert "private-token" not in result
    assert "postgresql+psycopg://db/app" in result
    assert "/play/stream" in result


def test_logging_filter_removes_exception_message_and_traceback() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RedactionFilter())
    logger = logging.getLogger("test-redaction-exception")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    try:
        raise CredentialError("Cookie: UID=private-cookie")
    except CredentialError:
        logger.exception("provider failed")
    handler.flush()

    output = stream.getvalue()
    assert "private-cookie" not in output
    assert "Traceback" not in output
    assert "cloud115_credentials_expired" in output
