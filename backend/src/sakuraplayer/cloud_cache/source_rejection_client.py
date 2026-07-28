from __future__ import annotations

from typing import Protocol

from sakuraplayer.cloud_cache.failure_classifier import (
    DeterministicSourceFailure,
    classify_rejection_reason,
)
from sakuraplayer.cloud_cache.worker.claim import CacheJobClaim
from sakuraplayer.resources.rejection import SourceRejectionPort
from sakuraplayer.resources.source_submission import SourceSubmissionPort


class SourceRejectionClientPort(Protocol):
    def existing_failure(
        self,
        claim: CacheJobClaim,
    ) -> DeterministicSourceFailure | None: ...

    def reject(
        self,
        claim: CacheJobClaim,
        failure: DeterministicSourceFailure,
    ) -> DeterministicSourceFailure: ...


class SourceRejectionClient:
    def __init__(
        self,
        source_port: SourceSubmissionPort,
        rejection_port: SourceRejectionPort,
    ) -> None:
        self._source_port = source_port
        self._rejection_port = rejection_port

    def existing_failure(
        self,
        claim: CacheJobClaim,
    ) -> DeterministicSourceFailure | None:
        reference = self._reference(claim)
        return classify_rejection_reason(reference.rejection_reason_code)

    def reject(
        self,
        claim: CacheJobClaim,
        failure: DeterministicSourceFailure,
    ) -> DeterministicSourceFailure:
        reference = self._reference(claim)
        existing = classify_rejection_reason(reference.rejection_reason_code)
        if existing is not None:
            return existing
        self._rejection_port.reject(
            website=reference.website,
            external_post_id=reference.external_post_id,
            reason_code=failure.rejection_reason_code,
        )
        persisted = classify_rejection_reason(
            self._reference(claim).rejection_reason_code
        )
        return persisted or failure

    def _reference(self, claim: CacheJobClaim):
        return self._source_port.load_submission_ref(
            movie_id=claim.movie_id,
            source_id=claim.source_id,
        )


__all__ = ["SourceRejectionClient", "SourceRejectionClientPort"]
