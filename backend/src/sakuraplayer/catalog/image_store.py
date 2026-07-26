from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import warnings
import uuid

import httpx
from PIL import Image, UnidentifiedImageError


ALLOWED_IMAGE_HOST = "c0.jdbstatic.com"
ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_REDIRECTS = 3
MAX_IMAGE_DIMENSION = 12_000
MAX_IMAGE_PIXELS = 40_000_000
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_FORMAT_TO_CONTENT_TYPE = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
_FORMAT_TO_EXTENSION = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


class ImageStoreProblem(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class StoredImage:
    relative_path: str
    sha256: str
    byte_size: int
    content_type: str
    width: int
    height: int
    created_new: bool


class PermanentImageStore:
    def __init__(self, *, root: Path, http_client: httpx.Client) -> None:
        self._root = Path(root)
        self._http = http_client

    def ensure_placeholder(self) -> str:
        relative_path = Path("_placeholder") / "catalog.png"
        target = self._root / relative_path
        if target.is_file():
            return relative_path.as_posix()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.parent / f".catalog.png.part-{uuid.uuid4().hex}"
        try:
            Image.new("RGB", (1, 1), color=(96, 96, 96)).save(
                temporary,
                format="PNG",
            )
            with temporary.open("rb+") as output:
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
        except OSError:
            raise ImageStoreProblem("image_download_failed") from None
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        return relative_path.as_posix()

    def discard(self, stored: StoredImage) -> None:
        if not stored.created_new:
            return
        target = (self._root / stored.relative_path).resolve()
        root = self._root.resolve()
        if root not in target.parents:
            raise ValueError("image path escapes permanent root")
        try:
            target.unlink(missing_ok=True)
        except OSError:
            raise ImageStoreProblem("image_download_failed") from None

    def store(
        self,
        *,
        owner_type: str,
        owner_id: uuid.UUID,
        kind: str,
        position: int,
        source_url: str,
    ) -> StoredImage:
        if owner_type not in {"movie", "actor"}:
            raise ValueError("invalid image owner type")
        if kind not in {"cover", "plot", "profile"} or position < 0:
            raise ValueError("invalid image identity")
        current_url = _validate_url(source_url)
        directory = self._root / owner_type / str(owner_id)
        temporary: Path | None = None
        try:
            response = self._fetch(current_url)
            try:
                declared_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if declared_type not in ALLOWED_CONTENT_TYPES:
                    raise ImageStoreProblem("image_content_type_invalid")
                declared_length = response.headers.get("Content-Length")
                if declared_length is not None:
                    try:
                        if int(declared_length) > MAX_IMAGE_BYTES:
                            raise ImageStoreProblem("image_too_large")
                    except ValueError:
                        raise ImageStoreProblem("image_download_failed") from None
                directory.mkdir(parents=True, exist_ok=True)
                for stale in directory.glob(f".{kind}-{position}.part-*"):
                    stale.unlink()
                temporary = directory / f".{kind}-{position}.part-{uuid.uuid4().hex}"
                digest = sha256()
                byte_size = 0
                with temporary.open("xb") as output:
                    for chunk in response.iter_bytes():
                        byte_size += len(chunk)
                        if byte_size > MAX_IMAGE_BYTES:
                            raise ImageStoreProblem("image_too_large")
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
            finally:
                response.close()
            format_name, width, height = _validate_image(temporary, declared_type)
            digest_hex = digest.hexdigest()
            extension = _FORMAT_TO_EXTENSION[format_name]
            target = directory / f"{kind}-{position}-{digest_hex[:16]}.{extension}"
            created_new = not target.exists()
            if created_new:
                os.replace(temporary, target)
            else:
                existing_digest = sha256(target.read_bytes()).hexdigest()
                if existing_digest != digest_hex:
                    os.replace(temporary, target)
                else:
                    temporary.unlink()
            temporary = None
            return StoredImage(
                relative_path=target.relative_to(self._root).as_posix(),
                sha256=digest_hex,
                byte_size=byte_size,
                content_type=declared_type,
                width=width,
                height=height,
                created_new=created_new,
            )
        except ImageStoreProblem:
            raise
        except (httpx.HTTPError, OSError, ValueError):
            raise ImageStoreProblem("image_download_failed") from None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def _fetch(self, initial_url: httpx.URL) -> httpx.Response:
        current = initial_url
        visited: set[str] = set()
        for redirect_count in range(MAX_REDIRECTS + 1):
            serialized = str(current)
            if serialized in visited:
                raise ImageStoreProblem("image_download_failed")
            visited.add(serialized)
            try:
                request = self._http.build_request("GET", current)
                response = self._http.send(request, stream=True, follow_redirects=False)
            except httpx.HTTPError:
                raise ImageStoreProblem("image_download_failed") from None
            if response.status_code not in _REDIRECT_STATUSES:
                if response.status_code != 200:
                    response.close()
                    raise ImageStoreProblem("image_download_failed")
                return response
            location = response.headers.get("Location")
            response.close()
            if redirect_count >= MAX_REDIRECTS or not location:
                raise ImageStoreProblem("image_download_failed")
            current = _validate_url(str(current.join(location)))
        raise ImageStoreProblem("image_download_failed")


def _validate_url(value: str) -> httpx.URL:
    try:
        url = httpx.URL(value)
    except (TypeError, ValueError):
        raise ImageStoreProblem("image_source_not_allowed") from None
    if (
        url.scheme != "https"
        or url.host != ALLOWED_IMAGE_HOST
        or url.userinfo
        or url.port not in {None, 443}
    ):
        raise ImageStoreProblem("image_source_not_allowed")
    return url


def _validate_image(path: Path, declared_type: str) -> tuple[str, int, int]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                format_name = image.format or ""
                width, height = image.size
                if (
                    width < 1
                    or height < 1
                    or width > MAX_IMAGE_DIMENSION
                    or height > MAX_IMAGE_DIMENSION
                    or width * height > MAX_IMAGE_PIXELS
                ):
                    raise ImageStoreProblem("image_dimensions_invalid")
                if _FORMAT_TO_CONTENT_TYPE.get(format_name) != declared_type:
                    raise ImageStoreProblem("image_content_type_invalid")
                image.load()
    except ImageStoreProblem:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, ValueError):
        raise ImageStoreProblem("image_download_failed") from None
    return format_name, width, height


__all__ = ["ImageStoreProblem", "PermanentImageStore", "StoredImage"]
