from __future__ import annotations

from io import BytesIO
from pathlib import Path
import uuid

import httpx
from PIL import Image
import pytest

import sakuraplayer.catalog.image_store as image_store_module
from sakuraplayer.catalog.image_store import ImageStoreProblem, PermanentImageStore


URL = "https://c0.jdbstatic.com/images/fixture.png"


def image_bytes(format_name: str = "PNG", size: tuple[int, int] = (2, 2)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color=(120, 30, 60)).save(output, format=format_name)
    return output.getvalue()


def store(tmp_path: Path, handler) -> PermanentImageStore:
    return PermanentImageStore(
        root=tmp_path,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_downloads_valid_image_to_server_generated_atomic_path(tmp_path: Path) -> None:
    content = image_bytes()
    images = store(
        tmp_path,
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "image/png"},
            content=content,
        ),
    )

    stored = images.store(
        owner_type="movie",
        owner_id=uuid.UUID("00000000-0000-0000-0000-000000000123"),
        kind="cover",
        position=0,
        source_url=URL,
    )

    path = tmp_path / stored.relative_path
    assert path.read_bytes() == content
    assert stored.content_type == "image/png"
    assert stored.width == 2 and stored.height == 2
    assert stored.created_new is True
    assert stored.relative_path.startswith("movie/00000000-0000-0000-0000-000000000123/")
    assert not list(tmp_path.rglob("*.part-*"))


def test_retry_removes_only_same_image_stale_partial(tmp_path: Path) -> None:
    owner_id = uuid.uuid4()
    directory = tmp_path / "movie" / str(owner_id)
    directory.mkdir(parents=True)
    stale = directory / ".cover-0.part-deadbeef"
    unrelated = directory / ".plot-0.part-activefixture"
    stale.write_bytes(b"partial")
    unrelated.write_bytes(b"other image")
    images = store(
        tmp_path,
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "image/png"},
            content=image_bytes(),
        ),
    )

    images.store(
        owner_type="movie",
        owner_id=owner_id,
        kind="cover",
        position=0,
        source_url=URL,
    )

    assert not stale.exists()
    assert unrelated.read_bytes() == b"other image"


def test_creates_and_reuses_local_placeholder_atomically(tmp_path: Path) -> None:
    images = store(tmp_path, lambda request: pytest.fail("network must not be used"))

    first = images.ensure_placeholder()
    second = images.ensure_placeholder()

    assert first == second == "_placeholder/catalog.png"
    with Image.open(tmp_path / first) as placeholder:
        assert placeholder.format == "PNG"
        assert placeholder.size == (1, 1)
        placeholder.load()
    assert not list(tmp_path.rglob("*.part-*"))


@pytest.mark.parametrize(
    "url",
    [
        "http://c0.jdbstatic.com/image.png",
        "https://user@c0.jdbstatic.com/image.png",
        "https://c0.jdbstatic.com:444/image.png",
        "https://evil.c0.jdbstatic.com/image.png",
        "https://127.0.0.1/image.png",
    ],
)
def test_rejects_non_allowlisted_url_before_network(tmp_path: Path, url: str) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200)

    with pytest.raises(ImageStoreProblem) as error:
        store(tmp_path, handler).store(
            owner_type="movie",
            owner_id=uuid.uuid4(),
            kind="cover",
            position=0,
            source_url=url,
        )

    assert error.value.code == "image_source_not_allowed"
    assert calls == 0


def test_revalidates_every_redirect_and_limits_hops(tmp_path: Path) -> None:
    requested: list[str] = []

    def unsafe_handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})

    with pytest.raises(ImageStoreProblem) as unsafe:
        store(tmp_path, unsafe_handler).store(
            owner_type="movie",
            owner_id=uuid.uuid4(),
            kind="cover",
            position=0,
            source_url=URL,
        )
    assert unsafe.value.code == "image_source_not_allowed"
    assert len(requested) == 1

    def loop_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "/images/fixture.png"})

    with pytest.raises(ImageStoreProblem) as loop:
        store(tmp_path, loop_handler).store(
            owner_type="movie",
            owner_id=uuid.uuid4(),
            kind="cover",
            position=0,
            source_url=URL,
        )
    assert loop.value.code == "image_download_failed"

    content = image_bytes()
    hops = 0

    def three_hops(request: httpx.Request) -> httpx.Response:
        nonlocal hops
        if hops < 3:
            hops += 1
            return httpx.Response(
                302,
                headers={"Location": f"/images/hop-{hops}.png"},
            )
        return httpx.Response(
            200,
            headers={"Content-Type": "image/png"},
            content=content,
        )

    stored = store(tmp_path, three_hops).store(
        owner_type="movie",
        owner_id=uuid.uuid4(),
        kind="cover",
        position=0,
        source_url=URL,
    )
    assert (tmp_path / stored.relative_path).is_file()
    assert hops == 3

    def fourth_hop(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "/images/next.png"})

    with pytest.raises(ImageStoreProblem) as too_many:
        store(tmp_path, fourth_hop).store(
            owner_type="movie",
            owner_id=uuid.uuid4(),
            kind="cover",
            position=0,
            source_url=URL,
        )
    assert too_many.value.code == "image_download_failed"


def test_rejects_mime_mismatch_and_stream_size_limit(tmp_path: Path, monkeypatch) -> None:
    jpeg = image_bytes("JPEG")
    mismatch = store(
        tmp_path,
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "image/png"},
            content=jpeg,
        ),
    )
    with pytest.raises(ImageStoreProblem) as content_type:
        mismatch.store(
            owner_type="movie",
            owner_id=uuid.uuid4(),
            kind="cover",
            position=0,
            source_url=URL,
        )
    assert content_type.value.code == "image_content_type_invalid"

    monkeypatch.setattr(image_store_module, "MAX_IMAGE_BYTES", 8)
    oversized = store(
        tmp_path,
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "image/png"},
            content=b"x" * 9,
        ),
    )
    with pytest.raises(ImageStoreProblem) as too_large:
        oversized.store(
            owner_type="movie",
            owner_id=uuid.uuid4(),
            kind="cover",
            position=0,
            source_url=URL,
        )
    assert too_large.value.code == "image_too_large"
    assert not list(tmp_path.rglob("*.part-*"))

    class UnknownLength(httpx.SyncByteStream):
        def __iter__(self):
            yield b"1234"
            yield b"56789"

    streamed = store(
        tmp_path,
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "image/png"},
            stream=UnknownLength(),
        ),
    )
    with pytest.raises(ImageStoreProblem) as streamed_too_large:
        streamed.store(
            owner_type="movie",
            owner_id=uuid.uuid4(),
            kind="cover",
            position=0,
            source_url=URL,
        )
    assert streamed_too_large.value.code == "image_too_large"
    assert not list(tmp_path.rglob("*.part-*"))


def test_rejects_dimensions_and_cleans_interrupted_partial(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(image_store_module, "MAX_IMAGE_DIMENSION", 1)
    dimensions = store(
        tmp_path,
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "image/png"},
            content=image_bytes(size=(2, 1)),
        ),
    )
    with pytest.raises(ImageStoreProblem) as invalid:
        dimensions.store(
            owner_type="movie",
            owner_id=uuid.uuid4(),
            kind="cover",
            position=0,
            source_url=URL,
        )
    assert invalid.value.code == "image_dimensions_invalid"

    monkeypatch.setattr(image_store_module, "MAX_IMAGE_DIMENSION", 12_000)
    monkeypatch.setattr(image_store_module, "MAX_IMAGE_PIXELS", 1)
    pixels = store(
        tmp_path,
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "image/png"},
            content=image_bytes(size=(2, 1)),
        ),
    )
    with pytest.raises(ImageStoreProblem) as too_many_pixels:
        pixels.store(
            owner_type="movie",
            owner_id=uuid.uuid4(),
            kind="cover",
            position=0,
            source_url=URL,
        )
    assert too_many_pixels.value.code == "image_dimensions_invalid"

    class Interrupted(httpx.SyncByteStream):
        def __iter__(self):
            yield b"partial"
            raise httpx.ReadError("fixture interruption")

    interrupted = store(
        tmp_path,
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "image/png"},
            stream=Interrupted(),
        ),
    )
    with pytest.raises(ImageStoreProblem) as download:
        interrupted.store(
            owner_type="movie",
            owner_id=uuid.uuid4(),
            kind="cover",
            position=0,
            source_url=URL,
        )
    assert download.value.code == "image_download_failed"
    assert not list(tmp_path.rglob("*.part-*"))


def test_atomic_replace_failure_leaves_no_partial(tmp_path: Path, monkeypatch) -> None:
    images = store(
        tmp_path,
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "image/png"},
            content=image_bytes(),
        ),
    )

    def fail_replace(source, destination):
        raise OSError("fixture replace failure")

    monkeypatch.setattr(image_store_module.os, "replace", fail_replace)
    with pytest.raises(ImageStoreProblem) as error:
        images.store(
            owner_type="movie",
            owner_id=uuid.uuid4(),
            kind="cover",
            position=0,
            source_url=URL,
        )

    assert error.value.code == "image_download_failed"
    assert not list(tmp_path.rglob("*.part-*"))


def test_failed_replacement_does_not_remove_existing_ready_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    owner_id = uuid.uuid4()
    first_content = image_bytes(size=(2, 2))
    first = store(
        tmp_path,
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "image/png"},
            content=first_content,
        ),
    ).store(
        owner_type="movie",
        owner_id=owner_id,
        kind="cover",
        position=0,
        source_url=URL,
    )
    existing = tmp_path / first.relative_path

    monkeypatch.setattr(
        image_store_module.os,
        "replace",
        lambda source, destination: (_ for _ in ()).throw(OSError("fixture")),
    )
    second = store(
        tmp_path,
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "image/png"},
            content=image_bytes(size=(3, 2)),
        ),
    )
    with pytest.raises(ImageStoreProblem):
        second.store(
            owner_type="movie",
            owner_id=owner_id,
            kind="cover",
            position=0,
            source_url=URL,
        )

    assert existing.read_bytes() == first_content
    assert not list(tmp_path.rglob("*.part-*"))


def test_reused_digest_is_not_deleted_by_failed_database_compensation(
    tmp_path: Path,
) -> None:
    owner_id = uuid.uuid4()
    content = image_bytes()
    images = store(
        tmp_path,
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "image/png"},
            content=content,
        ),
    )
    first = images.store(
        owner_type="movie",
        owner_id=owner_id,
        kind="cover",
        position=0,
        source_url=URL,
    )
    reused = images.store(
        owner_type="movie",
        owner_id=owner_id,
        kind="cover",
        position=0,
        source_url=URL,
    )

    assert first.created_new is True
    assert reused.created_new is False
    assert first.relative_path == reused.relative_path
    images.discard(reused)
    assert (tmp_path / first.relative_path).read_bytes() == content
