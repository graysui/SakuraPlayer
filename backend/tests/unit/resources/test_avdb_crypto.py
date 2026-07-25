from __future__ import annotations

import base64
from datetime import date, datetime
from hashlib import pbkdf2_hmac
import io
import json
import logging
from pathlib import Path
import stat
from zipfile import ZIP_DEFLATED, ZipFile
from zipfile import ZipInfo

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from sakuraplayer.resources.avdb_crypto import (
    AvdbAssetError,
    decrypt_asset,
    validate_asset_name,
    verify_asset_digest,
)


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "avdb"


def encrypted_asset(
    *,
    include_bom: bool = False,
    iterations: int = 200_000,
    tag: bytes | None = None,
    extra_outer_file: bool = False,
    extra_csv_field: bool = False,
    manifest_overrides: dict[str, object] | None = None,
    csv_content_override: str | None = None,
    extra_inner_file: bool = False,
) -> bytes:
    extra_header = ",ignored" if extra_csv_field else ""
    extra_value = ",value" if extra_csv_field else ""
    csv_content = (
        "tid,number,title,publish_date,magnet,preview_images,detail_url,size,"
        f"section,category,website,create_time,update_time{extra_header}\n"
        "1,,Example,2026-07-25,urn:fixture-resource,,,1024,亚洲有码,,"
        f"sehuatang,2026-07-25T01:00:00,2026-07-25T02:00:00{extra_value}\n"
    )
    csv_content = csv_content_override or csv_content
    if include_bom:
        csv_content = "\ufeff" + csv_content
    inner_buffer = io.BytesIO()
    with ZipFile(inner_buffer, "w", ZIP_DEFLATED) as inner_zip:
        inner_zip.writestr("resource.csv", csv_content.encode("utf-8"))
        if extra_inner_file:
            inner_zip.writestr("extra.csv", b"tid,title\n2,extra\n")

    salt = b"s" * 16
    nonce = b"n" * 12
    key = pbkdf2_hmac(
        "sha256",
        bytes.fromhex(
            "ca42e687df5818e2e88da0ff5b9fd2c60f7e22721f682b66c3e50485a00d06d5"
        ),
        salt,
        iterations,
        dklen=32,
    )
    encrypted = AESGCM(key).encrypt(nonce, inner_buffer.getvalue(), None)
    ciphertext, computed_tag = encrypted[:-16], encrypted[-16:]
    manifest = {
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "tag": base64.b64encode(tag or computed_tag).decode("ascii"),
        "iterations": iterations,
        "algorithm": "AES-256-GCM",
        "kdf": "PBKDF2-HMAC-SHA256",
        "key_length": 32,
    }
    manifest.update(manifest_overrides or {})
    outer_buffer = io.BytesIO()
    with ZipFile(outer_buffer, "w", ZIP_DEFLATED) as outer_zip:
        outer_zip.writestr("avdb-resource-library.json", json.dumps(manifest))
        outer_zip.writestr("avdb-resource-library.bin", ciphertext)
        if extra_outer_file:
            outer_zip.writestr("extra.exe", b"not allowed")
    return outer_buffer.getvalue()


def test_decrypts_the_contract_format_and_reads_utf8_bom_csv() -> None:
    encoded = (FIXTURES / "valid-utf8-bom.b64").read_text(encoding="ascii").strip()
    asset = decrypt_asset(base64.b64decode(encoded, validate=True))

    assert asset.manifest_summary == {
        "algorithm": "AES-256-GCM",
        "iterations": 200_000,
        "kdf": "PBKDF2-HMAC-SHA256",
        "key_length": 32,
    }
    assert list(asset.iter_rows()) == [
        {
            "tid": 1,
            "number": None,
            "title": "Example",
            "publish_date": date(2026, 7, 25),
            "magnet": "urn:fixture-resource",
            "preview_images": None,
            "detail_url": None,
            "size": 1024,
            "section": "亚洲有码",
            "category": None,
            "website": "sehuatang",
            "create_time": datetime(2026, 7, 25, 1, 0),
            "update_time": datetime(2026, 7, 25, 2, 0),
        }
    ]


@pytest.mark.parametrize(
    "kwargs, expected_code",
    [
        ({"iterations": 199_999}, "avdb_asset_invalid"),
        ({"tag": b"x" * 16}, "avdb_decryption_failed"),
        ({"extra_outer_file": True}, "avdb_asset_invalid"),
    ],
)
def test_rejects_invalid_manifest_or_unauthenticated_ciphertext(
    kwargs: dict[str, object],
    expected_code: str,
) -> None:
    with pytest.raises(AvdbAssetError) as error:
        decrypt_asset(encrypted_asset(**kwargs))

    assert error.value.code == expected_code
    assert "magnet" not in str(error.value).lower()


def test_validates_complete_asset_names_and_digest() -> None:
    validate_asset_name("30D_202607250300.zip", mode="incremental_30d")
    validate_asset_name("All_sehuatang_100_202607250400.zip", mode="full_reconcile")

    with pytest.raises(AvdbAssetError):
        validate_asset_name("prefix-30D_202607250300.zip", mode="incremental_30d")
    with pytest.raises(AvdbAssetError) as error:
        verify_asset_digest(b"asset", "0" * 64)

    assert error.value.code == "avdb_asset_digest_mismatch"


def test_rejects_empty_corrupt_and_oversized_assets(monkeypatch) -> None:
    for invalid in (b"", b"not-a-zip"):
        with pytest.raises(AvdbAssetError):
            decrypt_asset(invalid)

    monkeypatch.setattr(
        "sakuraplayer.resources.avdb_crypto.MAX_OUTER_BYTES",
        4,
    )
    with pytest.raises(AvdbAssetError):
        decrypt_asset(b"12345")


def test_ignores_extra_csv_fields_with_a_safe_warning(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        row = next(decrypt_asset(encrypted_asset(extra_csv_field=True)).iter_rows())

    assert "ignored" not in row
    assert "avdb_csv_extra_fields" in caplog.text
    assert "urn:fixture-resource" not in caplog.text


def test_fixed_invalid_tag_fixture_fails_authentication() -> None:
    encoded = (FIXTURES / "invalid-tag.b64").read_text(encoding="ascii").strip()

    with pytest.raises(AvdbAssetError) as error:
        decrypt_asset(base64.b64decode(encoded, validate=True))

    assert error.value.code == "avdb_decryption_failed"


@pytest.mark.parametrize(
    "overrides",
    [
        {"iterations": 200_000.0},
        {"key_length": 32.0},
        {"unknown_algorithm_option": "unsafe"},
    ],
)
def test_manifest_requires_exact_integer_types_and_known_fields(overrides) -> None:
    with pytest.raises(AvdbAssetError) as error:
        decrypt_asset(encrypted_asset(manifest_overrides=overrides))

    assert error.value.code == "avdb_asset_invalid"


def test_file_decryption_uses_an_owned_temporary_inner_zip(tmp_path) -> None:
    from sakuraplayer.resources.avdb_crypto import decrypt_asset_file

    outer_path = tmp_path / "outer.zip"
    plaintext_directory = tmp_path / "plaintext"
    plaintext_directory.mkdir()
    outer_path.write_bytes(encrypted_asset())

    asset = decrypt_asset_file(outer_path, temp_directory=plaintext_directory)

    assert asset.inner_zip_path.parent == plaintext_directory
    assert asset.inner_zip_path.exists()
    assert list(asset.iter_rows())[0]["tid"] == 1
    asset.close()
    assert not asset.inner_zip_path.exists()


def test_invalid_date_becomes_null_and_preserves_a_safe_field_error() -> None:
    csv_content = (
        "tid,number,title,publish_date,magnet,preview_images,detail_url,size,"
        "section,category,website,create_time,update_time\n"
        "1,ABC-1,Title,not-a-date,fixture,,,,亚洲有码,,sehuatang,,\n"
    )

    row = next(
        decrypt_asset(
            encrypted_asset(csv_content_override=csv_content)
        ).iter_rows()
    )

    assert row["publish_date"] is None
    assert row["field_errors"] == {"publish_date": "not-a-date"}


@pytest.mark.parametrize(
    "first_column, title, website",
    [
        (str(2**63), "Title", "sehuatang"),
        ("1", "   ", "sehuatang"),
        ("1", "Title", "unknown"),
    ],
)
def test_rejects_invalid_int64_title_or_website(first_column, title, website) -> None:
    csv_content = (
        "tid,number,title,publish_date,magnet,preview_images,detail_url,size,"
        "section,category,website,create_time,update_time\n"
        f"{first_column},,{title},,fixture,,,,亚洲有码,,{website},,\n"
    )

    with pytest.raises(AvdbAssetError):
        asset = decrypt_asset(encrypted_asset(csv_content_override=csv_content))
        list(asset.iter_rows())


def test_rejects_duplicate_required_csv_headers() -> None:
    csv_content = (
        "tid,tid,title,publish_date,magnet,preview_images,detail_url,size,"
        "section,category,website,create_time,update_time\n"
        "1,1,Title,,fixture,,,,亚洲有码,,sehuatang,,\n"
    )

    with pytest.raises(AvdbAssetError):
        asset = decrypt_asset(encrypted_asset(csv_content_override=csv_content))
        list(asset.iter_rows())


def outer_entries(asset: bytes) -> tuple[bytes, bytes]:
    with ZipFile(io.BytesIO(asset)) as archive:
        return (
            archive.read("avdb-resource-library.json"),
            archive.read("avdb-resource-library.bin"),
        )


def build_outer(entries) -> bytes:
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return output.getvalue()


def test_zip_and_manifest_attacks_map_to_stable_invalid_error() -> None:
    manifest, ciphertext = outer_entries(encrypted_asset())
    symlink = ZipInfo("avdb-resource-library.json")
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    attacks = [
        build_outer(
            [
                ("../avdb-resource-library.json", manifest),
                ("avdb-resource-library.bin", ciphertext),
            ]
        ),
        build_outer(
            [
                (symlink, manifest),
                ("avdb-resource-library.bin", ciphertext),
            ]
        ),
        build_outer(
            [
                ("avdb-resource-library.json", b"{" + b" " * (65 * 1024)),
                ("avdb-resource-library.bin", ciphertext),
            ]
        ),
        encrypted_asset(manifest_overrides={"salt": "***"}),
        encrypted_asset(extra_inner_file=True),
    ]
    with pytest.warns(UserWarning):
        duplicate = build_outer(
            [
                ("avdb-resource-library.json", manifest),
                ("avdb-resource-library.json", manifest),
                ("avdb-resource-library.bin", ciphertext),
            ]
        )
    attacks.append(duplicate)

    for attack in attacks:
        with pytest.raises(AvdbAssetError) as error:
            decrypt_asset(attack)
        assert error.value.code == "avdb_asset_invalid"
