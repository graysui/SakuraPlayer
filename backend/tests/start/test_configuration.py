from __future__ import annotations

import base64

import pytest

from sakuraplayer.shared.config import StartupConfigurationError, load_settings


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


@pytest.fixture
def production_env() -> dict[str, str]:
    return {
        "SAKURAPLAYER_ENV": "production-private",
        "SAKURAPLAYER_DATABASE_URL": "postgresql+psycopg://app:secret@postgres/sakuraplayer",
        "SAKURAPLAYER_SETTINGS_KEY": _b64(b"s" * 32),
        "SAKURAPLAYER_TOKEN_KEY": _b64(b"t" * 32),
        "SAKURAPLAYER_PLAYBACK_KEY": _b64(b"p" * 32),
        "SAKURAPLAYER_BOOTSTRAP_TOKEN": _b64(b"b" * 32),
    }


def test_loads_valid_production_configuration(production_env: dict[str, str]) -> None:
    settings = load_settings(production_env)

    assert settings.environment == "production-private"
    assert settings.publish_host == "127.0.0.1"
    assert settings.api_port == 8000
    assert settings.javdb_host == "jdforrepam.com"
    assert settings.settings_key_id == "v1"
    assert settings.bootstrap_token == production_env[
        "SAKURAPLAYER_BOOTSTRAP_TOKEN"
    ].encode("ascii")
    assert production_env["SAKURAPLAYER_DATABASE_URL"] not in repr(settings)


def test_generic_postgresql_url_uses_the_pinned_psycopg_driver(
    production_env: dict[str, str],
) -> None:
    production_env["SAKURAPLAYER_DATABASE_URL"] = (
        "postgresql://app:secret@postgres/sakuraplayer"
    )

    settings = load_settings(production_env)

    assert settings.database_url == (
        "postgresql+psycopg://app:secret@postgres/sakuraplayer"
    )


@pytest.mark.parametrize(
    "missing_name",
    [
        "SAKURAPLAYER_DATABASE_URL",
        "SAKURAPLAYER_SETTINGS_KEY",
        "SAKURAPLAYER_TOKEN_KEY",
        "SAKURAPLAYER_PLAYBACK_KEY",
        "SAKURAPLAYER_BOOTSTRAP_TOKEN",
    ],
)
def test_production_rejects_missing_required_values(
    production_env: dict[str, str], missing_name: str
) -> None:
    production_env.pop(missing_name)

    with pytest.raises(StartupConfigurationError) as error:
        load_settings(production_env)

    assert error.value.code == "startup_configuration_invalid"
    assert missing_name in str(error.value)


def test_production_rejects_non_postgresql_database(
    production_env: dict[str, str],
) -> None:
    production_env["SAKURAPLAYER_DATABASE_URL"] = "sqlite:///local.db"

    with pytest.raises(StartupConfigurationError) as error:
        load_settings(production_env)

    assert error.value.code == "startup_configuration_invalid"
    assert "SAKURAPLAYER_DATABASE_URL" in str(error.value)


def test_rejects_plain_and_file_secret_together(
    production_env: dict[str, str], tmp_path
) -> None:
    secret_file = tmp_path / "settings-key"
    secret_file.write_text(_b64(b"x" * 32), encoding="ascii")
    production_env["SAKURAPLAYER_SETTINGS_KEY_FILE"] = str(secret_file)

    with pytest.raises(StartupConfigurationError) as error:
        load_settings(production_env)

    assert error.value.code == "startup_configuration_invalid"
    assert "SAKURAPLAYER_SETTINGS_KEY" in str(error.value)


def test_reads_secret_file_without_exposing_its_value(
    production_env: dict[str, str], tmp_path
) -> None:
    secret_value = _b64(b"x" * 32)
    secret_file = tmp_path / "settings-key"
    secret_file.write_text(secret_value, encoding="ascii")
    production_env.pop("SAKURAPLAYER_SETTINGS_KEY")
    production_env["SAKURAPLAYER_SETTINGS_KEY_FILE"] = str(secret_file)

    settings = load_settings(production_env)

    assert settings.settings_key == b"x" * 32
    assert secret_value not in repr(settings)


@pytest.mark.parametrize(
    ("name", "invalid_value"),
    [
        ("SAKURAPLAYER_SETTINGS_KEY", _b64(b"s" * 31)),
        ("SAKURAPLAYER_TOKEN_KEY", _b64(b"t" * 31)),
        ("SAKURAPLAYER_PLAYBACK_KEY", "not base64!"),
        ("SAKURAPLAYER_PLAYBACK_KEY", base64.b64encode(b"\xfb" * 32).decode()),
        ("SAKURAPLAYER_BOOTSTRAP_TOKEN", "short"),
        ("SAKURAPLAYER_BOOTSTRAP_TOKEN", "b" * 32),
        ("SAKURAPLAYER_BOOTSTRAP_TOKEN", _b64(b"b" * 31)),
        ("SAKURAPLAYER_BOOTSTRAP_TOKEN", _b64(b"b" * 385)),
    ],
)
def test_rejects_invalid_secret_format_without_echoing_secret(
    production_env: dict[str, str], name: str, invalid_value: str
) -> None:
    production_env[name] = invalid_value

    with pytest.raises(StartupConfigurationError) as error:
        load_settings(production_env)

    assert error.value.code == "startup_configuration_invalid"
    assert name in str(error.value)
    assert invalid_value not in str(error.value)


def test_rejects_reused_secret_material(production_env: dict[str, str]) -> None:
    production_env["SAKURAPLAYER_TOKEN_KEY"] = production_env[
        "SAKURAPLAYER_SETTINGS_KEY"
    ]

    with pytest.raises(StartupConfigurationError) as error:
        load_settings(production_env)

    assert error.value.code == "startup_configuration_invalid"
    assert "secret purposes" in str(error.value)


def test_rejects_reused_secret_source_across_key_and_bootstrap(
    production_env: dict[str, str],
) -> None:
    production_env["SAKURAPLAYER_BOOTSTRAP_TOKEN"] = production_env[
        "SAKURAPLAYER_SETTINGS_KEY"
    ]

    with pytest.raises(StartupConfigurationError) as error:
        load_settings(production_env)

    assert error.value.code == "startup_configuration_invalid"
    assert "secret purposes" in str(error.value)


@pytest.mark.parametrize("key_id", ["", "x" * 65, "contains spaces"])
def test_rejects_invalid_settings_key_id(
    production_env: dict[str, str],
    key_id: str,
) -> None:
    production_env["SAKURAPLAYER_SETTINGS_KEY_ID"] = key_id

    with pytest.raises(StartupConfigurationError) as error:
        load_settings(production_env)

    assert error.value.variable == "SAKURAPLAYER_SETTINGS_KEY_ID"


def test_rejects_same_key_material_with_different_base64_padding(
    production_env: dict[str, str],
) -> None:
    material = b"shared-key-material" + b"x" * 13
    production_env["SAKURAPLAYER_TOKEN_KEY"] = base64.urlsafe_b64encode(
        material
    ).decode("ascii")
    production_env["SAKURAPLAYER_BOOTSTRAP_TOKEN"] = _b64(material)

    with pytest.raises(StartupConfigurationError) as error:
        load_settings(production_env)

    assert error.value.code == "startup_configuration_invalid"
    assert "secret purposes" in str(error.value)


@pytest.mark.parametrize(
    "host",
    ["", "https://javdb.example", "javdb.example:443", "javdb.example/path"],
)
def test_rejects_invalid_javdb_host(
    production_env: dict[str, str],
    host: str,
) -> None:
    production_env["SAKURAPLAYER_JAVDB_HOST"] = host

    with pytest.raises(StartupConfigurationError) as error:
        load_settings(production_env)

    assert error.value.variable == "SAKURAPLAYER_JAVDB_HOST"
