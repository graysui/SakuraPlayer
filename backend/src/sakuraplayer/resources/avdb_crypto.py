from __future__ import annotations

import base64
import csv
import hmac
import io
import json
import logging
import os
import re
import stat
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime
from hashlib import pbkdf2_hmac, sha256
from pathlib import Path, PurePosixPath
from typing import Iterator
from urllib.parse import urlparse
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile, ZipInfo

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

PUBLIC_PASSWORD_DIGEST = (
    "ca42e687df5818e2e88da0ff5b9fd2c60f7e22721f682b66c3e50485a00d06d5"
)
PBKDF2_ITERATIONS = 200_000
MAX_OUTER_BYTES = 512 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAX_INNER_BYTES = 1024 * 1024 * 1024

_OUTER_FILES = {
    "avdb-resource-library.json",
    "avdb-resource-library.bin",
}
_REQUIRED_FIELDS = {
    "tid",
    "number",
    "title",
    "publish_date",
    "magnet",
    "preview_images",
    "detail_url",
    "size",
    "section",
    "category",
    "website",
    "create_time",
    "update_time",
}
_ASSET_TIMESTAMP = r"(?:[0-9]{8,14}|[0-9]{4}(?:-[0-9]{2}){5})"
_INCREMENTAL_NAME = re.compile(rf"30D_{_ASSET_TIMESTAMP}\.zip")
_FULL_NAME = re.compile(
    rf"All_(?:sehuatang|X1080X)_[1-9][0-9]*_{_ASSET_TIMESTAMP}\.zip"
)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_PUBLIC_ENVELOPE_FIELDS = frozenset(
    {"format", "version", "payload", "original_filename"}
)
_MANIFEST_FIELDS = frozenset(
    {
        "salt",
        "nonce",
        "tag",
        "iterations",
        "algorithm",
        "kdf",
        "key_length",
        *_PUBLIC_ENVELOPE_FIELDS,
    }
)
_SUPPORTED_COMPRESSION = frozenset({ZIP_STORED, ZIP_DEFLATED})
_LOGGER = logging.getLogger(__name__)


class AvdbAssetError(ValueError):
    def __init__(self, code: str = "avdb_asset_invalid") -> None:
        self.code = code
        super().__init__(code)


@dataclass
class DecryptedAsset:
    manifest_summary: dict[str, object]
    inner_zip_path: Path = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def iter_rows(self) -> Iterator[dict[str, object]]:
        if self._closed:
            raise AvdbAssetError()
        try:
            with ZipFile(self.inner_zip_path) as archive:
                entries = archive.infolist()
                if len(entries) != 1:
                    raise AvdbAssetError()
                info = entries[0]
                _validate_zip_info(info)
                if not info.filename.lower().endswith(".csv"):
                    raise AvdbAssetError()
                if info.file_size <= 0 or info.file_size > MAX_INNER_BYTES:
                    raise AvdbAssetError()
                _validate_compression_ratio(info.file_size, info.compress_size)
                with archive.open(info) as raw:
                    text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                    reader = csv.DictReader(text)
                    field_names = reader.fieldnames or []
                    fields = set(field_names)
                    if len(field_names) != len(fields):
                        raise AvdbAssetError()
                    if not _REQUIRED_FIELDS.issubset(fields):
                        raise AvdbAssetError()
                    extra_field_count = len(fields - _REQUIRED_FIELDS)
                    if extra_field_count:
                        _LOGGER.warning(
                            "avdb_csv_extra_fields count=%d",
                            extra_field_count,
                        )
                    for row in reader:
                        if None in row:
                            raise AvdbAssetError()
                        yield _parse_row(row)
        except AvdbAssetError:
            raise
        except (
            BadZipFile,
            csv.Error,
            UnicodeError,
            OSError,
            RuntimeError,
            NotImplementedError,
            ValueError,
        ):
            raise AvdbAssetError() from None

    def close(self) -> None:
        if not self._closed:
            self.inner_zip_path.unlink(missing_ok=True)
            self._closed = True

    def __enter__(self) -> DecryptedAsset:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        del exc_type, exc_value, traceback
        self.close()


def validate_asset_name(name: str, *, mode: str) -> str:
    pattern = {
        "incremental_30d": _INCREMENTAL_NAME,
        "full_reconcile": _FULL_NAME,
    }.get(mode)
    if pattern is None or pattern.fullmatch(name) is None:
        raise AvdbAssetError()
    return name


def verify_asset_digest(data: bytes, expected_sha256: str) -> str:
    if not isinstance(data, bytes) or not _SHA256.fullmatch(expected_sha256):
        raise AvdbAssetError()
    actual = sha256(data).hexdigest()
    if not hmac.compare_digest(actual, expected_sha256):
        raise AvdbAssetError("avdb_asset_digest_mismatch")
    return actual


def decrypt_asset(outer_zip: bytes) -> DecryptedAsset:
    if not isinstance(outer_zip, bytes) or not 0 < len(outer_zip) <= MAX_OUTER_BYTES:
        raise AvdbAssetError()
    descriptor, outer_name = tempfile.mkstemp(suffix=".outer.zip")
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(outer_zip)
        return decrypt_asset_file(Path(outer_name))
    finally:
        Path(outer_name).unlink(missing_ok=True)


def decrypt_asset_file(
    outer_zip_path: Path,
    *,
    temp_directory: Path | None = None,
) -> DecryptedAsset:
    outer_zip_path = Path(outer_zip_path)
    try:
        outer_size = outer_zip_path.stat().st_size
    except OSError:
        raise AvdbAssetError() from None
    if not 0 < outer_size <= MAX_OUTER_BYTES:
        raise AvdbAssetError()

    inner_path: Path | None = None
    try:
        with ZipFile(outer_zip_path) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(entries) != 2 or len(names) != len(set(names)):
                raise AvdbAssetError()
            if set(names) != _OUTER_FILES:
                raise AvdbAssetError()
            for entry in entries:
                _validate_zip_info(entry)
                _validate_compression_ratio(entry.file_size, entry.compress_size)
            manifest_info = archive.getinfo("avdb-resource-library.json")
            encrypted_info = archive.getinfo("avdb-resource-library.bin")
            if not 0 < manifest_info.file_size <= MAX_MANIFEST_BYTES:
                raise AvdbAssetError()
            if not 0 < encrypted_info.file_size <= MAX_OUTER_BYTES:
                raise AvdbAssetError()
            manifest = _load_manifest(archive.read(manifest_info))
            key = pbkdf2_hmac(
                "sha256",
                bytes.fromhex(PUBLIC_PASSWORD_DIGEST),
                manifest["salt"],
                PBKDF2_ITERATIONS,
                dklen=32,
            )
            if temp_directory is not None:
                temp_directory = Path(temp_directory)
                if not temp_directory.is_dir():
                    raise AvdbAssetError()
            inner_descriptor, inner_name = tempfile.mkstemp(
                suffix=".inner.zip",
                dir=temp_directory,
            )
            inner_path = Path(inner_name)
            decryptor = Cipher(
                algorithms.AES(key),
                modes.GCM(manifest["nonce"], manifest["tag"]),
            ).decryptor()
            plaintext_size = 0
            with (
                archive.open(encrypted_info) as encrypted,
                os.fdopen(
                    inner_descriptor,
                    "wb",
                ) as plaintext,
            ):
                while True:
                    chunk = encrypted.read(1024 * 1024)
                    if not chunk:
                        break
                    decrypted = decryptor.update(chunk)
                    plaintext_size += len(decrypted)
                    if plaintext_size > MAX_INNER_BYTES:
                        raise AvdbAssetError()
                    plaintext.write(decrypted)
                final = decryptor.finalize()
                plaintext_size += len(final)
                if not 0 < plaintext_size <= MAX_INNER_BYTES:
                    raise AvdbAssetError()
                plaintext.write(final)
                plaintext.flush()
                os.fsync(plaintext.fileno())
        _validate_inner_zip(inner_path)
    except AvdbAssetError:
        if inner_path is not None:
            inner_path.unlink(missing_ok=True)
        raise
    except InvalidTag:
        if inner_path is not None:
            inner_path.unlink(missing_ok=True)
        raise AvdbAssetError("avdb_decryption_failed") from None
    except (
        BadZipFile,
        KeyError,
        NotImplementedError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        if inner_path is not None:
            inner_path.unlink(missing_ok=True)
        raise AvdbAssetError() from None
    if inner_path is None:
        raise AvdbAssetError()
    return DecryptedAsset(
        manifest_summary={
            "algorithm": "AES-256-GCM",
            "iterations": PBKDF2_ITERATIONS,
            "kdf": "PBKDF2-HMAC-SHA256",
            "key_length": 32,
        },
        inner_zip_path=inner_path,
    )


def _load_manifest(raw: bytes) -> dict[str, object]:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise AvdbAssetError()
            result[key] = value
        return result

    try:
        manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except AvdbAssetError:
        raise
    except (UnicodeError, json.JSONDecodeError, TypeError):
        raise AvdbAssetError() from None
    if not isinstance(manifest, dict):
        raise AvdbAssetError()
    if not set(manifest).issubset(_MANIFEST_FIELDS):
        raise AvdbAssetError()
    envelope_fields = set(manifest).intersection(_PUBLIC_ENVELOPE_FIELDS)
    if envelope_fields and envelope_fields != _PUBLIC_ENVELOPE_FIELDS:
        raise AvdbAssetError()
    if envelope_fields:
        original_filename = manifest["original_filename"]
        if (
            manifest["format"] != "avdb-resource-library"
            or type(manifest["version"]) is not int
            or manifest["version"] != 1
            or manifest["payload"] != "avdb-resource-library.bin"
            or not isinstance(original_filename, str)
            or (
                _INCREMENTAL_NAME.fullmatch(original_filename) is None
                and _FULL_NAME.fullmatch(original_filename) is None
            )
        ):
            raise AvdbAssetError()
    if (
        type(manifest.get("iterations")) is not int
        or manifest["iterations"] != PBKDF2_ITERATIONS
    ):
        raise AvdbAssetError()
    optional_values = {
        "algorithm": "AES-256-GCM",
        "kdf": "PBKDF2-HMAC-SHA256",
        "key_length": 32,
    }
    for key, expected in optional_values.items():
        if key == "key_length" and key in manifest:
            if type(manifest[key]) is not int or manifest[key] != expected:
                raise AvdbAssetError()
        elif key in manifest and manifest[key] != expected:
            raise AvdbAssetError()
    decoded = {
        "salt": _decode_manifest_value(manifest.get("salt"), 16),
        "nonce": _decode_manifest_value(manifest.get("nonce"), 12),
        "tag": _decode_manifest_value(manifest.get("tag"), 16),
    }
    return {**manifest, **decoded}


def _decode_manifest_value(value: object, expected_length: int) -> bytes:
    if not isinstance(value, str):
        raise AvdbAssetError()
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        raise AvdbAssetError() from None
    if len(decoded) != expected_length:
        raise AvdbAssetError()
    return decoded


def _validate_inner_zip(path: Path) -> None:
    try:
        with ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) != 1:
                raise AvdbAssetError()
            info = entries[0]
            _validate_zip_info(info)
            if not info.filename.lower().endswith(".csv"):
                raise AvdbAssetError()
            if not 0 < info.file_size <= MAX_INNER_BYTES:
                raise AvdbAssetError()
            _validate_compression_ratio(info.file_size, info.compress_size)
    except AvdbAssetError:
        raise
    except (BadZipFile, NotImplementedError, OSError, RuntimeError, ValueError):
        raise AvdbAssetError() from None


def _validate_zip_info(info: ZipInfo) -> None:
    path = PurePosixPath(info.filename)
    mode = info.external_attr >> 16
    if (
        not info.filename
        or "\\" in info.filename
        or path.is_absolute()
        or ".." in path.parts
        or len(path.parts) != 1
        or stat.S_ISLNK(mode)
        or info.flag_bits & 0x1
        or info.compress_type not in _SUPPORTED_COMPRESSION
    ):
        raise AvdbAssetError()


def _validate_compression_ratio(file_size: int, compressed_size: int) -> None:
    if file_size < 0 or compressed_size < 0:
        raise AvdbAssetError()
    if file_size > 1024 * 1024 and file_size > max(compressed_size, 1) * 1000:
        raise AvdbAssetError()


def _parse_row(row: dict[str | None, str | None]) -> dict[str, object]:
    field_errors: dict[str, str] = {}
    tid = _parse_int(row.get("tid"), field="tid", nullable=False)
    title = _required_text(row.get("title"))
    website = _required_text(row.get("website"))
    if website not in {"sehuatang", "x1080x"}:
        raise AvdbAssetError()
    publish_date = _parse_date(row.get("publish_date"), "publish_date", field_errors)
    create_time = _parse_datetime(row.get("create_time"), "create_time", field_errors)
    update_time = _parse_datetime(row.get("update_time"), "update_time", field_errors)
    detail_url = _parse_url(row.get("detail_url"), "detail_url", field_errors)
    preview_images = _parse_preview_urls(row.get("preview_images"), field_errors)
    parsed: dict[str, object] = {
        "tid": tid,
        "number": _optional_text(row.get("number")),
        "title": title,
        "publish_date": publish_date,
        "magnet": _required_text(row.get("magnet")),
        "preview_images": preview_images,
        "detail_url": detail_url,
        "size": _parse_int(row.get("size"), field="size", nullable=True),
        "section": _required_text(row.get("section")),
        "category": _optional_text(row.get("category")),
        "website": website,
        "create_time": create_time,
        "update_time": update_time,
    }
    if field_errors:
        parsed["field_errors"] = field_errors
    return parsed


def _required_text(value: str | None) -> str:
    normalized = _optional_text(value)
    if normalized is None:
        raise AvdbAssetError()
    return normalized


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _parse_int(value: str | None, *, field: str, nullable: bool) -> int | None:
    normalized = _optional_text(value)
    if normalized is None:
        if nullable:
            return None
        raise AvdbAssetError()
    try:
        parsed = int(normalized)
    except ValueError:
        raise AvdbAssetError() from None
    if not -(2**63) <= parsed < 2**63 or (field == "size" and parsed < 0):
        raise AvdbAssetError()
    return parsed


def _parse_date(
    value: str | None,
    field: str,
    errors: dict[str, str],
) -> date | None:
    normalized = _optional_text(value)
    if normalized is None:
        return None
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        errors[field] = normalized
        return None


def _parse_datetime(
    value: str | None,
    field: str,
    errors: dict[str, str],
) -> datetime | None:
    normalized = _optional_text(value)
    if normalized is None:
        return None
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        errors[field] = normalized
        return None


def _parse_url(
    value: str | None,
    field: str,
    errors: dict[str, str],
) -> str | None:
    normalized = _optional_text(value)
    if normalized is None:
        return None
    try:
        parsed = urlparse(normalized)
        port = parsed.port
    except ValueError:
        parsed = None
        port = None
    if (
        parsed is None
        or parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.fragment
    ):
        errors[field] = "invalid_url"
        return None
    return normalized


def _parse_preview_urls(
    value: str | None,
    errors: dict[str, str],
) -> str | None:
    normalized = _optional_text(value)
    if normalized is None:
        return None
    accepted: list[str] = []
    invalid = False
    for index, item in enumerate(normalized.split(",")):
        local_errors: dict[str, str] = {}
        parsed = _parse_url(item, f"preview_images[{index}]", local_errors)
        if parsed is None:
            invalid = True
        else:
            accepted.append(parsed)
    if invalid:
        errors["preview_images"] = "contains_invalid_url"
    return ",".join(accepted) or None
