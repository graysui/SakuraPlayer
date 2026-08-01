from __future__ import annotations

import base64
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


class StartupConfigurationError(RuntimeError):
    code = "startup_configuration_invalid"

    def __init__(self, variable: str, reason: str) -> None:
        self.variable = variable
        super().__init__(f"{self.code}: {variable}: {reason}")


@dataclass(frozen=True)
class Settings:
    environment: str
    database_url: str = field(repr=False)
    log_level: str
    publish_host: str
    api_port: int
    trust_proxy_headers: bool
    settings_key_id: str
    settings_key: bytes | None = field(repr=False)
    token_key: bytes | None = field(repr=False)
    playback_key: bytes | None = field(repr=False)
    bootstrap_token: bytes | None = field(repr=False)
    javdb_host: str = "jdforrepam.com"


_SECURE_ENVIRONMENTS = frozenset({"production-private", "acceptance-real115"})
_ENVIRONMENTS = frozenset(
    {"test", "development", "production-private", "acceptance-real115"}
)
_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})
_URL_SAFE_TEXT = re.compile(r"^[A-Za-z0-9_-]+$")
_URL_SAFE_BASE64 = re.compile(r"^[A-Za-z0-9_-]+={0,2}$")
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_DNS_HOSTNAME = re.compile(
    r"(?=^.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name, "").strip()
    if not value:
        raise StartupConfigurationError(name, "value is required")
    return value


def _parse_bool(values: Mapping[str, str], name: str, default: bool) -> bool:
    raw = values.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise StartupConfigurationError(name, "expected true or false")


def _read_secret_text(values: Mapping[str, str], name: str) -> str | None:
    file_name = f"{name}_FILE"
    plain_value = values.get(name)
    file_value = values.get(file_name)
    if plain_value is not None and file_value is not None:
        raise StartupConfigurationError(name, "plain and _FILE values conflict")
    if file_value is not None:
        try:
            return Path(file_value).read_text(encoding="ascii").strip()
        except (OSError, UnicodeError):
            raise StartupConfigurationError(
                file_name, "secret file is unreadable"
            ) from None
    if plain_value is None:
        return None
    return plain_value.strip()


def _decode_key(
    values: Mapping[str, str],
    name: str,
    minimum: int,
    exact: bool,
) -> tuple[bytes | None, str | None]:
    encoded = _read_secret_text(values, name)
    if encoded is None:
        return None, None
    if not _URL_SAFE_BASE64.fullmatch(encoded):
        raise StartupConfigurationError(name, "secret format is invalid")
    try:
        padding = "=" * (-len(encoded) % 4)
        decoded = base64.b64decode(
            encoded + padding,
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, base64.binascii.Error):
        raise StartupConfigurationError(name, "secret format is invalid") from None
    valid_length = len(decoded) == minimum if exact else len(decoded) >= minimum
    if not valid_length:
        requirement = f"exactly {minimum}" if exact else f"at least {minimum}"
        raise StartupConfigurationError(
            name, f"secret must decode to {requirement} bytes"
        )
    return decoded, encoded


def _decode_bootstrap(
    values: Mapping[str, str],
) -> tuple[bytes | None, str | None, bytes | None]:
    name = "SAKURAPLAYER_BOOTSTRAP_TOKEN"
    encoded = _read_secret_text(values, name)
    if encoded is None:
        return None, None, None
    if len(encoded) > 512 or not _URL_SAFE_TEXT.fullmatch(encoded):
        raise StartupConfigurationError(name, "secret format is invalid")
    try:
        padding = "=" * (-len(encoded) % 4)
        decoded = base64.b64decode(
            encoded + padding,
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, base64.binascii.Error):
        raise StartupConfigurationError(name, "secret format is invalid") from None
    canonical = base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=")
    if len(decoded) < 32 or canonical != encoded:
        raise StartupConfigurationError(name, "secret format is invalid")
    return encoded.encode("ascii"), encoded, decoded


def load_settings(environment: Mapping[str, str] | None = None) -> Settings:
    values = dict(os.environ if environment is None else environment)
    app_environment = values.get("SAKURAPLAYER_ENV", "development").strip()
    if app_environment not in _ENVIRONMENTS:
        raise StartupConfigurationError("SAKURAPLAYER_ENV", "unsupported environment")

    database_url = _required(values, "SAKURAPLAYER_DATABASE_URL")
    if database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url.removeprefix(
            "postgresql://"
        )
    if app_environment in _SECURE_ENVIRONMENTS and not database_url.startswith(
        ("postgresql://", "postgresql+psycopg://")
    ):
        raise StartupConfigurationError(
            "SAKURAPLAYER_DATABASE_URL", "PostgreSQL is required"
        )

    log_level = values.get("SAKURAPLAYER_LOG_LEVEL", "INFO").strip().upper()
    if log_level not in _LOG_LEVELS:
        raise StartupConfigurationError("SAKURAPLAYER_LOG_LEVEL", "unsupported level")

    raw_port = values.get("SAKURAPLAYER_API_PORT", "8000").strip()
    try:
        api_port = int(raw_port)
    except ValueError:
        raise StartupConfigurationError(
            "SAKURAPLAYER_API_PORT", "invalid port"
        ) from None
    if not 1 <= api_port <= 65535:
        raise StartupConfigurationError("SAKURAPLAYER_API_PORT", "invalid port")

    javdb_host = values.get("SAKURAPLAYER_JAVDB_HOST", "jdforrepam.com").strip()
    if not _DNS_HOSTNAME.fullmatch(javdb_host):
        raise StartupConfigurationError(
            "SAKURAPLAYER_JAVDB_HOST", "expected a DNS hostname"
        )
    javdb_host = javdb_host.lower()

    settings_key, settings_key_source = _decode_key(
        values, "SAKURAPLAYER_SETTINGS_KEY", minimum=32, exact=True
    )
    token_key, token_key_source = _decode_key(
        values, "SAKURAPLAYER_TOKEN_KEY", minimum=32, exact=False
    )
    playback_key, playback_key_source = _decode_key(
        values, "SAKURAPLAYER_PLAYBACK_KEY", minimum=32, exact=False
    )
    (
        bootstrap_token,
        bootstrap_token_source,
        bootstrap_token_material,
    ) = _decode_bootstrap(values)

    secrets = {
        "SAKURAPLAYER_SETTINGS_KEY": settings_key,
        "SAKURAPLAYER_TOKEN_KEY": token_key,
        "SAKURAPLAYER_PLAYBACK_KEY": playback_key,
        "SAKURAPLAYER_BOOTSTRAP_TOKEN": bootstrap_token_material,
    }
    if app_environment in _SECURE_ENVIRONMENTS:
        for name, value in secrets.items():
            if value is None:
                raise StartupConfigurationError(name, "value is required")
    sources = [
        value
        for value in (
            settings_key_source,
            token_key_source,
            playback_key_source,
            bootstrap_token_source,
        )
        if value is not None
    ]
    if len(sources) != len(set(sources)):
        raise StartupConfigurationError(
            "secret purposes", "secret purposes must not reuse source material"
        )
    present = [value for value in secrets.values() if value is not None]
    if len(present) != len(set(present)):
        raise StartupConfigurationError(
            "secret purposes", "secret purposes must not reuse key material"
        )

    settings_key_id = values.get("SAKURAPLAYER_SETTINGS_KEY_ID", "v1").strip()
    if not _KEY_ID.fullmatch(settings_key_id):
        raise StartupConfigurationError(
            "SAKURAPLAYER_SETTINGS_KEY_ID",
            "expected 1..64 stable characters",
        )

    return Settings(
        environment=app_environment,
        database_url=database_url,
        log_level=log_level,
        publish_host=values.get("SAKURAPLAYER_PUBLISH_HOST", "127.0.0.1").strip(),
        api_port=api_port,
        trust_proxy_headers=_parse_bool(
            values, "SAKURAPLAYER_TRUST_PROXY_HEADERS", False
        ),
        javdb_host=javdb_host,
        settings_key_id=settings_key_id,
        settings_key=settings_key,
        token_key=token_key,
        playback_key=playback_key,
        bootstrap_token=bootstrap_token,
    )
