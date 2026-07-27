from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sakuraplayer.identity.models import Base

_JSON_VALUE = JSON(none_as_null=True).with_variant(
    JSONB(none_as_null=True),
    "postgresql",
)


class MetadataQueueState(Base):
    __tablename__ = "metadata_queue_state"
    __table_args__ = (
        CheckConstraint("singleton_key", name="ck_metadata_queue_state_singleton"),
    )

    singleton_key: Mapped[bool] = mapped_column(Boolean, primary_key=True, default=True)
    initial_as_of: Mapped[date] = mapped_column(Date, nullable=False)
    initial_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class MetadataJob(Base):
    __tablename__ = "metadata_job"
    __table_args__ = (
        CheckConstraint(
            "(reason = 'manual_or_search' AND priority = 10) OR "
            "(reason = 'ranking' AND priority = 20) OR "
            "(reason = 'daily' AND priority = 30) OR "
            "(reason = 'initial' AND priority = 40) OR "
            "(reason = 'history' AND priority = 50)",
            name="ck_metadata_job_priority_reason",
        ),
        CheckConstraint(
            "retry_mode IN ('full', 'missing_enrichment')",
            name="ck_metadata_job_retry_mode",
        ),
        CheckConstraint(
            "(retry_mode = 'full' AND requested_stages = '[]'::jsonb) OR "
            "(retry_mode = 'missing_enrichment' "
            "AND jsonb_typeof(requested_stages) = 'array' "
            "AND jsonb_array_length(requested_stages) > 0 "
            "AND requested_stages <@ "
            '\'["images","dmm","actor_map","gfriends","translation"]\'::jsonb '
            "AND NOT requested_stages ? 'javdb_core')",
            name="ck_metadata_job_retry_shape",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', "
            "'completed_with_warnings', 'failed')",
            name="ck_metadata_job_status",
        ),
        CheckConstraint("attempt_no >= 1", name="ck_metadata_job_attempt_no"),
        CheckConstraint(
            "elapsed_ms IS NULL OR elapsed_ms >= 0",
            name="ck_metadata_job_elapsed",
        ),
        CheckConstraint(
            "(status = 'queued' AND claim_owner IS NULL "
            "AND claim_expires_at IS NULL AND started_at IS NULL "
            "AND finished_at IS NULL AND elapsed_ms IS NULL "
            "AND failure_code IS NULL AND failure_detail IS NULL) OR "
            "(status = 'running' AND claim_owner IS NOT NULL "
            "AND claim_expires_at IS NOT NULL AND started_at IS NOT NULL "
            "AND finished_at IS NULL AND elapsed_ms IS NULL "
            "AND failure_code IS NULL AND failure_detail IS NULL) OR "
            "(status IN ('completed', 'completed_with_warnings') "
            "AND claim_owner IS NULL AND claim_expires_at IS NULL "
            "AND started_at IS NOT NULL AND finished_at IS NOT NULL "
            "AND elapsed_ms IS NOT NULL AND failure_code IS NULL "
            "AND failure_detail IS NULL) OR "
            "(status = 'failed' AND claim_owner IS NULL "
            "AND claim_expires_at IS NULL AND started_at IS NOT NULL "
            "AND finished_at IS NOT NULL AND elapsed_ms IS NOT NULL "
            "AND failure_code IS NOT NULL AND failure_detail IS NOT NULL)",
            name="ck_metadata_job_state",
        ),
        UniqueConstraint(
            "normalized_number",
            "attempt_no",
            name="uq_metadata_job_number_attempt",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    movie_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("movie.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    normalized_number: Mapped[str] = mapped_column(String(128), nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    sort_date: Mapped[date | None] = mapped_column(Date)
    retry_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_stages: Mapped[list[str]] = mapped_column(_JSON_VALUE, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_no: Mapped[int] = mapped_column(BigInteger, nullable=False)
    parent_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("metadata_job.id", ondelete="RESTRICT")
    )
    claim_owner: Mapped[str | None] = mapped_column(String(128))
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    elapsed_ms: Mapped[int | None] = mapped_column(BigInteger)
    failure_code: Mapped[str | None] = mapped_column(String(128))
    failure_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


Index(
    "uq_metadata_job_active_number",
    MetadataJob.normalized_number,
    unique=True,
    postgresql_where=MetadataJob.status.in_(("queued", "running")),
    sqlite_where=MetadataJob.status.in_(("queued", "running")),
)
Index(
    "ix_metadata_job_claim",
    MetadataJob.status,
    MetadataJob.priority,
    MetadataJob.sort_date.desc().nulls_last(),
    MetadataJob.created_at,
    MetadataJob.id,
).ddl_if(dialect="postgresql")
Index(
    "ix_metadata_job_claim_sqlite",
    MetadataJob.status,
    MetadataJob.priority,
    MetadataJob.sort_date.desc(),
    MetadataJob.created_at,
    MetadataJob.id,
).ddl_if(dialect="sqlite")


class MetadataStage(Base):
    __tablename__ = "metadata_stage"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('javdb_core', 'images', 'dmm', 'actor_map', "
            "'gfriends', 'translation')",
            name="ck_metadata_stage_name",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'warning', "
            "'failed', 'skipped')",
            name="ck_metadata_stage_status",
        ),
        CheckConstraint(
            "(status = 'pending' AND started_at IS NULL "
            "AND finished_at IS NULL AND failure_code IS NULL) OR "
            "(status = 'running' AND started_at IS NOT NULL "
            "AND finished_at IS NULL AND failure_code IS NULL) OR "
            "(status = 'succeeded' AND started_at IS NOT NULL "
            "AND finished_at IS NOT NULL AND failure_code IS NULL) OR "
            "(status IN ('warning', 'failed') AND started_at IS NOT NULL "
            "AND finished_at IS NOT NULL AND failure_code IS NOT NULL) OR "
            "(status = 'skipped' AND started_at IS NULL "
            "AND finished_at IS NULL AND failure_code IS NULL)",
            name="ck_metadata_stage_state",
        ),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("metadata_job.id", ondelete="CASCADE"),
        primary_key=True,
    )
    stage: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(128))


class Actor(Base):
    __tablename__ = "actor"
    __table_args__ = (
        CheckConstraint(
            "gender IN ('female', 'male', 'unknown')",
            name="ck_actor_gender",
        ),
        UniqueConstraint("javdb_id", name="uq_actor_javdb_id"),
        CheckConstraint(
            "(bio_zh IS NULL AND bio_zh_source IS NULL) OR "
            "(bio_zh IS NOT NULL AND bio_zh_source IN ('actor_mapping', 'ai'))",
            name="ck_actor_bio_zh_source",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    javdb_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name_ja: Mapped[str | None] = mapped_column(String(255))
    name_zh: Mapped[str | None] = mapped_column(String(255))
    bio_original: Mapped[str | None] = mapped_column(Text)
    bio_zh: Mapped[str | None] = mapped_column(Text)
    bio_zh_source: Mapped[str | None] = mapped_column(String(16))
    gender: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ActorAlias(Base):
    __tablename__ = "actor_alias"
    __table_args__ = (
        CheckConstraint(
            "authority IN ('javdb', 'actor_mapping')",
            name="ck_actor_alias_authority",
        ),
    )

    actor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actor.id", ondelete="CASCADE"),
        primary_key=True,
    )
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(255), primary_key=True)
    authority: Mapped[str] = mapped_column(String(32), nullable=False)


Index("ix_actor_alias_normalized", ActorAlias.normalized_alias)


class MovieActor(Base):
    __tablename__ = "movie_actor"
    __table_args__ = (
        CheckConstraint("position >= 0", name="ck_movie_actor_position"),
        UniqueConstraint("movie_id", "position", name="uq_movie_actor_position"),
    )

    movie_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("movie.id", ondelete="CASCADE"),
        primary_key=True,
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actor.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class Tag(Base):
    __tablename__ = "tag"
    __table_args__ = (UniqueConstraint("name", name="uq_tag_name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class MovieTag(Base):
    __tablename__ = "movie_tag"

    movie_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("movie.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tag.id", ondelete="RESTRICT"),
        primary_key=True,
    )


class CatalogImage(Base):
    __tablename__ = "catalog_image"
    __table_args__ = (
        CheckConstraint(
            "owner_type IN ('movie', 'actor')",
            name="ck_catalog_image_owner_type",
        ),
        CheckConstraint(
            "kind IN ('cover', 'plot', 'profile', 'placeholder')",
            name="ck_catalog_image_kind",
        ),
        CheckConstraint("position >= 0", name="ck_catalog_image_position"),
        CheckConstraint(
            "kind <> 'cover' OR position = 0",
            name="ck_catalog_image_cover_position",
        ),
        CheckConstraint(
            "status IN ('ready', 'placeholder', 'retry_pending')",
            name="ck_catalog_image_status",
        ),
        CheckConstraint(
            "relative_path <> '' AND relative_path NOT LIKE '/%' "
            "AND relative_path NOT LIKE '%..%'",
            name="ck_catalog_image_relative_path",
        ),
        CheckConstraint(
            "sha256 IS NULL OR (length(sha256) = 64 AND lower(sha256) = sha256)",
            name="ck_catalog_image_sha256",
        ),
        CheckConstraint(
            "sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_catalog_image_sha256_format",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "(status = 'ready' AND source_url IS NOT NULL AND sha256 IS NOT NULL) OR "
            "(status = 'retry_pending' AND source_url IS NOT NULL) OR "
            "(status = 'placeholder' AND source_url IS NULL AND sha256 IS NOT NULL)",
            name="ck_catalog_image_ready_shape",
        ),
        UniqueConstraint(
            "owner_type",
            "owner_id",
            "kind",
            "position",
            name="uq_catalog_image_owner_kind_position",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    owner_type: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


Index("ix_catalog_image_owner", CatalogImage.owner_type, CatalogImage.owner_id)


class ProviderSnapshotRequest(Base):
    __tablename__ = "provider_snapshot_request"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'claimed', 'completed', 'failed')",
            name="ck_provider_snapshot_request_status",
        ),
        CheckConstraint(
            "attempt_count >= 0", name="ck_provider_snapshot_request_attempt"
        ),
        CheckConstraint(
            "(status = 'queued' AND claim_owner IS NULL AND claim_token IS NULL "
            "AND claim_expires_at IS NULL AND completed_at IS NULL "
            "AND failure_code IS NULL) OR "
            "(status = 'claimed' AND claim_owner IS NOT NULL "
            "AND claim_token IS NOT NULL AND claim_expires_at IS NOT NULL "
            "AND completed_at IS NULL AND failure_code IS NULL) OR "
            "(status = 'completed' AND claim_owner IS NULL AND claim_token IS NULL "
            "AND claim_expires_at IS NULL AND completed_at IS NOT NULL "
            "AND failure_code IS NULL) OR "
            "(status = 'failed' AND claim_owner IS NULL AND claim_token IS NULL "
            "AND claim_expires_at IS NULL AND completed_at IS NOT NULL "
            "AND failure_code IS NOT NULL)",
            name="ck_provider_snapshot_request_state",
        ),
        UniqueConstraint(
            "scheduled_for",
            name="uq_provider_snapshot_request_slot",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    claim_owner: Mapped[str | None] = mapped_column(String(128))
    claim_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(128))


class ActorMappingSnapshot(Base):
    __tablename__ = "actor_mapping_snapshot"
    __table_args__ = (
        CheckConstraint(
            "status IN ('current', 'superseded')",
            name="ck_actor_mapping_snapshot_state",
        ),
        CheckConstraint(
            "byte_size > 0 AND byte_size <= 16777216",
            name="ck_actor_mapping_snapshot_size",
        ),
        CheckConstraint(
            "length(sha256) = 64 AND lower(sha256) = sha256",
            name="ck_actor_mapping_snapshot_sha256",
        ),
        CheckConstraint(
            "relative_path <> '' AND relative_path NOT LIKE '/%' "
            "AND relative_path NOT LIKE '%..%'",
            name="ck_actor_mapping_snapshot_path",
        ),
        UniqueConstraint("sha256", name="uq_actor_mapping_snapshot_sha256"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


Index(
    "uq_actor_mapping_snapshot_current",
    ActorMappingSnapshot.status,
    unique=True,
    postgresql_where=ActorMappingSnapshot.status == "current",
    sqlite_where=ActorMappingSnapshot.status == "current",
)


class GfriendsSnapshot(Base):
    __tablename__ = "gfriends_snapshot"
    __table_args__ = (
        CheckConstraint(
            "status IN ('current', 'superseded')",
            name="ck_gfriends_snapshot_state",
        ),
        CheckConstraint(
            "byte_size > 0 AND byte_size <= 33554432",
            name="ck_gfriends_snapshot_size",
        ),
        CheckConstraint(
            "length(sha256) = 64 AND lower(sha256) = sha256",
            name="ck_gfriends_snapshot_sha256",
        ),
        CheckConstraint(
            "relative_path <> '' AND relative_path NOT LIKE '/%' "
            "AND relative_path NOT LIKE '%..%'",
            name="ck_gfriends_snapshot_path",
        ),
        UniqueConstraint("sha256", name="uq_gfriends_snapshot_sha256"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


Index(
    "uq_gfriends_snapshot_current",
    GfriendsSnapshot.status,
    unique=True,
    postgresql_where=GfriendsSnapshot.status == "current",
    sqlite_where=GfriendsSnapshot.status == "current",
)


class GfriendsActorAsset(Base):
    __tablename__ = "gfriends_actor_asset"
    __table_args__ = (
        CheckConstraint(
            "asset_kind IN ('profile', 'gallery')",
            name="ck_gfriends_actor_asset_kind",
        ),
        CheckConstraint(
            "(asset_kind = 'profile' AND position = 0) OR "
            "(asset_kind = 'gallery' AND position >= 1)",
            name="ck_gfriends_actor_asset_position",
        ),
        CheckConstraint("match_name <> ''", name="ck_gfriends_actor_asset_match_name"),
        CheckConstraint(
            "url LIKE 'https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/%'",
            name="ck_gfriends_actor_asset_url",
        ),
        UniqueConstraint(
            "actor_id",
            "asset_kind",
            "position",
            name="uq_gfriends_actor_asset_owner_position",
        ),
        UniqueConstraint("url", name="uq_gfriends_actor_asset_url"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actor.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("gfriends_snapshot.id", ondelete="RESTRICT"),
        nullable=False,
    )
    asset_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    match_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class TranslationRecord(Base):
    __tablename__ = "translation_record"
    __table_args__ = (
        CheckConstraint(
            "owner_type IN ('movie_title', 'movie_description', 'actor_bio')",
            name="ck_translation_record_owner_type",
        ),
        CheckConstraint(
            "length(source_text) BETWEEN 1 AND 32000",
            name="ck_translation_record_source_text",
        ),
        CheckConstraint(
            "length(source_hash) = 64 AND lower(source_hash) = source_hash",
            name="ck_translation_record_source_hash",
        ),
        CheckConstraint(
            "source_hash ~ '^[0-9a-f]{64}$'",
            name="ck_translation_record_source_hash_format",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "length(model) BETWEEN 1 AND 255",
            name="ck_translation_record_model",
        ),
        CheckConstraint(
            "length(prompt_version) BETWEEN 1 AND 64",
            name="ck_translation_record_prompt_version",
        ),
        CheckConstraint(
            "translated_text IS NULL OR length(translated_text) BETWEEN 1 AND 32000",
            name="ck_translation_record_translated_text",
        ),
        CheckConstraint(
            "status IN ('reserved', 'dispatched', 'completed', 'rejected', 'unknown')",
            name="ck_translation_record_status",
        ),
        CheckConstraint(
            "(status = 'reserved' AND translated_text IS NULL "
            "AND claim_token IS NOT NULL AND claim_expires_at IS NOT NULL "
            "AND dispatch_started_at IS NULL AND failure_code IS NULL) OR "
            "(status = 'dispatched' AND translated_text IS NULL "
            "AND claim_token IS NOT NULL AND claim_expires_at IS NULL "
            "AND dispatch_started_at IS NOT NULL AND failure_code IS NULL) OR "
            "(status = 'completed' AND translated_text IS NOT NULL "
            "AND claim_token IS NULL AND claim_expires_at IS NULL "
            "AND dispatch_started_at IS NOT NULL AND failure_code IS NULL) OR "
            "(status IN ('rejected', 'unknown') AND translated_text IS NULL "
            "AND claim_token IS NULL AND claim_expires_at IS NULL "
            "AND dispatch_started_at IS NOT NULL AND failure_code IS NOT NULL)",
            name="ck_translation_record_state",
        ),
        UniqueConstraint(
            "owner_type",
            "owner_id",
            "source_hash",
            "model",
            "prompt_version",
            name="uq_translation_record_business_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    owner_type: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    translated_text: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    claim_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatch_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    failure_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


__all__ = [
    "Actor",
    "ActorAlias",
    "ActorMappingSnapshot",
    "CatalogImage",
    "GfriendsActorAsset",
    "GfriendsSnapshot",
    "MetadataJob",
    "MetadataQueueState",
    "MetadataStage",
    "MovieActor",
    "MovieTag",
    "ProviderSnapshotRequest",
    "Tag",
    "TranslationRecord",
]
