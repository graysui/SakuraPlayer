from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from urllib.parse import urlparse
import uuid

from sqlalchemy import case, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.identity.crypto import SecretCipher
from sakuraplayer.resources.models import Movie, ResourceSource
from sakuraplayer.resources.number_normalizer import normalize_movie_number
from sakuraplayer.resources.sync_service import BatchStats


TARGET_SECTIONS = frozenset(
    {"亚洲有码", "亚洲无码", "中文字幕", "4K原版", "素人有码", "FC2"}
)
_DETAIL_HOST_SUFFIXES = {
    "sehuatang": ("sehuatang.net",),
    "x1080x": ("x1080x.com",),
}


class SourceImportError(ValueError):
    code = "avdb_asset_invalid"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True)
class _PreparedSource:
    website: str
    external_post_id: int
    raw_number: str | None
    normalized_number: str | None
    title: str
    publish_date: date | None
    section: str
    category: str | None
    resource_size_mb: int | None
    detail_url: str | None
    preview_urls: list[str]
    magnet: str
    source_created_at: datetime | None
    source_updated_at: datetime | None


def source_magnet_context(website: str, external_post_id: int) -> bytes:
    return f"resource_source:{website}:{external_post_id}".encode("ascii")


class SourceImporter:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        cipher: SecretCipher,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._cipher = cipher
        self._now = now or (lambda: datetime.now(timezone.utc))

    def import_batch(
        self,
        asset_name: str,
        rows: tuple[dict[str, object], ...],
    ) -> BatchStats:
        if not asset_name or not isinstance(rows, tuple):
            raise SourceImportError
        prepared_by_key: dict[tuple[str, int], _PreparedSource] = {}
        skipped = 0
        for row in rows:
            section = _required_text(row, "section")
            if section not in TARGET_SECTIONS:
                skipped += 1
                continue
            item = self._prepare(row, section=section)
            key = (item.website, item.external_post_id)
            if key in prepared_by_key:
                skipped += 1
            prepared_by_key[key] = item

        prepared = list(prepared_by_key.values())
        if not prepared:
            return BatchStats(skipped=skipped)
        current = self._utc_now()
        with self._session_factory.begin() as session:
            movies = self._upsert_movies(session, prepared, current=current)
            existing = self._lock_existing_sources(session, prepared)
            self._upsert_sources(
                session,
                prepared,
                movies=movies,
                current=current,
            )
        pending = sum(
            item.normalized_number is None
            and existing.get((item.website, item.external_post_id)) != "manual"
            for item in prepared
        )
        inserted = sum(
            (item.website, item.external_post_id) not in existing for item in prepared
        )
        return BatchStats(
            inserted=inserted,
            updated=len(prepared) - inserted,
            skipped=skipped,
            pending=pending,
        )

    def _prepare(
        self,
        row: Mapping[str, object],
        *,
        section: str,
    ) -> _PreparedSource:
        website = _required_text(row, "website")
        if website not in _DETAIL_HOST_SUFFIXES:
            raise SourceImportError
        external_post_id = _required_int(row, "tid")
        raw_number = _optional_text(row.get("number"))
        persisted_raw = (
            raw_number if raw_number is None or len(raw_number) <= 128 else None
        )
        normalized_number = normalize_movie_number(raw_number)
        preview_urls = _preview_urls(row.get("preview_images"), website)
        return _PreparedSource(
            website=website,
            external_post_id=external_post_id,
            raw_number=persisted_raw,
            normalized_number=normalized_number,
            title=_required_text(row, "title"),
            publish_date=_optional_date(row.get("publish_date")),
            section=section,
            category=_optional_text(row.get("category")),
            resource_size_mb=_optional_nonnegative_int(row.get("size")),
            detail_url=_safe_detail_url(row.get("detail_url"), website),
            preview_urls=preview_urls,
            magnet=_required_text(row, "magnet"),
            source_created_at=_optional_datetime(row.get("create_time")),
            source_updated_at=_optional_datetime(row.get("update_time")),
        )

    @staticmethod
    def _upsert_movies(
        session: Session,
        prepared: list[_PreparedSource],
        *,
        current: datetime,
    ) -> dict[str, Movie]:
        aliases: dict[str, set[str]] = {}
        for item in prepared:
            if item.normalized_number is not None and item.raw_number is not None:
                aliases.setdefault(item.normalized_number, set()).add(item.raw_number)
        if not aliases:
            return {}

        session.execute(
            insert(Movie)
            .values(
                [
                    {
                        "id": uuid.uuid4(),
                        "normalized_number": number,
                        "raw_numbers": sorted(raw_numbers),
                        "catalog_state": "raw_only",
                        "created_at": current,
                        "updated_at": current,
                    }
                    for number, raw_numbers in aliases.items()
                ]
            )
            .on_conflict_do_nothing(index_elements=[Movie.normalized_number])
        )
        movies = list(
            session.scalars(
                select(Movie)
                .where(Movie.normalized_number.in_(aliases))
                .with_for_update()
            )
        )
        for movie in movies:
            merged = sorted(set(movie.raw_numbers) | aliases[movie.normalized_number])
            if merged != movie.raw_numbers:
                movie.raw_numbers = merged
                movie.updated_at = current
        return {movie.normalized_number: movie for movie in movies}

    @staticmethod
    def _lock_existing_sources(
        session: Session,
        prepared: list[_PreparedSource],
    ) -> dict[tuple[str, int], str]:
        keys = {(item.website, item.external_post_id) for item in prepared}
        return {
            (website, external_post_id): identification_status
            for website, external_post_id, identification_status in session.execute(
                select(
                    ResourceSource.website,
                    ResourceSource.external_post_id,
                    ResourceSource.identification_status,
                )
                .where(
                    tuple_(
                        ResourceSource.website,
                        ResourceSource.external_post_id,
                    ).in_(keys)
                )
                .with_for_update()
            ).tuples()
        }

    def _upsert_sources(
        self,
        session: Session,
        prepared: list[_PreparedSource],
        *,
        movies: dict[str, Movie],
        current: datetime,
    ) -> None:
        values: list[dict[str, object]] = []
        for item in prepared:
            movie = (
                movies[item.normalized_number]
                if item.normalized_number is not None
                else None
            )
            envelope = self._cipher.encrypt(
                item.magnet.encode("utf-8"),
                context=source_magnet_context(item.website, item.external_post_id),
            )
            values.append(
                {
                    "id": uuid.uuid4(),
                    "website": item.website,
                    "external_post_id": item.external_post_id,
                    "movie_id": movie.id if movie is not None else None,
                    "raw_number": item.raw_number,
                    "normalized_number": item.normalized_number,
                    "title": item.title,
                    "publish_date": item.publish_date,
                    "section": item.section,
                    "category": item.category,
                    "resource_size_mb": item.resource_size_mb,
                    "detail_url": item.detail_url,
                    "preview_urls": item.preview_urls,
                    "magnet_key_id": envelope.key_id,
                    "magnet_nonce": envelope.nonce,
                    "magnet_ciphertext": envelope.ciphertext,
                    "identification_status": (
                        "identified" if movie is not None else "pending"
                    ),
                    "source_created_at": item.source_created_at,
                    "source_updated_at": item.source_updated_at,
                    "imported_at": current,
                }
            )
        statement = insert(ResourceSource).values(values)
        excluded = statement.excluded
        preserve_manual = ResourceSource.identification_status == "manual"
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[
                    ResourceSource.website,
                    ResourceSource.external_post_id,
                ],
                set_={
                    "movie_id": case(
                        (preserve_manual, ResourceSource.movie_id),
                        else_=excluded.movie_id,
                    ),
                    "raw_number": excluded.raw_number,
                    "normalized_number": case(
                        (preserve_manual, ResourceSource.normalized_number),
                        else_=excluded.normalized_number,
                    ),
                    "title": excluded.title,
                    "publish_date": excluded.publish_date,
                    "section": excluded.section,
                    "category": excluded.category,
                    "resource_size_mb": excluded.resource_size_mb,
                    "detail_url": excluded.detail_url,
                    "preview_urls": excluded.preview_urls,
                    "magnet_key_id": excluded.magnet_key_id,
                    "magnet_nonce": excluded.magnet_nonce,
                    "magnet_ciphertext": excluded.magnet_ciphertext,
                    "identification_status": case(
                        (preserve_manual, ResourceSource.identification_status),
                        else_=excluded.identification_status,
                    ),
                    "source_created_at": excluded.source_created_at,
                    "source_updated_at": excluded.source_updated_at,
                    "imported_at": excluded.imported_at,
                },
            )
        )

    def _utc_now(self) -> datetime:
        current = self._now()
        if current.tzinfo is None:
            raise SourceImportError
        return current.astimezone(timezone.utc)


def _required_text(row: Mapping[str, object], field: str) -> str:
    value = _optional_text(row.get(field))
    if value is None:
        raise SourceImportError
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SourceImportError
    stripped = value.strip()
    return stripped or None


def _required_int(row: Mapping[str, object], field: str) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SourceImportError
    return value


def _optional_nonnegative_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SourceImportError
    return value


def _optional_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime) or not isinstance(value, date):
        raise SourceImportError
    return value


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise SourceImportError
    return value


def _safe_detail_url(value: object, website: str) -> str | None:
    url = _optional_text(value)
    if url is None:
        return None
    return url if _is_allowed_source_url(url, website) else None


def _preview_urls(value: object, website: str) -> list[str]:
    text = _optional_text(value)
    if text is None:
        return []
    return [
        part
        for item in text.split(",")
        if (part := item.strip()) and _is_allowed_source_url(part, website)
    ]


def _is_allowed_source_url(url: str, website: str) -> bool:
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.username is None
        and parsed.password is None
        and port in {None, 443}
        and not parsed.fragment
        and any(
            hostname == suffix or hostname.endswith(f".{suffix}")
            for suffix in _DETAIL_HOST_SUFFIXES[website]
        )
    )
