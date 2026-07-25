from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.resources.models import Movie, ResourceSource, ResourceSourceLabel
from sakuraplayer.resources.number_normalizer import normalize_movie_number


class MovieSourceProblem(RuntimeError):
    def __init__(self, *, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MovieSourceView:
    id: uuid.UUID
    website: str
    external_post_id: int
    title: str
    publish_date: date | None
    category: str
    labels: list[str]
    resource_size_mb: int | None
    video_file_size_bytes: int | None
    availability: str


@dataclass(frozen=True)
class MovieDetailView:
    id: uuid.UUID
    number: str
    title: str
    title_original: str | None
    cover_url: str | None
    publish_date: date | None
    labels: list[str]
    favorite: bool
    source_count: int
    progress: None
    actors: list[object]
    tags: list[str]
    plot_image_urls: list[str]
    sources: list[MovieSourceView]


class MovieSourceService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._now = now or (lambda: datetime.now(timezone.utc))

    def merge(
        self,
        *,
        target_movie_id: uuid.UUID,
        source_movie_ids: list[uuid.UUID],
    ) -> MovieDetailView:
        source_ids = set(source_movie_ids)
        if not source_ids or len(source_ids) != len(source_movie_ids):
            raise MovieSourceProblem(status_code=422, code="validation_failed")
        if target_movie_id in source_ids:
            raise MovieSourceProblem(status_code=409, code="movie_merge_conflict")
        with self._session_factory.begin() as session:
            movies = list(
                session.scalars(
                    select(Movie)
                    .where(Movie.id.in_(source_ids | {target_movie_id}))
                    .order_by(Movie.id)
                    .with_for_update()
                )
            )
            if len(movies) != len(source_ids) + 1:
                raise MovieSourceProblem(status_code=404, code="resource_not_found")
            by_id = {movie.id: movie for movie in movies}
            target = by_id[target_movie_id]
            source_movies = [by_id[movie_id] for movie_id in source_ids]
            aliases = set(target.raw_numbers)
            for movie in source_movies:
                aliases.update(movie.raw_numbers)
            target.raw_numbers = sorted(aliases)
            target.updated_at = _utc(self._now())
            session.execute(
                update(ResourceSource)
                .where(ResourceSource.movie_id.in_(source_ids))
                .values(
                    movie_id=target.id,
                    normalized_number=target.normalized_number,
                )
            )
            for movie in source_movies:
                session.delete(movie)
            session.flush()
            return _movie_detail(session, target)

    def split(
        self,
        *,
        movie_id: uuid.UUID,
        source_id: uuid.UUID,
        new_normalized_number: str,
    ) -> MovieDetailView:
        normalized_number = normalize_movie_number(new_normalized_number)
        if normalized_number is None:
            raise MovieSourceProblem(status_code=422, code="validation_failed")
        with self._session_factory.begin() as session:
            source = session.scalar(
                select(ResourceSource)
                .where(
                    ResourceSource.id == source_id,
                    ResourceSource.movie_id == movie_id,
                )
                .with_for_update()
            )
            if source is None:
                raise MovieSourceProblem(status_code=404, code="resource_not_found")
            existing = session.scalar(
                select(Movie)
                .where(Movie.normalized_number == normalized_number)
                .with_for_update()
            )
            if existing is not None:
                raise MovieSourceProblem(status_code=409, code="movie_merge_conflict")
            current = _utc(self._now())
            movie = Movie(
                id=uuid.uuid4(),
                normalized_number=normalized_number,
                raw_numbers=sorted(
                    {value for value in (source.raw_number, normalized_number) if value}
                ),
                catalog_state="raw_only",
                created_at=current,
                updated_at=current,
            )
            session.add(movie)
            session.flush()
            source.movie_id = movie.id
            source.normalized_number = movie.normalized_number
            session.flush()
            return _movie_detail(session, movie)


def _movie_detail(session: Session, movie: Movie) -> MovieDetailView:
    sources = list(
        session.scalars(
            select(ResourceSource)
            .where(ResourceSource.movie_id == movie.id)
            .order_by(ResourceSource.publish_date.desc(), ResourceSource.id.desc())
        )
    )
    labels_by_source: dict[uuid.UUID, list[str]] = {source.id: [] for source in sources}
    if sources:
        for label in session.scalars(
            select(ResourceSourceLabel).where(
                ResourceSourceLabel.source_id.in_([source.id for source in sources])
            )
        ):
            labels_by_source[label.source_id].append(label.label)
    source_views = [
        MovieSourceView(
            id=source.id,
            website=source.website,
            external_post_id=source.external_post_id,
            title=source.title,
            publish_date=source.publish_date,
            category=source.section,
            labels=sorted(labels_by_source[source.id]),
            resource_size_mb=source.resource_size_mb,
            video_file_size_bytes=None,
            availability=(
                "rejected"
                if source.identification_status == "rejected"
                else "available"
            ),
        )
        for source in sources
    ]
    return MovieDetailView(
        id=movie.id,
        number=movie.normalized_number,
        title=movie.normalized_number,
        title_original=None,
        cover_url=None,
        publish_date=None,
        labels=sorted({label for source in source_views for label in source.labels}),
        favorite=False,
        source_count=len(source_views),
        progress=None,
        actors=[],
        tags=[],
        plot_image_urls=[],
        sources=source_views,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("now must return a timezone-aware datetime")
    return value.astimezone(timezone.utc)
