from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sakuraplayer.catalog.core_import import (
    CoreImportProblem,
    CoreMetadataImporter,
    MetadataWriteFence,
)
from sakuraplayer.catalog.models import (
    Actor,
    ActorAlias,
    CatalogImage,
    MetadataJob,
    MetadataStage,
    MovieActor,
    MovieTag,
    Tag,
)
from sakuraplayer.catalog.providers.javdb import CoreActorMetadata, CoreMovieMetadata
from sakuraplayer.identity.models import Base
from sakuraplayer.resources.models import Movie

NOW = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def factory() -> sessionmaker:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(engine, expire_on_commit=False)
    finally:
        engine.dispose()


def add_movie(factory: sessionmaker, number: str) -> Movie:
    movie = Movie(
        id=uuid.uuid4(),
        normalized_number=number,
        raw_numbers=[number],
        catalog_state="metadata_running",
        created_at=NOW,
        updated_at=NOW,
    )
    with factory.begin() as session:
        session.add(movie)
    return movie


def add_fence(factory: sessionmaker, movie: Movie) -> MetadataWriteFence:
    job_id = uuid.uuid4()
    claim_owner = f"fixture:{uuid.uuid4().hex}"
    with factory.begin() as session:
        session.add_all(
            [
                MetadataJob(
                    id=job_id,
                    movie_id=movie.id,
                    normalized_number=movie.normalized_number,
                    priority=40,
                    reason="initial",
                    sort_date=date(2026, 7, 1),
                    retry_mode="full",
                    requested_stages=[],
                    status="running",
                    attempt_no=1,
                    parent_job_id=None,
                    claim_owner=claim_owner,
                    claim_expires_at=NOW + timedelta(seconds=30),
                    started_at=NOW,
                    finished_at=None,
                    elapsed_ms=None,
                    failure_code=None,
                    failure_detail=None,
                    created_at=NOW,
                ),
                MetadataStage(
                    job_id=job_id,
                    stage="javdb_core",
                    status="running",
                    started_at=NOW,
                    finished_at=None,
                    failure_code=None,
                ),
            ]
        )
    return MetadataWriteFence(
        job_id=job_id,
        claim_owner=claim_owner,
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        stage="javdb_core",
    )


def metadata(
    number: str = "ABP-123", javdb_id: str = "javdb-abp-123"
) -> CoreMovieMetadata:
    return CoreMovieMetadata(
        javdb_id=javdb_id,
        normalized_number=number,
        title_original="Fixture title",
        release_date=date(2026, 7, 1),
        maker="Fixture Maker",
        series="Fixture Series",
        director="Fixture Director",
        actors=(
            CoreActorMetadata(
                javdb_id="actor-1",
                name="Actor One",
                aliases=("Alias One", "Actor One"),
            ),
            CoreActorMetadata(
                javdb_id="actor-2",
                name="Actor Two",
                aliases=(),
            ),
        ),
        tags=("Drama", "HD"),
        score=Decimal("4.25"),
        cover_url="https://c0.jdbstatic.com/covers/abp-123.jpg",
        plot_urls=(
            "https://c0.jdbstatic.com/samples/abp-123-1.jpg",
            "https://c0.jdbstatic.com/samples/abp-123-2.jpg",
        ),
    )


def test_core_import_commits_movie_relations_and_image_plans_atomically(
    factory: sessionmaker,
) -> None:
    movie = add_movie(factory, "ABP-123")
    fence = add_fence(factory, movie)
    importer = CoreMetadataImporter(
        factory,
        placeholder_relative_path="_placeholder/catalog.png",
        now=lambda: NOW,
    )

    importer.import_core(movie_id=movie.id, metadata=metadata(), fence=fence)

    with factory() as session:
        persisted = session.get(Movie, movie.id)
        actors = list(session.scalars(select(Actor).order_by(Actor.javdb_id)))
        aliases = list(session.scalars(select(ActorAlias).order_by(ActorAlias.alias)))
        relations = list(
            session.scalars(
                select(MovieActor)
                .where(MovieActor.movie_id == movie.id)
                .order_by(MovieActor.position)
            )
        )
        tags = list(session.scalars(select(Tag).order_by(Tag.name)))
        tag_relations = list(
            session.scalars(select(MovieTag).where(MovieTag.movie_id == movie.id))
        )
        images = list(
            session.scalars(
                select(CatalogImage)
                .where(CatalogImage.owner_id == movie.id)
                .order_by(CatalogImage.kind, CatalogImage.position)
            )
        )

    assert persisted is not None
    assert persisted.catalog_state == "core_ready"
    assert persisted.javdb_id == "javdb-abp-123"
    assert persisted.title_original == "Fixture title"
    assert persisted.metadata_updated_at is not None
    assert persisted.metadata_updated_at.replace(tzinfo=timezone.utc) == NOW
    assert [actor.javdb_id for actor in actors] == ["actor-1", "actor-2"]
    assert [alias.normalized_alias for alias in aliases] == [
        "actor one",
        "actor two",
        "alias one",
    ]
    assert [relation.position for relation in relations] == [0, 1]
    assert [tag.name for tag in tags] == ["Drama", "HD"]
    assert len(tag_relations) == 2
    assert [(image.kind, image.position, image.status) for image in images] == [
        ("cover", 0, "retry_pending"),
        ("plot", 0, "retry_pending"),
        ("plot", 1, "retry_pending"),
    ]
    assert all(image.relative_path == "_placeholder/catalog.png" for image in images)


def test_core_import_is_idempotent_and_replaces_provider_owned_relations(
    factory: sessionmaker,
) -> None:
    movie = add_movie(factory, "ABP-123")
    fence = add_fence(factory, movie)
    importer = CoreMetadataImporter(
        factory,
        placeholder_relative_path="_placeholder/catalog.png",
        now=lambda: NOW,
    )
    importer.import_core(movie_id=movie.id, metadata=metadata(), fence=fence)
    changed = metadata()
    changed = CoreMovieMetadata(
        **{
            **changed.__dict__,
            "actors": changed.actors[:1],
            "tags": ("Drama",),
            "plot_urls": changed.plot_urls[:1],
        }
    )

    importer.import_core(movie_id=movie.id, metadata=changed, fence=fence)

    with factory() as session:
        assert len(list(session.scalars(select(MovieActor)))) == 1
        assert len(list(session.scalars(select(MovieTag)))) == 1
        images = list(session.scalars(select(CatalogImage)))
    assert len(images) == 2


def test_core_import_rolls_back_when_javdb_identity_conflicts(
    factory: sessionmaker,
) -> None:
    existing = add_movie(factory, "ABP-122")
    target = add_movie(factory, "ABP-123")
    existing_fence = add_fence(factory, existing)
    target_fence = add_fence(factory, target)
    importer = CoreMetadataImporter(
        factory,
        placeholder_relative_path="_placeholder/catalog.png",
        now=lambda: NOW,
    )
    importer.import_core(
        movie_id=existing.id,
        metadata=metadata(number="ABP-122", javdb_id="shared-javdb-id"),
        fence=existing_fence,
    )

    with pytest.raises(CoreImportProblem) as conflict:
        importer.import_core(
            movie_id=target.id,
            metadata=metadata(javdb_id="shared-javdb-id"),
            fence=target_fence,
        )

    assert conflict.value.code == "metadata_core_identity_conflict"
    with factory() as session:
        persisted = session.get(Movie, target.id)
        target_relations = list(
            session.scalars(select(MovieActor).where(MovieActor.movie_id == target.id))
        )
    assert persisted is not None
    assert persisted.catalog_state == "metadata_running"
    assert persisted.javdb_id is None
    assert target_relations == []


def test_core_import_rejects_expired_claim_without_writes(
    factory: sessionmaker,
) -> None:
    movie = add_movie(factory, "ABP-123")
    fence = add_fence(factory, movie)
    with factory.begin() as session:
        job = session.get(MetadataJob, fence.job_id)
        assert job is not None
        job.claim_expires_at = NOW
    importer = CoreMetadataImporter(
        factory,
        placeholder_relative_path="_placeholder/catalog.png",
        now=lambda: NOW,
    )

    with pytest.raises(CoreImportProblem) as expired:
        importer.import_core(movie_id=movie.id, metadata=metadata(), fence=fence)

    assert expired.value.code == "metadata_claim_lost"
    with factory() as session:
        persisted = session.get(Movie, movie.id)
    assert persisted is not None
    assert persisted.javdb_id is None
    assert persisted.catalog_state == "metadata_running"


def test_core_import_rejects_fence_for_another_movie_or_stage(
    factory: sessionmaker,
) -> None:
    owner = add_movie(factory, "ABP-122")
    target = add_movie(factory, "ABP-123")
    fence = add_fence(factory, owner)
    importer = CoreMetadataImporter(
        factory,
        placeholder_relative_path="_placeholder/catalog.png",
        now=lambda: NOW,
    )
    wrong_movie = MetadataWriteFence(
        job_id=fence.job_id,
        claim_owner=fence.claim_owner,
        movie_id=target.id,
        normalized_number=target.normalized_number,
        stage="javdb_core",
    )
    wrong_stage = MetadataWriteFence(
        job_id=fence.job_id,
        claim_owner=fence.claim_owner,
        movie_id=owner.id,
        normalized_number=owner.normalized_number,
        stage="images",
    )

    for movie, core, invalid_fence in (
        (
            target,
            metadata(number="ABP-123", javdb_id="target-id"),
            wrong_movie,
        ),
        (
            owner,
            metadata(number="ABP-122", javdb_id="owner-id"),
            wrong_stage,
        ),
    ):
        with pytest.raises(CoreImportProblem) as error:
            importer.import_core(
                movie_id=movie.id,
                metadata=core,
                fence=invalid_fence,
            )
        assert error.value.code == "metadata_claim_lost"
    with factory() as session:
        assert session.get(Movie, owner.id).javdb_id is None
        assert session.get(Movie, target.id).javdb_id is None


def test_core_reimport_preserves_actor_mapping_alias_with_same_normalized_value(
    factory: sessionmaker,
) -> None:
    movie = add_movie(factory, "ABP-123")
    fence = add_fence(factory, movie)
    importer = CoreMetadataImporter(
        factory,
        placeholder_relative_path="_placeholder/catalog.png",
        now=lambda: NOW,
    )
    importer.import_core(movie_id=movie.id, metadata=metadata(), fence=fence)
    with factory.begin() as session:
        actor = session.scalar(select(Actor).where(Actor.javdb_id == "actor-1"))
        assert actor is not None
        alias = session.get(ActorAlias, (actor.id, "alias one"))
        assert alias is not None
        alias.authority = "actor_mapping"

    importer.import_core(movie_id=movie.id, metadata=metadata(), fence=fence)

    with factory() as session:
        actor = session.scalar(select(Actor).where(Actor.javdb_id == "actor-1"))
        assert actor is not None
        alias = session.get(ActorAlias, (actor.id, "alias one"))
    assert alias is not None
    assert alias.authority == "actor_mapping"


def test_core_reimport_keeps_last_ready_image_until_replacement_succeeds(
    factory: sessionmaker,
) -> None:
    movie = add_movie(factory, "ABP-123")
    fence = add_fence(factory, movie)
    importer = CoreMetadataImporter(
        factory,
        placeholder_relative_path="_placeholder/catalog.png",
        now=lambda: NOW,
    )
    importer.import_core(movie_id=movie.id, metadata=metadata(), fence=fence)
    with factory.begin() as session:
        images = list(
            session.scalars(
                select(CatalogImage)
                .where(CatalogImage.owner_id == movie.id)
                .order_by(CatalogImage.kind, CatalogImage.position)
            )
        )
        for image in images:
            image.relative_path = f"movie/{movie.id}/{image.kind}-{image.position}.png"
            image.sha256 = "a" * 64
            image.status = "ready"
            if image.kind == "plot" and image.position == 0:
                image.status = "retry_pending"
    changed = metadata().model_copy(
        update={
            "cover_url": "https://c0.jdbstatic.com/covers/replacement.jpg",
            "plot_urls": (),
        }
    )

    importer.import_core(movie_id=movie.id, metadata=changed, fence=fence)

    with factory() as session:
        images = list(
            session.scalars(
                select(CatalogImage)
                .where(CatalogImage.owner_id == movie.id)
                .order_by(CatalogImage.kind, CatalogImage.position)
            )
        )
    cover = next(image for image in images if image.kind == "cover")
    assert cover.source_url == "https://c0.jdbstatic.com/covers/replacement.jpg"
    assert cover.status == "retry_pending"
    assert cover.sha256 == "a" * 64
    assert cover.relative_path.endswith("cover-0.png")
    assert len([image for image in images if image.kind == "plot"]) == 2
    assert all(image.status == "ready" for image in images if image.kind == "plot")
