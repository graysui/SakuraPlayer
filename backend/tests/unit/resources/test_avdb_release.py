from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import httpx
import pytest

import sakuraplayer.resources.avdb_release as release_module
from sakuraplayer.resources.avdb_crypto import AvdbAssetError
from sakuraplayer.resources.avdb_release import GitHubAvdbReleaseClient

PRIMARY = "li-peifeng/AVdb-Only"
BACKUP = "jzdxjk/AVdb-Only"
TAG = "2026.07.25"
ASSET_NAME = "30D_2026-07-31-12-03-28.zip"


class CloseTracker:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def release(repository: str, content: bytes, *, asset_url: str | None = None) -> dict:
    return {
        "id": 42 if repository == PRIMARY else 84,
        "tag_name": TAG,
        "assets": [
            {
                "name": ASSET_NAME,
                "browser_download_url": asset_url
                or (
                    f"https://github.com/{repository}/releases/download/"
                    f"{TAG}/{ASSET_NAME}"
                ),
                "size": len(content),
                "digest": f"sha256:{sha256(content).hexdigest()}",
            }
        ],
    }


def full_release(repository: str, contents: tuple[bytes, bytes]) -> dict:
    names = (
        "All_sehuatang_1_2026-07-31-12-03-28.zip",
        "All_X1080X_1_2026-07-31-12-03-28.zip",
    )
    return {
        "id": 42,
        "tag_name": TAG,
        "assets": [
            {
                "name": name,
                "browser_download_url": (
                    f"https://github.com/{repository}/releases/download/{TAG}/{name}"
                ),
                "size": len(content),
                "digest": f"sha256:{sha256(content).hexdigest()}",
            }
            for name, content in zip(names, contents)
        ],
    }


def client(handler) -> GitHubAvdbReleaseClient:
    transport = httpx.MockTransport(handler)
    return GitHubAvdbReleaseClient(
        http_client=httpx.Client(transport=transport, follow_redirects=True)
    )


def test_uses_verified_backup_when_primary_discovery_fails(tmp_path) -> None:
    content = b"verified-backup"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/repos/{PRIMARY}/releases/latest":
            return httpx.Response(503)
        if request.url.path == f"/repos/{BACKUP}/releases/latest":
            return httpx.Response(200, json=release(BACKUP, content))
        return httpx.Response(200, content=content)

    fetched = client(handler).fetch_release(
        mode="incremental_30d",
        destination=tmp_path,
        validator=lambda path: Path(path).read_bytes(),
    )

    assert fetched.repository == BACKUP
    assert fetched.release_id == "84"
    assert fetched.assets[0].path.read_bytes() == content
    assert not list(tmp_path.glob("*.part-*"))


def test_prefers_primary_only_after_matching_backup_digest(tmp_path) -> None:
    content = b"same-mirror-content"
    validated: list[Path] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/repos/{PRIMARY}/releases/latest":
            return httpx.Response(200, json=release(PRIMARY, content))
        if request.url.path == f"/repos/{BACKUP}/releases/tags/{TAG}":
            return httpx.Response(200, json=release(BACKUP, content))
        return httpx.Response(200, content=content)

    fetched = client(handler).fetch_release(
        mode="incremental_30d",
        destination=tmp_path,
        validator=lambda path: validated.append(path),
    )

    assert fetched.repository == PRIMARY
    assert fetched.assets[0].sha256 == sha256(content).hexdigest()
    assert fetched.assets[0].path.name == ASSET_NAME
    assert len(validated) == 1


def test_reuses_matching_committed_release_directory(tmp_path) -> None:
    content = b"same-release-content"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/repos/{PRIMARY}/releases/latest":
            return httpx.Response(200, json=release(PRIMARY, content))
        if request.url.path == f"/repos/{BACKUP}/releases/tags/{TAG}":
            return httpx.Response(404)
        return httpx.Response(200, content=content)

    release_client = client(handler)
    first = release_client.fetch_release(
        mode="incremental_30d",
        destination=tmp_path,
        validator=lambda path: Path(path).read_bytes(),
    )
    repeated = release_client.fetch_release(
        mode="incremental_30d",
        destination=tmp_path,
        validator=lambda path: Path(path).read_bytes(),
    )

    assert repeated.assets[0].path == first.assets[0].path
    assert repeated.assets[0].path.read_bytes() == content
    assert not list(tmp_path.glob("*.part-*"))


def test_reuses_full_release_without_changing_asset_order(tmp_path) -> None:
    contents = (b"first", b"second")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/repos/{PRIMARY}/releases/latest":
            return httpx.Response(200, json=full_release(PRIMARY, contents))
        if request.url.path == f"/repos/{BACKUP}/releases/tags/{TAG}":
            return httpx.Response(404)
        content = contents[1] if "X1080X" in request.url.path else contents[0]
        return httpx.Response(200, content=content)

    release_client = client(handler)
    first = release_client.fetch_release(
        mode="full_reconcile",
        destination=tmp_path,
        validator=lambda path: Path(path).read_bytes(),
    )
    repeated = release_client.fetch_release(
        mode="full_reconcile",
        destination=tmp_path,
        validator=lambda path: Path(path).read_bytes(),
    )

    assert [asset.name for asset in repeated.assets] == [
        asset.name for asset in first.assets
    ]


def test_rejects_corrupted_committed_release_directory(tmp_path) -> None:
    content = b"same-release-content"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/repos/{PRIMARY}/releases/latest":
            return httpx.Response(200, json=release(PRIMARY, content))
        if request.url.path == f"/repos/{BACKUP}/releases/tags/{TAG}":
            return httpx.Response(404)
        return httpx.Response(200, content=content)

    release_client = client(handler)
    first = release_client.fetch_release(
        mode="incremental_30d",
        destination=tmp_path,
        validator=lambda path: Path(path).read_bytes(),
    )
    first.assets[0].path.write_bytes(b"corrupted")

    with pytest.raises(AvdbAssetError) as error:
        release_client.fetch_release(
            mode="incremental_30d",
            destination=tmp_path,
            validator=lambda path: Path(path).read_bytes(),
        )

    assert error.value.code == "state_conflict"
    assert not list(tmp_path.glob("*.part-*"))


def test_stops_when_primary_and_backup_digests_differ(tmp_path) -> None:
    contents = {PRIMARY: b"primary", BACKUP: b"backup"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/repos/{PRIMARY}/releases/latest":
            return httpx.Response(200, json=release(PRIMARY, contents[PRIMARY]))
        if request.url.path == f"/repos/{BACKUP}/releases/tags/{TAG}":
            return httpx.Response(200, json=release(BACKUP, contents[BACKUP]))
        repository = PRIMARY if request.url.path.startswith(f"/{PRIMARY}/") else BACKUP
        return httpx.Response(200, content=contents[repository])

    with pytest.raises(AvdbAssetError) as error:
        client(handler).fetch_release(
            mode="incremental_30d",
            destination=tmp_path,
            validator=lambda path: None,
        )

    assert error.value.code == "avdb_asset_digest_mismatch"
    assert list(tmp_path.iterdir()) == []


def test_removes_partial_download_after_interruption(tmp_path) -> None:
    content = b"expected"

    class InterruptedStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"partial"
            raise httpx.ReadError("interrupted")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/repos/{PRIMARY}/releases/latest":
            return httpx.Response(200, json=release(PRIMARY, content))
        if request.url.path == f"/repos/{BACKUP}/releases/tags/{TAG}":
            return httpx.Response(404)
        return httpx.Response(200, stream=InterruptedStream())

    with pytest.raises(AvdbAssetError):
        client(handler).fetch_release(
            mode="incremental_30d",
            destination=tmp_path,
            validator=lambda path: None,
        )

    assert list(tmp_path.iterdir()) == []


def test_rejects_non_https_or_unknown_asset_hosts(tmp_path) -> None:
    content = b"asset"
    payload = release(
        PRIMARY,
        content,
        asset_url=f"https://downloads.example.invalid/{ASSET_NAME}",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(AvdbAssetError) as error:
        client(handler).fetch_release(
            mode="incremental_30d",
            destination=tmp_path,
            validator=lambda path: None,
        )

    assert error.value.code == "avdb_asset_invalid"
    assert list(tmp_path.iterdir()) == []


def test_does_not_follow_metadata_redirect_to_unknown_host(tmp_path) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(
            302,
            headers={"Location": "http://127.0.0.1/internal"},
        )

    with pytest.raises(AvdbAssetError):
        client(handler).fetch_release(
            mode="incremental_30d",
            destination=tmp_path,
            validator=lambda path: None,
        )

    assert len(requested) == 2
    assert all("api.github.com" in url for url in requested)


def test_does_not_follow_asset_redirect_to_unknown_host(tmp_path) -> None:
    content = b"asset"
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.path == f"/repos/{PRIMARY}/releases/latest":
            return httpx.Response(200, json=release(PRIMARY, content))
        if request.url.path == f"/repos/{BACKUP}/releases/tags/{TAG}":
            return httpx.Response(404)
        return httpx.Response(
            302,
            headers={"Location": "https://internal.example.invalid/asset"},
        )

    with pytest.raises(AvdbAssetError):
        client(handler).fetch_release(
            mode="incremental_30d",
            destination=tmp_path,
            validator=lambda path: None,
        )

    assert not any("internal.example.invalid" in url for url in requested)
    assert list(tmp_path.iterdir()) == []


def test_limits_streamed_release_metadata_without_content_length(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(release_module, "MAX_RELEASE_METADATA_BYTES", 8)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.extensions["timeout"]["connect"] == 10.0
        return httpx.Response(200, content=b"{" + b"x" * 20)

    with pytest.raises(AvdbAssetError):
        client(handler).fetch_release(
            mode="incremental_30d",
            destination=tmp_path,
            validator=lambda path: None,
        )


def test_cleans_partial_file_when_validator_raises_unexpected_error(tmp_path) -> None:
    content = b"asset"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/repos/{PRIMARY}/releases/latest":
            return httpx.Response(200, json=release(PRIMARY, content))
        if request.url.path == f"/repos/{BACKUP}/releases/tags/{TAG}":
            return httpx.Response(404)
        return httpx.Response(200, content=content)

    with pytest.raises(AvdbAssetError) as error:
        client(handler).fetch_release(
            mode="incremental_30d",
            destination=tmp_path,
            validator=lambda path: (_ for _ in ()).throw(RuntimeError("boom")),
        )

    assert error.value.code == "internal_error"
    assert list(tmp_path.iterdir()) == []


def test_closes_prior_validation_when_later_full_asset_is_invalid(tmp_path) -> None:
    contents = (b"first", b"second")
    first_validation = CloseTracker()
    validation_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/repos/{PRIMARY}/releases/latest":
            return httpx.Response(200, json=full_release(PRIMARY, contents))
        if request.url.path == f"/repos/{BACKUP}/releases/tags/{TAG}":
            return httpx.Response(404)
        content = contents[1] if "X1080X" in request.url.path else contents[0]
        return httpx.Response(200, content=content)

    def validate(path: Path):
        nonlocal validation_calls
        del path
        validation_calls += 1
        if validation_calls == 2:
            raise AvdbAssetError()
        return first_validation

    with pytest.raises(AvdbAssetError):
        client(handler).fetch_release(
            mode="full_reconcile",
            destination=tmp_path,
            validator=validate,
        )

    assert first_validation.closed
    assert list(tmp_path.iterdir()) == []


def test_full_release_commit_failure_leaves_no_partial_directory(
    tmp_path,
    monkeypatch,
) -> None:
    contents = (b"first", b"second")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/repos/{PRIMARY}/releases/latest":
            return httpx.Response(200, json=full_release(PRIMARY, contents))
        if request.url.path == f"/repos/{BACKUP}/releases/tags/{TAG}":
            return httpx.Response(404)
        content = contents[1] if "X1080X" in request.url.path else contents[0]
        return httpx.Response(200, content=content)

    original_replace = release_module.os.replace
    calls = 0

    def fail_second_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated move failure")
        original_replace(source, destination)

    validations = [CloseTracker(), CloseTracker()]
    pending_validations = iter(validations)
    monkeypatch.setattr(release_module.os, "replace", fail_second_replace)
    with pytest.raises(AvdbAssetError) as error:
        client(handler).fetch_release(
            mode="full_reconcile",
            destination=tmp_path,
            validator=lambda path: next(pending_validations),
        )

    assert error.value.code == "internal_error"
    assert all(validation.closed for validation in validations)
    assert list(tmp_path.iterdir()) == []
