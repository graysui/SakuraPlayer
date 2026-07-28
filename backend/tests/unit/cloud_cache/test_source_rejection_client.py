from __future__ import annotations

import uuid
from types import SimpleNamespace

from sakuraplayer.cloud_cache.failure_classifier import DeterministicSourceFailure
from sakuraplayer.cloud_cache.source_rejection_client import SourceRejectionClient
from sakuraplayer.resources.source_submission import SourceSubmissionRef


def test_rejection_call_has_only_resource_identity_and_stable_reason() -> None:
    source_id = uuid.uuid4()
    movie_id = uuid.uuid4()
    source_port = RecordingSourcePort(source_id)
    rejection_port = RecordingRejectionPort(source_port)
    client = SourceRejectionClient(source_port, rejection_port)
    failure = DeterministicSourceFailure(
        failure_code="cloud115_source_unavailable",
        rejection_reason_code="cloud115_source_unavailable",
    )

    persisted = client.reject(
        SimpleNamespace(movie_id=movie_id, source_id=source_id),
        failure,
    )

    assert persisted == failure
    assert rejection_port.calls == [
        {
            "website": "sehuatang",
            "external_post_id": 106,
            "reason_code": "cloud115_source_unavailable",
        }
    ]
    assert "magnet" not in repr(rejection_port.calls).lower()


def test_existing_first_reason_wins_without_second_rejection_call() -> None:
    source_id = uuid.uuid4()
    source_port = RecordingSourcePort(
        source_id,
        rejection_reason_code="cloud115_source_unavailable",
    )
    rejection_port = RecordingRejectionPort(source_port)
    client = SourceRejectionClient(source_port, rejection_port)

    persisted = client.reject(
        SimpleNamespace(movie_id=uuid.uuid4(), source_id=source_id),
        DeterministicSourceFailure(
            failure_code="cloud115_source_blocked",
            rejection_reason_code="cloud115_source_blocked",
        ),
    )

    assert persisted.failure_code == "cloud115_source_unavailable"
    assert rejection_port.calls == []


class RecordingSourcePort:
    def __init__(
        self,
        source_id: uuid.UUID,
        rejection_reason_code: str | None = None,
    ) -> None:
        self.source_id = source_id
        self.rejection_reason_code = rejection_reason_code

    def load_submission_ref(self, *, movie_id, source_id) -> SourceSubmissionRef:
        del movie_id
        assert source_id == self.source_id
        return SourceSubmissionRef(
            source_id=source_id,
            website="sehuatang",
            external_post_id=106,
            rejection_reason_code=self.rejection_reason_code,
        )


class RecordingRejectionPort:
    def __init__(self, source_port: RecordingSourcePort) -> None:
        self.source_port = source_port
        self.calls: list[dict[str, object]] = []

    def reject(self, **kwargs) -> None:
        self.calls.append(kwargs)
        self.source_port.rejection_reason_code = str(kwargs["reason_code"])
