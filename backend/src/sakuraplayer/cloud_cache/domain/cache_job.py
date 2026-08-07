from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CacheJobStatus(str, Enum):
    QUEUED = "queued"
    SUBMITTING = "submitting"
    OFFLINING = "offlining"
    SUBMIT_UNCERTAIN = "submit_uncertain"
    RESOLVING = "resolving"
    AWAITING_SELECTION = "awaiting_selection"
    READY = "ready"
    CANCELLING = "cancelling"
    CLEANING = "cleaning"
    CLEANUP_FAILED = "cleanup_failed"
    FAILED = "failed"
    CLEANED = "cleaned"
    DETACHED = "detached"

    @classmethod
    def terminal(cls) -> frozenset[CacheJobStatus]:
        return frozenset({cls.FAILED, cls.CLEANED, cls.DETACHED})


class CapacityClass(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    READY = "ready"
    RELEASED = "released"


class InvalidCacheJobTransition(ValueError):
    code = "state_conflict"

    def __init__(self) -> None:
        super().__init__(self.code)


_CAPACITY_BY_STATUS = {
    CacheJobStatus.QUEUED: CapacityClass.QUEUED,
    CacheJobStatus.SUBMITTING: CapacityClass.RUNNING,
    CacheJobStatus.OFFLINING: CapacityClass.RUNNING,
    CacheJobStatus.SUBMIT_UNCERTAIN: CapacityClass.RUNNING,
    CacheJobStatus.RESOLVING: CapacityClass.RUNNING,
    CacheJobStatus.AWAITING_SELECTION: CapacityClass.READY,
    CacheJobStatus.READY: CapacityClass.READY,
    CacheJobStatus.CLEANING: CapacityClass.READY,
    CacheJobStatus.CLEANUP_FAILED: CapacityClass.READY,
    CacheJobStatus.FAILED: CapacityClass.RELEASED,
    CacheJobStatus.CLEANED: CapacityClass.RELEASED,
    CacheJobStatus.DETACHED: CapacityClass.RELEASED,
}

_LEGAL_TRANSITIONS = {
    CacheJobStatus.QUEUED: frozenset(
        {
            CacheJobStatus.SUBMITTING,
            CacheJobStatus.CANCELLING,
            CacheJobStatus.FAILED,
        }
    ),
    CacheJobStatus.SUBMITTING: frozenset(
        {
            CacheJobStatus.OFFLINING,
            CacheJobStatus.SUBMIT_UNCERTAIN,
            CacheJobStatus.CANCELLING,
            CacheJobStatus.FAILED,
            CacheJobStatus.DETACHED,
        }
    ),
    CacheJobStatus.OFFLINING: frozenset(
        {
            CacheJobStatus.RESOLVING,
            CacheJobStatus.CANCELLING,
            CacheJobStatus.FAILED,
            CacheJobStatus.DETACHED,
        }
    ),
    CacheJobStatus.SUBMIT_UNCERTAIN: frozenset({CacheJobStatus.CANCELLING}),
    CacheJobStatus.RESOLVING: frozenset(
        {
            CacheJobStatus.AWAITING_SELECTION,
            CacheJobStatus.READY,
            CacheJobStatus.CANCELLING,
            CacheJobStatus.FAILED,
            CacheJobStatus.DETACHED,
        }
    ),
    CacheJobStatus.AWAITING_SELECTION: frozenset(
        {
            CacheJobStatus.READY,
            CacheJobStatus.CLEANING,
            CacheJobStatus.FAILED,
            CacheJobStatus.DETACHED,
        }
    ),
    CacheJobStatus.READY: frozenset(
        {
            CacheJobStatus.CLEANING,
            CacheJobStatus.FAILED,
            CacheJobStatus.DETACHED,
        }
    ),
    CacheJobStatus.CANCELLING: frozenset(
        {
            CacheJobStatus.CLEANING,
            CacheJobStatus.FAILED,
            CacheJobStatus.DETACHED,
        }
    ),
    CacheJobStatus.CLEANING: frozenset(
        {
            CacheJobStatus.CLEANED,
            CacheJobStatus.CLEANUP_FAILED,
            CacheJobStatus.FAILED,
            CacheJobStatus.DETACHED,
        }
    ),
    CacheJobStatus.CLEANUP_FAILED: frozenset(
        {
            CacheJobStatus.CLEANING,
            CacheJobStatus.FAILED,
            CacheJobStatus.DETACHED,
        }
    ),
    CacheJobStatus.FAILED: frozenset(),
    CacheJobStatus.CLEANED: frozenset(),
    CacheJobStatus.DETACHED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class CacheJobState:
    status: CacheJobStatus
    capacity_class: CapacityClass

    def __post_init__(self) -> None:
        if self.status is CacheJobStatus.CANCELLING:
            if self.capacity_class is CapacityClass.RELEASED:
                raise ValueError("cancelling must retain capacity")
            return
        if _CAPACITY_BY_STATUS[self.status] is not self.capacity_class:
            raise ValueError("cache status and capacity class do not match")

    def transition(self, target: CacheJobStatus) -> CacheJobState:
        if target not in _LEGAL_TRANSITIONS[self.status]:
            raise InvalidCacheJobTransition
        capacity = (
            self.capacity_class
            if target is CacheJobStatus.CANCELLING
            else _CAPACITY_BY_STATUS[target]
        )
        return CacheJobState(target, capacity)


__all__ = [
    "CacheJobState",
    "CacheJobStatus",
    "CapacityClass",
    "InvalidCacheJobTransition",
]
