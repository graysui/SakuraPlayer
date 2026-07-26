from __future__ import annotations

import base64
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from typing import Any
import uuid

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.actor_mapping import normalize_actor_alias
from sakuraplayer.catalog.models import (
    Actor,
    ActorAlias,
    CatalogImage,
    GfriendsActorAsset,
    MovieActor,
    MovieTag,
    Tag,
)
from sakuraplayer.catalog.ports import (
    EmptyFavoriteStatePort,
    EmptyPlaybackStatePort,
    EmptySourceAvailabilityPort,
    FavoriteStatePort,
    PlaybackProgress,
    PlaybackStatePort,
    SourceAvailability,
    SourceAvailabilityPort,
)
from sakuraplayer.resources.models import Movie, ResourceSource, ResourceSourceLabel
from sakuraplayer.resources.number_normalizer import normalize_movie_number


MAX_PAGE_SIZE = 100
_ACTIVE_SOURCE_STATES = ("identified", "manual")
_CATEGORIES = {
    "亚洲有码",
    "亚洲无码",
    "中文字幕",
    "4K原版",
    "素人有码",
    "FC2",
}
_LABELS = {"subtitle", "cracked", "4k", "censored"}
_SORTS = {"publish_date_desc", "publish_date_asc", "number_asc"}
_IMAGE_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


class CatalogProblem(RuntimeError):
    def __init__(self, *, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MovieFilters:
    categories: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    source_website: str | None = None
    playable: bool | None = None
    min_resource_size_mb: int | None = None
    max_resource_size_mb: int | None = None
    sort: str = "publish_date_desc"
    favorite: bool = False


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
class PlaybackProgressView:
    position_seconds: float
    duration_seconds: float | None
    completed: bool
    version: int


@dataclass(frozen=True)
class MovieSummaryView:
    id: uuid.UUID
    number: str
    title: str
    title_original: str | None
    cover_url: str | None
    publish_date: date | None
    labels: list[str]
    favorite: bool
    source_count: int
    progress: PlaybackProgressView | None


@dataclass(frozen=True)
class ActorSummaryView:
    id: uuid.UUID
    display_name: str
    name_ja: str | None
    name_zh: str | None
    aliases: list[str]
    profile_url: str | None
    favorite: bool


@dataclass(frozen=True)
class MovieDetailView(MovieSummaryView):
    release_date: date | None
    maker: str | None
    series: str | None
    director: str | None
    score: float | None
    description: str | None
    description_original: str | None
    actors: list[ActorSummaryView]
    tags: list[str]
    plot_image_urls: list[str]
    sources: list[MovieSourceView]


@dataclass(frozen=True)
class ActorDetailView(ActorSummaryView):
    bio: str | None
    bio_original: str | None
    gallery_urls: list[str]
    movies: list[MovieSummaryView]


@dataclass(frozen=True)
class MoviePage:
    items: list[MovieSummaryView]
    next_cursor: str | None


@dataclass(frozen=True)
class ActorPage:
    items: list[ActorSummaryView]
    next_cursor: str | None


@dataclass(frozen=True)
class RawMetadataCandidate:
    movie_id: uuid.UUID
    number: str
    sort_date: date | None


@dataclass(frozen=True)
class CatalogSearchResult:
    movies: list[MovieSummaryView]
    actors: list[ActorSummaryView]
    raw_candidate: RawMetadataCandidate | None


@dataclass(frozen=True)
class CatalogImageFile:
    path: Path
    media_type: str


class CatalogQueryService:
    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        availability_port: SourceAvailabilityPort | None = None,
        playback_port: PlaybackStatePort | None = None,
        favorite_port: FavoriteStatePort | None = None,
        image_root: Path = Path("/var/lib/sakuraplayer/catalog-images"),
    ) -> None:
        self._session_factory = session_factory
        self._availability = availability_port or EmptySourceAvailabilityPort()
        self._playback = playback_port or EmptyPlaybackStatePort()
        self._favorites = favorite_port or EmptyFavoriteStatePort()
        self._image_root = Path(image_root)

    def movie_summaries_by_ids(
        self,
        movie_ids: Iterable[uuid.UUID],
    ) -> list[MovieSummaryView]:
        requested = tuple(movie_ids)
        if (
            len(requested) > MAX_PAGE_SIZE
            or len(set(requested)) != len(requested)
            or any(not isinstance(movie_id, uuid.UUID) for movie_id in requested)
        ):
            raise CatalogProblem(status_code=422, code="validation_failed")
        if not requested:
            return []
        with self._session_factory() as session:
            movies_by_id = {
                movie.id: movie
                for movie in session.scalars(
                    select(Movie).where(
                        Movie.id.in_(requested),
                        Movie.catalog_state == "core_ready",
                        _has_active_source(Movie.id),
                    )
                )
            }
            visible = [movies_by_id[movie_id] for movie_id in requested if movie_id in movies_by_id]
            if not visible:
                return []
            visible_ids = tuple(movie.id for movie in visible)
            publish_dates = {
                movie_id: publish_date
                for movie_id, publish_date in session.execute(
                    select(
                        ResourceSource.movie_id,
                        func.max(ResourceSource.publish_date),
                    )
                    .where(
                        ResourceSource.movie_id.in_(visible_ids),
                        ResourceSource.identification_status.in_(_ACTIVE_SOURCE_STATES),
                    )
                    .group_by(ResourceSource.movie_id)
                )
            }
            return self._movie_summaries(
                session,
                visible,
                publish_dates=publish_dates,
                favorite_ids=self._favorites.target_ids("movie"),
            )

    def list_movies(
        self,
        *,
        filters: MovieFilters,
        cursor: str | None,
        limit: int,
    ) -> MoviePage:
        normalized = _normalize_movie_filters(filters)
        _validate_limit(limit)
        favorite_ids = self._favorites.target_ids("movie")
        if normalized.favorite and not favorite_ids:
            return MoviePage(items=[], next_cursor=None)
        if normalized.playable is True and isinstance(
            self._availability,
            EmptySourceAvailabilityPort,
        ):
            return MoviePage(items=[], next_cursor=None)

        source_conditions = _source_conditions(normalized)
        qualifying_sources = (
            select(
                ResourceSource.movie_id.label("movie_id"),
                func.max(ResourceSource.publish_date).label("publish_key"),
            )
            .where(*source_conditions)
            .group_by(ResourceSource.movie_id)
            .subquery()
        )
        publish_key = qualifying_sources.c.publish_key
        statement = select(Movie, publish_key.label("publish_key")).where(
            Movie.catalog_state == "core_ready"
        ).join(qualifying_sources, qualifying_sources.c.movie_id == Movie.id)
        if normalized.favorite:
            statement = statement.where(Movie.id.in_(favorite_ids))
        with self._session_factory() as session:
            rows = self._movie_rows(
                session,
                statement=statement,
                filters=normalized,
                cursor=cursor,
                limit=limit,
                publish_key=publish_key,
                source_conditions=source_conditions,
            )
            visible = rows[:limit]
            items = self._movie_summaries(
                session,
                [row[0] for row in visible],
                publish_dates={row[0].id: row[1] for row in visible},
                favorite_ids=favorite_ids,
            )

        next_cursor = None
        if len(rows) > limit and visible:
            last_movie, last_key = visible[-1]
            next_cursor = _encode_movie_cursor(
                normalized,
                _movie_cursor_key(normalized, last_movie, last_key),
                last_movie.id,
            )
        return MoviePage(items=items, next_cursor=next_cursor)

    def _movie_rows(
        self,
        session,
        *,
        statement: Select,
        filters: MovieFilters,
        cursor: str | None,
        limit: int,
        publish_key,
        source_conditions: list[Any],
    ) -> list[Any]:
        use_availability_filter = filters.playable is not None and not isinstance(
            self._availability,
            EmptySourceAvailabilityPort,
        )
        if not use_availability_filter:
            query = _apply_movie_cursor(
                statement,
                cursor=cursor,
                filters=filters,
                publish_key=publish_key,
            ).limit(limit + 1)
            return list(session.execute(query))

        matched: list[Any] = []
        scan_cursor = cursor
        while len(matched) <= limit:
            query = _apply_movie_cursor(
                statement,
                cursor=scan_cursor,
                filters=filters,
                publish_key=publish_key,
            ).limit(MAX_PAGE_SIZE)
            scanned = list(session.execute(query))
            if not scanned:
                break
            for row in scanned:
                if self._movie_matches_playable(
                    session,
                    row[0].id,
                    source_conditions,
                    bool(filters.playable),
                ):
                    matched.append(row)
                    if len(matched) > limit:
                        break
            if len(matched) > limit or len(scanned) < MAX_PAGE_SIZE:
                break
            last_movie, last_key = scanned[-1]
            scan_cursor = _encode_movie_cursor(
                filters,
                _movie_cursor_key(filters, last_movie, last_key),
                last_movie.id,
            )
        return matched

    def get_movie(self, movie_id: uuid.UUID) -> MovieDetailView:
        with self._session_factory() as session:
            movie = session.scalar(
                select(Movie).where(
                    Movie.id == movie_id,
                    Movie.catalog_state == "core_ready",
                    _has_active_source(Movie.id),
                )
            )
            if movie is None:
                raise CatalogProblem(status_code=404, code="resource_not_found")
            sources = list(
                session.scalars(
                    select(ResourceSource)
                    .where(
                        ResourceSource.movie_id == movie.id,
                        ResourceSource.identification_status.in_(_ACTIVE_SOURCE_STATES),
                    )
                    .order_by(
                        ResourceSource.publish_date.desc().nulls_last(),
                        ResourceSource.id.desc(),
                    )
                    .limit(MAX_PAGE_SIZE)
                )
            )
            source_count = int(
                session.scalar(
                    select(func.count(ResourceSource.id)).where(
                        ResourceSource.movie_id == movie.id,
                        ResourceSource.identification_status.in_(_ACTIVE_SOURCE_STATES),
                    )
                )
                or 0
            )
            source_views = self._source_views(session, sources)
            favorite_ids = self._favorites.target_ids("movie")
            summary = self._movie_summaries(
                session,
                [movie],
                publish_dates={
                    movie.id: max(
                        (
                            source.publish_date
                            for source in sources
                            if source.publish_date
                        ),
                        default=None,
                    )
                },
                favorite_ids=favorite_ids,
                source_counts={movie.id: source_count},
            )[0]
            actors = self._movie_actor_summaries(session, movie.id)
            tags = list(
                session.scalars(
                    select(Tag.name)
                    .join(MovieTag, MovieTag.tag_id == Tag.id)
                    .where(MovieTag.movie_id == movie.id)
                    .order_by(Tag.name)
                    .limit(MAX_PAGE_SIZE)
                )
            )
            plot_urls = [
                _catalog_image_url(image.id)
                for image in session.scalars(
                    select(CatalogImage)
                    .where(
                        CatalogImage.owner_type == "movie",
                        CatalogImage.owner_id == movie.id,
                        CatalogImage.kind == "plot",
                    )
                    .order_by(CatalogImage.position, CatalogImage.id)
                    .limit(MAX_PAGE_SIZE)
                )
            ]
            return MovieDetailView(
                **summary.__dict__,
                release_date=movie.release_date,
                maker=movie.maker,
                series=movie.series,
                director=movie.director,
                score=float(movie.score) if movie.score is not None else None,
                description=movie.description_zh or movie.description_original,
                description_original=movie.description_original,
                actors=actors,
                tags=tags,
                plot_image_urls=plot_urls,
                sources=source_views,
            )

    def list_actors(
        self,
        *,
        q: str | None,
        cursor: str | None,
        limit: int,
        favorite: bool,
    ) -> ActorPage:
        _validate_limit(limit)
        normalized_query = normalize_actor_alias(q or "") if q else None
        favorite_ids = self._favorites.target_ids("actor")
        if favorite and not favorite_ids:
            return ActorPage(items=[], next_cursor=None)
        display_key = func.lower(
            func.coalesce(Actor.name_zh, Actor.name_ja, Actor.javdb_id)
        )
        statement = select(Actor, display_key.label("display_key")).where(
            _actor_has_visible_movie(Actor.id)
        )
        if normalized_query:
            pattern = _literal_like(normalized_query)
            statement = statement.where(
                or_(
                    Actor.name_ja.ilike(pattern, escape="\\"),
                    Actor.name_zh.ilike(pattern, escape="\\"),
                    exists(
                        select(ActorAlias.actor_id).where(
                            ActorAlias.actor_id == Actor.id,
                            ActorAlias.normalized_alias.ilike(pattern, escape="\\"),
                        )
                    ),
                )
            )
        if favorite:
            statement = statement.where(Actor.id.in_(favorite_ids))
        signature = {"favorite": favorite, "q": normalized_query, "v": 1}
        cursor_values = _decode_cursor(cursor, expected=signature, keys={"key", "id"})
        if cursor_values is not None:
            key = cursor_values["key"]
            if not isinstance(key, str):
                raise CatalogProblem(status_code=422, code="validation_failed")
            actor_id = uuid.UUID(cursor_values["id"])
            statement = statement.where(
                or_(display_key > key, (display_key == key) & (Actor.id > actor_id))
            )
        statement = statement.order_by(display_key, Actor.id).limit(limit + 1)
        with self._session_factory() as session:
            rows = list(session.execute(statement))
            visible = rows[:limit]
            items = self._actor_summaries(
                session,
                [row[0] for row in visible],
                favorite_ids=favorite_ids,
            )
        next_cursor = None
        if len(rows) > limit and visible:
            actor, key = visible[-1]
            next_cursor = _encode_cursor({**signature, "key": key, "id": str(actor.id)})
        return ActorPage(items=items, next_cursor=next_cursor)

    def get_actor(self, actor_id: uuid.UUID) -> ActorDetailView:
        with self._session_factory() as session:
            actor = session.scalar(
                select(Actor).where(
                    Actor.id == actor_id,
                    _actor_has_visible_movie(Actor.id),
                )
            )
            if actor is None:
                raise CatalogProblem(status_code=404, code="resource_not_found")
            summary = self._actor_summaries(
                session,
                [actor],
                favorite_ids=self._favorites.target_ids("actor"),
            )[0]
            gallery_urls = list(
                session.scalars(
                    select(GfriendsActorAsset.url)
                    .where(
                        GfriendsActorAsset.actor_id == actor.id,
                        GfriendsActorAsset.asset_kind == "gallery",
                    )
                    .order_by(GfriendsActorAsset.position, GfriendsActorAsset.id)
                    .limit(MAX_PAGE_SIZE)
                )
            )
            movie_rows = list(
                session.execute(
                    select(Movie)
                    .join(MovieActor, MovieActor.movie_id == Movie.id)
                    .where(
                        MovieActor.actor_id == actor.id,
                        Movie.catalog_state == "core_ready",
                        _has_active_source(Movie.id),
                    )
                    .order_by(Movie.release_date.desc().nulls_last(), Movie.id.desc())
                    .limit(MAX_PAGE_SIZE)
                )
            )
            movies = [row[0] for row in movie_rows]
            movie_summaries = self._movie_summaries(
                session,
                movies,
                publish_dates=self._latest_publish_dates(
                    session,
                    [movie.id for movie in movies],
                ),
                favorite_ids=self._favorites.target_ids("movie"),
            )
            return ActorDetailView(
                **summary.__dict__,
                bio=actor.bio_zh or actor.bio_original,
                bio_original=actor.bio_original,
                gallery_urls=gallery_urls,
                movies=movie_summaries,
            )

    def search_catalog(self, q: str, *, limit: int) -> CatalogSearchResult:
        query = q.strip()
        if not query or len(query) > 200:
            raise CatalogProblem(status_code=422, code="validation_failed")
        _validate_limit(limit)
        normalized_number = normalize_movie_number(query)
        with self._session_factory() as session:
            exact: Movie | None = None
            raw_candidate = None
            if normalized_number is not None:
                exact = session.scalar(
                    select(Movie).where(Movie.normalized_number == normalized_number)
                )
                if exact is not None and exact.catalog_state != "core_ready":
                    sort_date = session.scalar(
                        select(func.max(ResourceSource.publish_date)).where(
                            ResourceSource.movie_id == exact.id,
                            ResourceSource.identification_status.in_(
                                _ACTIVE_SOURCE_STATES
                            ),
                        )
                    )
                    if session.scalar(
                        select(exists().where(
                            ResourceSource.movie_id == exact.id,
                            ResourceSource.identification_status.in_(
                                _ACTIVE_SOURCE_STATES
                            ),
                        ))
                    ):
                        raw_candidate = RawMetadataCandidate(
                            movie_id=exact.id,
                            number=exact.normalized_number,
                            sort_date=sort_date,
                        )
                    exact = None
                elif exact is not None and not session.scalar(
                    select(_has_active_source(exact.id))
                ):
                    exact = None
            literal = query.casefold()
            pattern = _literal_like(literal)
            statement = select(Movie).where(
                Movie.catalog_state == "core_ready",
                _has_active_source(Movie.id),
                or_(
                    Movie.title_original.ilike(pattern, escape="\\"),
                    Movie.title_zh.ilike(pattern, escape="\\"),
                ),
            )
            if exact is not None:
                statement = statement.where(Movie.id != exact.id)
            fuzzy = list(session.scalars(statement.order_by(Movie.id).limit(limit)))
            movies = ([exact] if exact is not None else []) + fuzzy
            movies = movies[:limit]
            movie_views = self._movie_summaries(
                session,
                movies,
                publish_dates=self._latest_publish_dates(
                    session,
                    [movie.id for movie in movies],
                ),
                favorite_ids=self._favorites.target_ids("movie"),
            )
            actor_page = self.list_actors(
                q=query,
                cursor=None,
                limit=limit,
                favorite=False,
            )
        return CatalogSearchResult(
            movies=movie_views,
            actors=actor_page.items,
            raw_candidate=raw_candidate,
        )

    def resolve_image(self, image_id: uuid.UUID) -> CatalogImageFile:
        with self._session_factory() as session:
            image = session.get(CatalogImage, image_id)
            if image is None:
                raise CatalogProblem(status_code=404, code="resource_not_found")
            relative = Path(image.relative_path)
        root = self._image_root.resolve()
        try:
            path = (root / relative).resolve(strict=True)
        except (OSError, RuntimeError):
            raise CatalogProblem(status_code=404, code="resource_not_found") from None
        media_type = _IMAGE_MEDIA_TYPES.get(path.suffix.lower())
        if root not in path.parents or not path.is_file() or media_type is None:
            raise CatalogProblem(status_code=404, code="resource_not_found")
        return CatalogImageFile(path=path, media_type=media_type)

    def _movie_matches_playable(
        self,
        session,
        movie_id: uuid.UUID,
        source_conditions: list[Any],
        playable: bool,
    ) -> bool:
        source_ids = tuple(
            session.scalars(
                select(ResourceSource.id).where(
                    ResourceSource.movie_id == movie_id,
                    *source_conditions,
                )
            )
        )
        states = self._availability.get_many(source_ids)
        return any(
            (states.get(source_id, SourceAvailability()).state == "ready") == playable
            for source_id in source_ids
        )

    def _movie_summaries(
        self,
        session,
        movies: list[Movie],
        *,
        publish_dates: dict[uuid.UUID, date | None],
        favorite_ids: set[uuid.UUID],
        source_counts: dict[uuid.UUID, int] | None = None,
    ) -> list[MovieSummaryView]:
        if not movies:
            return []
        movie_ids = [movie.id for movie in movies]
        sources = list(
            session.scalars(
                select(ResourceSource).where(
                    ResourceSource.movie_id.in_(movie_ids),
                    ResourceSource.identification_status.in_(_ACTIVE_SOURCE_STATES),
                )
            )
        )
        sources_by_movie: dict[uuid.UUID, list[ResourceSource]] = {
            movie_id: [] for movie_id in movie_ids
        }
        for source in sources:
            if source.movie_id is not None:
                sources_by_movie[source.movie_id].append(source)
        labels_by_source = _labels_by_source(session, sources)
        covers: dict[uuid.UUID, CatalogImage] = {}
        for image in session.scalars(
            select(CatalogImage)
            .where(
                CatalogImage.owner_type == "movie",
                CatalogImage.owner_id.in_(movie_ids),
                CatalogImage.kind.in_(("cover", "placeholder")),
            )
            .order_by(CatalogImage.owner_id, CatalogImage.kind, CatalogImage.position)
        ):
            covers.setdefault(image.owner_id, image)
        progress = self._playback.get_many(tuple(movie_ids))
        counts = source_counts or {
            movie_id: len(sources_by_movie[movie_id]) for movie_id in movie_ids
        }
        return [
            MovieSummaryView(
                id=movie.id,
                number=movie.normalized_number,
                title=movie.title_zh or movie.title_original or movie.normalized_number,
                title_original=movie.title_original,
                cover_url=(
                    _catalog_image_url(covers[movie.id].id)
                    if movie.id in covers
                    else None
                ),
                publish_date=publish_dates.get(movie.id),
                labels=sorted(
                    {
                        label
                        for source in sources_by_movie[movie.id]
                        for label in labels_by_source.get(source.id, [])
                    }
                ),
                favorite=movie.id in favorite_ids,
                source_count=counts.get(movie.id, 0),
                progress=_progress_view(progress.get(movie.id)),
            )
            for movie in movies
        ]

    def _source_views(
        self,
        session,
        sources: list[ResourceSource],
    ) -> list[MovieSourceView]:
        labels = _labels_by_source(session, sources)
        states = self._availability.get_many(tuple(source.id for source in sources))
        return [
            MovieSourceView(
                id=source.id,
                website=source.website,
                external_post_id=source.external_post_id,
                title=source.title,
                publish_date=source.publish_date,
                category=source.section,
                labels=labels.get(source.id, []),
                resource_size_mb=source.resource_size_mb,
                video_file_size_bytes=states.get(
                    source.id,
                    SourceAvailability(),
                ).video_file_size_bytes,
                availability=states.get(source.id, SourceAvailability()).state,
            )
            for source in sources
        ]

    def _movie_actor_summaries(
        self,
        session,
        movie_id: uuid.UUID,
    ) -> list[ActorSummaryView]:
        actors = list(
            session.scalars(
                select(Actor)
                .join(MovieActor, MovieActor.actor_id == Actor.id)
                .where(MovieActor.movie_id == movie_id)
                .order_by(MovieActor.position, Actor.id)
                .limit(MAX_PAGE_SIZE)
            )
        )
        return self._actor_summaries(
            session,
            actors,
            favorite_ids=self._favorites.target_ids("actor"),
        )

    @staticmethod
    def _actor_summaries(
        session,
        actors: list[Actor],
        *,
        favorite_ids: set[uuid.UUID],
    ) -> list[ActorSummaryView]:
        if not actors:
            return []
        actor_ids = [actor.id for actor in actors]
        aliases: dict[uuid.UUID, list[str]] = {actor_id: [] for actor_id in actor_ids}
        ranked_aliases = (
            select(
                ActorAlias.actor_id.label("actor_id"),
                ActorAlias.alias.label("alias"),
                func.row_number()
                .over(
                    partition_by=ActorAlias.actor_id,
                    order_by=(ActorAlias.normalized_alias, ActorAlias.alias),
                )
                .label("position"),
            )
            .where(ActorAlias.actor_id.in_(actor_ids))
            .subquery()
        )
        for actor_id, alias in session.execute(
            select(ranked_aliases.c.actor_id, ranked_aliases.c.alias)
            .where(ranked_aliases.c.position <= MAX_PAGE_SIZE)
            .order_by(ranked_aliases.c.actor_id, ranked_aliases.c.position)
        ):
            aliases[actor_id].append(alias)
        profiles = {
            asset.actor_id: asset.url
            for asset in session.scalars(
                select(GfriendsActorAsset)
                .where(
                    GfriendsActorAsset.actor_id.in_(actor_ids),
                    GfriendsActorAsset.asset_kind == "profile",
                )
                .order_by(GfriendsActorAsset.actor_id, GfriendsActorAsset.position)
            )
        }
        return [
            ActorSummaryView(
                id=actor.id,
                display_name=actor.name_zh or actor.name_ja or actor.javdb_id,
                name_ja=actor.name_ja,
                name_zh=actor.name_zh,
                aliases=aliases[actor.id],
                profile_url=profiles.get(actor.id),
                favorite=actor.id in favorite_ids,
            )
            for actor in actors
        ]

    @staticmethod
    def _latest_publish_dates(
        session,
        movie_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, date | None]:
        if not movie_ids:
            return {}
        return {
            movie_id: publish_date
            for movie_id, publish_date in session.execute(
                select(ResourceSource.movie_id, func.max(ResourceSource.publish_date))
                .where(
                    ResourceSource.movie_id.in_(movie_ids),
                    ResourceSource.identification_status.in_(_ACTIVE_SOURCE_STATES),
                )
                .group_by(ResourceSource.movie_id)
            )
            if movie_id is not None
        }


def _normalize_movie_filters(filters: MovieFilters) -> MovieFilters:
    categories = tuple(sorted(set(filters.categories)))
    labels = tuple(sorted(set(filters.labels)))
    if not set(categories) <= _CATEGORIES or not set(labels) <= _LABELS:
        raise CatalogProblem(status_code=422, code="validation_failed")
    if filters.source_website not in {None, "sehuatang", "x1080x"}:
        raise CatalogProblem(status_code=422, code="validation_failed")
    if filters.sort not in _SORTS:
        raise CatalogProblem(status_code=422, code="validation_failed")
    for value in (filters.min_resource_size_mb, filters.max_resource_size_mb):
        if value is not None and value < 0:
            raise CatalogProblem(status_code=422, code="validation_failed")
    if (
        filters.min_resource_size_mb is not None
        and filters.max_resource_size_mb is not None
        and filters.min_resource_size_mb > filters.max_resource_size_mb
    ):
        raise CatalogProblem(status_code=422, code="validation_failed")
    return MovieFilters(
        categories=categories,
        labels=labels,
        source_website=filters.source_website,
        playable=filters.playable,
        min_resource_size_mb=filters.min_resource_size_mb,
        max_resource_size_mb=filters.max_resource_size_mb,
        sort=filters.sort,
        favorite=filters.favorite,
    )


def _source_conditions(filters: MovieFilters) -> list[Any]:
    conditions: list[Any] = [
        ResourceSource.identification_status.in_(_ACTIVE_SOURCE_STATES)
    ]
    if filters.categories:
        conditions.append(ResourceSource.section.in_(filters.categories))
    if filters.source_website is not None:
        conditions.append(ResourceSource.website == filters.source_website)
    if filters.min_resource_size_mb is not None:
        conditions.append(
            ResourceSource.resource_size_mb >= filters.min_resource_size_mb
        )
    if filters.max_resource_size_mb is not None:
        conditions.append(
            ResourceSource.resource_size_mb <= filters.max_resource_size_mb
        )
    for label in filters.labels:
        conditions.append(
            exists(
                select(ResourceSourceLabel.source_id).where(
                    ResourceSourceLabel.source_id == ResourceSource.id,
                    ResourceSourceLabel.label == label,
                )
            )
        )
    return conditions


def _apply_movie_cursor(
    statement: Select,
    *,
    cursor: str | None,
    filters: MovieFilters,
    publish_key,
) -> Select:
    signature = _movie_signature(filters)
    cursor_values = _decode_cursor(cursor, expected=signature, keys={"id", "key"})
    if filters.sort == "number_asc":
        if cursor_values is not None:
            key = cursor_values["key"]
            if not isinstance(key, str):
                raise CatalogProblem(status_code=422, code="validation_failed")
            movie_id = uuid.UUID(cursor_values["id"])
            statement = statement.where(
                or_(
                    Movie.normalized_number > key,
                    (Movie.normalized_number == key) & (Movie.id > movie_id),
                )
            )
        return statement.order_by(Movie.normalized_number, Movie.id)

    descending = filters.sort == "publish_date_desc"
    if cursor_values is not None:
        try:
            key = (
                date.fromisoformat(cursor_values["key"])
                if cursor_values["key"]
                else None
            )
        except ValueError:
            raise CatalogProblem(status_code=422, code="validation_failed") from None
        movie_id = uuid.UUID(cursor_values["id"])
        if key is None:
            id_condition = Movie.id < movie_id if descending else Movie.id > movie_id
            statement = statement.where(publish_key.is_(None), id_condition)
        elif descending:
            statement = statement.where(
                or_(
                    publish_key < key,
                    publish_key.is_(None),
                    (publish_key == key) & (Movie.id < movie_id),
                )
            )
        else:
            statement = statement.where(
                or_(
                    publish_key > key,
                    publish_key.is_(None),
                    (publish_key == key) & (Movie.id > movie_id),
                )
            )
    if descending:
        return statement.order_by(
            publish_key.is_(None),
            publish_key.desc(),
            Movie.id.desc(),
        )
    return statement.order_by(
        publish_key.is_(None),
        publish_key.asc(),
        Movie.id.asc(),
    )


def _encode_movie_cursor(
    filters: MovieFilters,
    key: date | str | None,
    movie_id: uuid.UUID,
) -> str:
    value = key.isoformat() if isinstance(key, date) else key
    return _encode_cursor(
        {**_movie_signature(filters), "id": str(movie_id), "key": value}
    )


def _movie_cursor_key(
    filters: MovieFilters,
    movie: Movie,
    publish_key: date | None,
) -> date | str | None:
    if filters.sort == "number_asc":
        return movie.normalized_number
    return publish_key


def _movie_signature(filters: MovieFilters) -> dict[str, object]:
    return {
        "categories": list(filters.categories),
        "favorite": filters.favorite,
        "labels": list(filters.labels),
        "max_size": filters.max_resource_size_mb,
        "min_size": filters.min_resource_size_mb,
        "playable": filters.playable,
        "sort": filters.sort,
        "v": 1,
        "website": filters.source_website,
    }


def _encode_cursor(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_cursor(
    cursor: str | None,
    *,
    expected: dict[str, object],
    keys: set[str],
) -> dict[str, Any] | None:
    if cursor is None:
        return None
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.b64decode(cursor + padding, altchars=b"-_", validate=True)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or set(payload) != set(expected) | keys:
            raise ValueError
        if any(
            payload.get(key) != value or type(payload.get(key)) is not type(value)
            for key, value in expected.items()
        ):
            raise ValueError
        if not isinstance(payload["id"], str) or not isinstance(
            payload["key"],
            (str, type(None)),
        ):
            raise ValueError
        uuid.UUID(payload["id"])
        return payload
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        raise CatalogProblem(status_code=422, code="validation_failed") from None


def _has_active_source(movie_id):
    return exists(
        select(ResourceSource.id).where(
            ResourceSource.movie_id == movie_id,
            ResourceSource.identification_status.in_(_ACTIVE_SOURCE_STATES),
        )
    )


def _actor_has_visible_movie(actor_id):
    return exists(
        select(MovieActor.actor_id)
        .join(Movie, Movie.id == MovieActor.movie_id)
        .join(ResourceSource, ResourceSource.movie_id == Movie.id)
        .where(
            MovieActor.actor_id == actor_id,
            Movie.catalog_state == "core_ready",
            ResourceSource.identification_status.in_(_ACTIVE_SOURCE_STATES),
        )
    )


def _labels_by_source(
    session,
    sources: list[ResourceSource],
) -> dict[uuid.UUID, list[str]]:
    labels = {source.id: [] for source in sources}
    if not sources:
        return labels
    for item in session.scalars(
        select(ResourceSourceLabel)
        .where(ResourceSourceLabel.source_id.in_(labels))
        .order_by(ResourceSourceLabel.label)
    ):
        labels[item.source_id].append(item.label)
    return labels


def _progress_view(progress: PlaybackProgress | None) -> PlaybackProgressView | None:
    if progress is None:
        return None
    return PlaybackProgressView(**progress.__dict__)


def _catalog_image_url(image_id: uuid.UUID) -> str:
    return f"/api/v1/catalog/images/{image_id}"


def _literal_like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _validate_limit(limit: int) -> None:
    if limit < 1 or limit > MAX_PAGE_SIZE:
        raise CatalogProblem(status_code=422, code="validation_failed")


__all__ = [
    "ActorDetailView",
    "ActorPage",
    "ActorSummaryView",
    "CatalogImageFile",
    "CatalogProblem",
    "CatalogQueryService",
    "CatalogSearchResult",
    "MovieDetailView",
    "MovieFilters",
    "MoviePage",
    "MovieSourceView",
    "MovieSummaryView",
    "PlaybackProgressView",
    "RawMetadataCandidate",
]
