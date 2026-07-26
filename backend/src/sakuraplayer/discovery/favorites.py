from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import uuid

from sqlalchemy import delete, exists, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.models import Actor, MovieActor
from sakuraplayer.catalog.ports import FavoriteStatePort
from sakuraplayer.discovery.models import Favorite
from sakuraplayer.resources.models import Movie, ResourceSource


_ACTIVE_SOURCE_STATES = ("identified", "manual")


class FavoriteProblem(RuntimeError):
    def __init__(self, *, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(code)


class FavoriteService(FavoriteStatePort):
    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._now = now or (lambda: datetime.now(timezone.utc))

    def target_ids(self, target_type: str) -> set[uuid.UUID]:
        _validate_target_type(target_type)
        with self._session_factory() as session:
            return set(
                session.scalars(
                    select(Favorite.target_id).where(
                        Favorite.target_type == target_type
                    )
                )
            )

    def set_favorite(
        self,
        target_type: str,
        target_id: uuid.UUID,
        *,
        enabled: bool,
    ) -> None:
        _validate_target_type(target_type)
        current = self._now()
        if current.tzinfo is None:
            raise ValueError("favorite clock must be timezone-aware")
        current = current.astimezone(timezone.utc)
        with self._session_factory.begin() as session:
            if not _target_is_visible(session, target_type, target_id):
                raise FavoriteProblem(status_code=404, code="resource_not_found")
            if enabled:
                values = {
                    "id": uuid.uuid4(),
                    "target_type": target_type,
                    "target_id": target_id,
                    "created_at": current,
                }
                if session.get_bind().dialect.name == "postgresql":
                    session.execute(
                        postgresql_insert(Favorite)
                        .values(**values)
                        .on_conflict_do_nothing(
                            index_elements=["target_type", "target_id"]
                        )
                    )
                elif session.scalar(
                    select(Favorite.id).where(
                        Favorite.target_type == target_type,
                        Favorite.target_id == target_id,
                    )
                ) is None:
                    session.add(Favorite(**values))
            else:
                session.execute(
                    delete(Favorite).where(
                        Favorite.target_type == target_type,
                        Favorite.target_id == target_id,
                    )
                )


def _target_is_visible(session, target_type: str, target_id: uuid.UUID) -> bool:
    source_exists = exists(
        select(ResourceSource.id).where(
            ResourceSource.movie_id == Movie.id,
            ResourceSource.identification_status.in_(_ACTIVE_SOURCE_STATES),
        )
    )
    if target_type == "movie":
        return session.scalar(
            select(exists().where(
                Movie.id == target_id,
                Movie.catalog_state == "core_ready",
                source_exists,
            ))
        )
    return session.scalar(
        select(exists().where(
            Actor.id == target_id,
            exists(
                select(MovieActor.actor_id)
                .join(Movie, Movie.id == MovieActor.movie_id)
                .join(ResourceSource, ResourceSource.movie_id == Movie.id)
                .where(
                    MovieActor.actor_id == Actor.id,
                    Movie.catalog_state == "core_ready",
                    ResourceSource.identification_status.in_(_ACTIVE_SOURCE_STATES),
                )
            ),
        ))
    )


def _validate_target_type(target_type: str) -> None:
    if target_type not in {"movie", "actor"}:
        raise ValueError("invalid favorite target type")


__all__ = ["FavoriteProblem", "FavoriteService"]
