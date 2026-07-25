from __future__ import annotations

from collections.abc import Mapping
import logging
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit


REDACTED = "[REDACTED]"

_SENSITIVE_FIELDS = frozenset(
    {
        "access_token",
        "ai_api_key",
        "api_key",
        "authorization",
        "authorization_header",
        "bootstrap_token",
        "ciphertext",
        "cookie",
        "cookies",
        "cookie_header",
        "database_url",
        "dsn",
        "jwt",
        "magnet",
        "password",
        "playback_key",
        "postgres_password",
        "proxy_authorization",
        "refresh_token",
        "secret",
        "set_cookie",
        "settings_key",
        "signature",
        "token",
        "token_key",
        "x_bootstrap_token",
    }
)
_SENSITIVE_SUFFIXES = (
    "_access_token",
    "_api_key",
    "_authorization",
    "_authorization_header",
    "_client_secret",
    "_cookie",
    "_cookie_header",
    "_cookies",
    "_database_url",
    "_dsn",
    "_password",
    "_refresh_token",
    "_secret",
    "_token",
)
_CAPABILITY_URL_FIELDS = frozenset(
    {"capability_url", "playback_url", "signed_url", "upstream_url"}
)
_URL = re.compile(
    r"(?P<url>(?:https?|postgresql(?:\+psycopg)?):\/\/[^\s]+)",
    re.I,
)
_RELATIVE_QUERY = re.compile(
    r"(?P<path>\/[A-Za-z0-9._~!$&'()*+,;=:@%\/-]*)\?[^\s]+"
)
_MAGNET = re.compile(r"magnet:\?[^\s]+", re.I)
_COOKIE_HEADER = re.compile(r"(?im)\b(cookie|set-cookie)\s*[:=]\s*[^\r\n]*")
_AUTH_HEADER = re.compile(
    r"(?i)\b(authorization|proxy-authorization)\s*[:=]\s*"
    r"(?:bearer\s+)?[^\s,;]+"
)
_SECRET_HEADER = re.compile(
    r"(?i)\b(x-bootstrap-token|x-api-key|api-key|client-secret)"
    r"\s*[:=]\s*[^\s,]+"
)
_NAMED_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|client[_-]?secret|password|refresh[_-]?token|"
    r"access[_-]?token|signature|token|secret|cookie|database[_-]?url)"
    r"\s*[:=]\s*[^\s,]+"
)
_JWT = re.compile(r"\b[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_STABLE_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_STANDARD_LOG_RECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__)


def _normalize_field(name: object) -> str:
    split_camel = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(name))
    return re.sub(r"[^a-z0-9]+", "_", split_camel.lower()).strip("_")


def _is_sensitive_field(name: object) -> bool:
    normalized = _normalize_field(name)
    return (
        normalized in _SENSITIVE_FIELDS
        or normalized in _CAPABILITY_URL_FIELDS
        or normalized.endswith(_SENSITIVE_SUFFIXES)
    )


def redact_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return REDACTED
    if parsed.scheme.lower() not in {
        "http",
        "https",
        "postgresql",
        "postgresql+psycopg",
    }:
        return REDACTED
    hostname = parsed.hostname or ""
    if not hostname:
        return REDACTED
    try:
        port = f":{parsed.port}" if parsed.port is not None else ""
    except ValueError:
        port = ""
    return urlunsplit((parsed.scheme, f"{hostname}{port}", parsed.path, "", ""))


def redact_text(value: str) -> str:
    result = _URL.sub(lambda match: redact_url(match.group("url")), value)
    result = _RELATIVE_QUERY.sub(lambda match: match.group("path"), result)
    result = _MAGNET.sub(REDACTED, result)
    result = _COOKIE_HEADER.sub(
        lambda match: f"{match.group(1)}={REDACTED}",
        result,
    )
    result = _AUTH_HEADER.sub(
        lambda match: f"{match.group(1)}={REDACTED}",
        result,
    )
    result = _SECRET_HEADER.sub(
        lambda match: f"{match.group(1)}={REDACTED}",
        result,
    )
    result = _NAMED_SECRET.sub(
        lambda match: f"{match.group(1)}={REDACTED}",
        result,
    )
    return _JWT.sub(REDACTED, result)


def redact_mapping(value: Mapping[object, Any]) -> dict[object, Any]:
    return {
        key: REDACTED if _is_sensitive_field(key) else redact_value(item)
        for key, item in value.items()
    }


def stable_error_code(value: object) -> str:
    if isinstance(value, str) and _STABLE_ERROR_CODE.fullmatch(value):
        return value
    return "internal_error"


def redact_value(value: Any) -> Any:
    if isinstance(value, BaseException):
        return {"code": stable_error_code(getattr(value, "code", None))}
    if isinstance(value, Mapping):
        return redact_mapping(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if isinstance(value, str):
        return redact_text(value)
    return value


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
        except (TypeError, ValueError):
            rendered = str(record.msg)
        record.msg = redact_text(rendered)
        record.args = ()
        for name, value in tuple(record.__dict__.items()):
            if name in _STANDARD_LOG_RECORD_FIELDS:
                continue
            record.__dict__[name] = (
                REDACTED if _is_sensitive_field(name) else redact_value(value)
            )
        if record.exc_info:
            error = record.exc_info[1]
            safe_error = redact_value(error)
            record.msg = f"{record.msg} exception={safe_error}"
            record.exc_info = None
            record.exc_text = None
        return True


def install_redaction_filters(logger: logging.Logger | None = None) -> None:
    target = logger or logging.getLogger()
    for handler in target.handlers:
        if not any(isinstance(item, RedactionFilter) for item in handler.filters):
            handler.addFilter(RedactionFilter())
