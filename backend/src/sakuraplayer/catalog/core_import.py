from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.catalog.models import (
    Actor,
    ActorAlias,
    CatalogImage,
    MovieActor,
    MovieTag,
    Tag,
    MetadataJob,
    MetadataStage,
)
from sakuraplayer.catalog.providers.javdb import CoreMovieMetadata
from sakuraplayer.resources.models import Movie


class CoreImportProblem(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MetadataWriteFence:
    job_id: uuid.UUID
    claim_owner: str
    movie_id: uuid.UUID
    normalized_number: str
    stage: str


class CoreMetadataImporter:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        placeholder_relative_path: str,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not placeholder_relative_path or placeholder_relative_path.startswith(("/", "\\")):
            raise ValueError("placeholder path must be relative")
        self._session_factory = session_factory
        self._placeholder_relative_path = placeholder_relative_path
        self._now = now or (lambda: datetime.now(timezone.utc))

    def import_core(
        self,
        *,
        movie_id: uuid.UUID,
        metadata: CoreMovieMetadata,
        fence: MetadataWriteFence,
    ) -> None:
        if (
            fence.movie_id != movie_id
            or fence.normalized_number != metadata.normalized_number
            or fence.stage != "javdb_core"
        ):
            raise CoreImportProblem("metadata_claim_lost")
        try:
            with self._session_factory.begin() as session:
                require_active_metadata_claim(
                    session,
                    fence,
                    current=self._now(),
                )
                movie = session.scalar(
                    select(Movie).where(Movie.id == movie_id).with_for_update()
                )
                if movie is None:
                    raise CoreImportProblem("metadata_movie_not_found")
                if movie.normalized_number != metadata.normalized_number:
                    raise CoreImportProblem("metadata_core_number_mismatch")
                self._write_movie(movie, metadata)
                actor_ids = self._upsert_actors(session, metadata)
                tag_ids = self._upsert_tags(session, metadata)
                self._replace_relations(session, movie.id, actor_ids, tag_ids)
                self._reconcile_image_plans(session, movie.id, metadata)
                movie.catalog_state = "core_ready"
        except IntegrityError:
            raise CoreImportProblem("metadata_core_identity_conflict") from None

    def _write_movie(self, movie: Movie, metadata: CoreMovieMetadata) -> None:
        current = self._now()
        movie.javdb_id = metadata.javdb_id
        movie.title_original = metadata.title_original
        movie.release_date = metadata.release_date
        movie.maker = metadata.maker
        movie.series = metadata.series
        movie.director = metadata.director
        movie.score = metadata.score
        movie.metadata_updated_at = current
        movie.updated_at = current

    def _upsert_actors(
        self,
        session: Session,
        metadata: CoreMovieMetadata,
    ) -> list[uuid.UUID]:
        actor_ids_by_javdb: dict[str, uuid.UUID] = {}
        current = self._now()
        is_postgresql = session.get_bind().dialect.name == "postgresql"
        for item in sorted(metadata.actors, key=lambda actor: actor.javdb_id):
            if is_postgresql:
                session.execute(
                    postgresql_insert(Actor)
                    .values(
                        id=uuid.uuid4(),
                        javdb_id=item.javdb_id,
                        name_ja=item.name,
                        name_zh=None,
                        bio_original=None,
                        bio_zh=None,
                        gender="unknown",
                        created_at=current,
                        updated_at=current,
                    )
                    .on_conflict_do_nothing(index_elements=["javdb_id"])
                )
                actor = session.scalar(
                    select(Actor)
                    .where(Actor.javdb_id == item.javdb_id)
                    .with_for_update()
                )
                assert actor is not None
            else:
                actor = session.scalar(
                    select(Actor).where(Actor.javdb_id == item.javdb_id)
                )
            if actor is None:
                actor = Actor(
                    id=uuid.uuid4(),
                    javdb_id=item.javdb_id,
                    name_ja=item.name,
                    name_zh=None,
                    bio_original=None,
                    bio_zh=None,
                    gender="unknown",
                    created_at=current,
                    updated_at=current,
                )
                session.add(actor)
                session.flush()
            else:
                actor.name_ja = item.name
                actor.updated_at = current
            session.execute(
                delete(ActorAlias).where(
                    ActorAlias.actor_id == actor.id,
                    ActorAlias.authority == "javdb",
                )
            )
            protected_aliases = set(
                session.scalars(
                    select(ActorAlias.normalized_alias).where(
                        ActorAlias.actor_id == actor.id,
                        ActorAlias.authority == "actor_mapping",
                    )
                )
            )
            aliases: dict[str, str] = {}
            for alias in (item.name, *item.aliases):
                normalized = _normalize_alias(alias)
                if normalized and normalized not in protected_aliases:
                    aliases.setdefault(normalized, alias)
            session.add_all(
                ActorAlias(
                    actor_id=actor.id,
                    alias=alias,
                    normalized_alias=normalized,
                    authority="javdb",
                )
                for normalized, alias in aliases.items()
            )
            actor_ids_by_javdb[item.javdb_id] = actor.id
        return [actor_ids_by_javdb[item.javdb_id] for item in metadata.actors]

    @staticmethod
    def _upsert_tags(session: Session, metadata: CoreMovieMetadata) -> list[uuid.UUID]:
        tag_ids_by_name: dict[str, uuid.UUID] = {}
        is_postgresql = session.get_bind().dialect.name == "postgresql"
        for name in sorted(metadata.tags):
            if is_postgresql:
                session.execute(
                    postgresql_insert(Tag)
                    .values(id=uuid.uuid4(), name=name)
                    .on_conflict_do_nothing(index_elements=["name"])
                )
                tag = session.scalar(
                    select(Tag).where(Tag.name == name).with_for_update()
                )
                assert tag is not None
            else:
                tag = session.scalar(select(Tag).where(Tag.name == name))
            if tag is None:
                tag = Tag(id=uuid.uuid4(), name=name)
                session.add(tag)
                session.flush()
            tag_ids_by_name[name] = tag.id
        return [tag_ids_by_name[name] for name in metadata.tags]

    @staticmethod
    def _replace_relations(
        session: Session,
        movie_id: uuid.UUID,
        actor_ids: list[uuid.UUID],
        tag_ids: list[uuid.UUID],
    ) -> None:
        session.execute(delete(MovieActor).where(MovieActor.movie_id == movie_id))
        session.execute(delete(MovieTag).where(MovieTag.movie_id == movie_id))
        session.add_all(
            MovieActor(movie_id=movie_id, actor_id=actor_id, position=position)
            for position, actor_id in enumerate(actor_ids)
        )
        session.add_all(
            MovieTag(movie_id=movie_id, tag_id=tag_id) for tag_id in tag_ids
        )

    def _reconcile_image_plans(
        self,
        session: Session,
        movie_id: uuid.UUID,
        metadata: CoreMovieMetadata,
    ) -> None:
        desired: dict[tuple[str, int], str] = {}
        if metadata.cover_url:
            desired[("cover", 0)] = metadata.cover_url
        desired.update(
            {("plot", position): url for position, url in enumerate(metadata.plot_urls)}
        )
        existing = {
            (image.kind, image.position): image
            for image in session.scalars(
                select(CatalogImage).where(
                    CatalogImage.owner_type == "movie",
                    CatalogImage.owner_id == movie_id,
                )
            )
        }
        for key, image in existing.items():
            source_url = desired.get(key)
            if source_url is None:
                if image.sha256 is not None:
                    image.status = "ready"
                elif image.status != "ready":
                    session.delete(image)
                continue
            if image.source_url != source_url:
                image.source_url = source_url
                if image.sha256 is None:
                    image.relative_path = self._placeholder_relative_path
                image.status = "retry_pending"
        for (kind, position), source_url in desired.items():
            if (kind, position) in existing:
                continue
            session.add(
                CatalogImage(
                    id=uuid.uuid4(),
                    owner_type="movie",
                    owner_id=movie_id,
                    kind=kind,
                    position=position,
                    source_url=source_url,
                    relative_path=self._placeholder_relative_path,
                    sha256=None,
                    status="retry_pending",
                    created_at=self._now(),
                )
            )


def _normalize_alias(value: str) -> str:
    return " ".join(value.casefold().split())


def require_active_metadata_claim(
    session: Session,
    fence: MetadataWriteFence,
    *,
    current: datetime,
) -> MetadataJob:
    if current.tzinfo is None:
        raise ValueError("metadata write clock must be timezone-aware")
    job = session.scalar(
        select(MetadataJob)
        .where(
            MetadataJob.id == fence.job_id,
            MetadataJob.status == "running",
            MetadataJob.claim_owner == fence.claim_owner,
            MetadataJob.claim_expires_at > current,
            MetadataJob.movie_id == fence.movie_id,
            MetadataJob.normalized_number == fence.normalized_number,
        )
        .with_for_update()
    )
    if job is None:
        raise CoreImportProblem("metadata_claim_lost")
    stage = session.get(
        MetadataStage,
        (fence.job_id, fence.stage),
        with_for_update=True,
    )
    if stage is None or stage.status != "running":
        raise CoreImportProblem("metadata_claim_lost")
    return job


__all__ = [
    "CoreImportProblem",
    "CoreMetadataImporter",
    "MetadataWriteFence",
    "require_active_metadata_claim",
]
