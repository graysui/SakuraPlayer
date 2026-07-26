from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
import uuid


@dataclass(frozen=True)
class SourceAvailability:
    state: str = "available"
    video_file_size_bytes: int | None = None

    def __post_init__(self) -> None:
        if self.state not in {
            "available",
            "queued",
            "running",
            "ready",
            "failed",
            "rejected",
        }:
            raise ValueError("invalid source availability")
        if self.video_file_size_bytes is not None and self.video_file_size_bytes < 0:
            raise ValueError("invalid video file size")


@dataclass(frozen=True)
class PlaybackProgress:
    position_seconds: float
    duration_seconds: float | None
    completed: bool
    version: int


class SourceAvailabilityPort(Protocol):
    def get_many(
        self,
        source_ids: tuple[uuid.UUID, ...],
    ) -> dict[uuid.UUID, SourceAvailability]: ...


class PlaybackStatePort(Protocol):
    def get_many(
        self,
        movie_ids: tuple[uuid.UUID, ...],
    ) -> dict[uuid.UUID, PlaybackProgress]: ...


class FavoriteStatePort(Protocol):
    def target_ids(self, target_type: str) -> set[uuid.UUID]: ...


class EmptySourceAvailabilityPort:
    def get_many(
        self,
        source_ids: tuple[uuid.UUID, ...],
    ) -> dict[uuid.UUID, SourceAvailability]:
        return {source_id: SourceAvailability() for source_id in source_ids}


class EmptyPlaybackStatePort:
    def get_many(
        self,
        movie_ids: tuple[uuid.UUID, ...],
    ) -> dict[uuid.UUID, PlaybackProgress]:
        del movie_ids
        return {}


class EmptyFavoriteStatePort:
    def target_ids(self, target_type: str) -> set[uuid.UUID]:
        if target_type not in {"movie", "actor"}:
            raise ValueError("invalid favorite target type")
        return set()


__all__ = [
    "EmptyFavoriteStatePort",
    "EmptyPlaybackStatePort",
    "EmptySourceAvailabilityPort",
    "FavoriteStatePort",
    "PlaybackProgress",
    "PlaybackStatePort",
    "SourceAvailability",
    "SourceAvailabilityPort",
]
