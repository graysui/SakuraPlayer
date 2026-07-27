from __future__ import annotations

import pytest

from sakuraplayer.cloud_cache.domain.cache_job import (
    CacheJobState,
    CacheJobStatus,
    CapacityClass,
    InvalidCacheJobTransition,
)

LEGAL_TRANSITIONS = {
    CacheJobStatus.QUEUED: {
        CacheJobStatus.SUBMITTING,
        CacheJobStatus.CANCELLING,
        CacheJobStatus.FAILED,
    },
    CacheJobStatus.SUBMITTING: {
        CacheJobStatus.OFFLINING,
        CacheJobStatus.CANCELLING,
        CacheJobStatus.FAILED,
        CacheJobStatus.DETACHED,
    },
    CacheJobStatus.OFFLINING: {
        CacheJobStatus.RESOLVING,
        CacheJobStatus.CANCELLING,
        CacheJobStatus.FAILED,
        CacheJobStatus.DETACHED,
    },
    CacheJobStatus.RESOLVING: {
        CacheJobStatus.AWAITING_SELECTION,
        CacheJobStatus.READY,
        CacheJobStatus.CANCELLING,
        CacheJobStatus.FAILED,
        CacheJobStatus.DETACHED,
    },
    CacheJobStatus.AWAITING_SELECTION: {
        CacheJobStatus.READY,
        CacheJobStatus.CLEANING,
        CacheJobStatus.FAILED,
        CacheJobStatus.DETACHED,
    },
    CacheJobStatus.READY: {
        CacheJobStatus.CLEANING,
        CacheJobStatus.FAILED,
        CacheJobStatus.DETACHED,
    },
    CacheJobStatus.CANCELLING: {
        CacheJobStatus.CLEANING,
        CacheJobStatus.FAILED,
        CacheJobStatus.DETACHED,
    },
    CacheJobStatus.CLEANING: {
        CacheJobStatus.CLEANED,
        CacheJobStatus.CLEANUP_FAILED,
        CacheJobStatus.FAILED,
        CacheJobStatus.DETACHED,
    },
    CacheJobStatus.CLEANUP_FAILED: {
        CacheJobStatus.CLEANING,
        CacheJobStatus.FAILED,
        CacheJobStatus.DETACHED,
    },
    CacheJobStatus.FAILED: set(),
    CacheJobStatus.CLEANED: set(),
    CacheJobStatus.DETACHED: set(),
}


def _capacity(status: CacheJobStatus) -> CapacityClass:
    if status is CacheJobStatus.QUEUED:
        return CapacityClass.QUEUED
    if status in {
        CacheJobStatus.SUBMITTING,
        CacheJobStatus.OFFLINING,
        CacheJobStatus.RESOLVING,
    }:
        return CapacityClass.RUNNING
    if status in {
        CacheJobStatus.AWAITING_SELECTION,
        CacheJobStatus.READY,
        CacheJobStatus.CLEANING,
        CacheJobStatus.CLEANUP_FAILED,
    }:
        return CapacityClass.READY
    return CapacityClass.RELEASED


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (source, target)
        for source, targets in LEGAL_TRANSITIONS.items()
        for target in targets
    ],
)
def test_all_legal_cache_transitions_preserve_capacity_rules(
    source: CacheJobStatus,
    target: CacheJobStatus,
) -> None:
    source_capacity = (
        CapacityClass.RUNNING
        if source is CacheJobStatus.CANCELLING
        else _capacity(source)
    )

    updated = CacheJobState(source, source_capacity).transition(target)

    assert updated.status is target
    if target is CacheJobStatus.CANCELLING:
        assert updated.capacity_class is source_capacity
    else:
        assert updated.capacity_class is _capacity(target)


@pytest.mark.parametrize("terminal", tuple(CacheJobStatus.terminal()))
def test_terminal_cache_states_cannot_move_backwards(
    terminal: CacheJobStatus,
) -> None:
    state = CacheJobState(terminal, CapacityClass.RELEASED)

    with pytest.raises(InvalidCacheJobTransition) as error:
        state.transition(CacheJobStatus.QUEUED)

    assert error.value.code == "state_conflict"


def test_cancelling_can_preserve_each_original_capacity_class() -> None:
    for capacity in (
        CapacityClass.QUEUED,
        CapacityClass.RUNNING,
        CapacityClass.READY,
    ):
        state = CacheJobState(CacheJobStatus.CANCELLING, capacity)
        assert state.capacity_class is capacity


@pytest.mark.parametrize(
    ("status", "capacity"),
    [
        (CacheJobStatus.QUEUED, CapacityClass.RUNNING),
        (CacheJobStatus.SUBMITTING, CapacityClass.QUEUED),
        (CacheJobStatus.READY, CapacityClass.RELEASED),
        (CacheJobStatus.FAILED, CapacityClass.RUNNING),
        (CacheJobStatus.CANCELLING, CapacityClass.RELEASED),
    ],
)
def test_status_and_capacity_shape_is_validated(
    status: CacheJobStatus,
    capacity: CapacityClass,
) -> None:
    with pytest.raises(ValueError):
        CacheJobState(status, capacity)


def test_wait_expired_is_not_a_cache_job_status() -> None:
    with pytest.raises(ValueError):
        CacheJobStatus("wait_expired")


def test_unlisted_transition_is_rejected() -> None:
    with pytest.raises(InvalidCacheJobTransition):
        CacheJobState(
            CacheJobStatus.OFFLINING,
            CapacityClass.RUNNING,
        ).transition(CacheJobStatus.READY)
