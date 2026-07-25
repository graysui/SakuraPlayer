from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.resources.models import ResourceSource, SourceRejection
from sakuraplayer.resources.source_lock import lock_source_keys


class SourceRejectionProblem(RuntimeError):
    def __init__(self, *, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(code)


class SourceRejectionPort(Protocol):
    def reject(
        self,
        *,
        website: str,
        external_post_id: int,
        reason_code: str,
    ) -> None: ...


class SourceRejectionService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._now = now or (lambda: datetime.now(timezone.utc))

    def reject(
        self,
        *,
        website: str,
        external_post_id: int,
        reason_code: str,
    ) -> None:
        _validate_rejection_input(website, external_post_id, reason_code)
        with self._session_factory.begin() as session:
            lock_source_keys(session, {(website, external_post_id)})
            source = session.scalar(
                select(ResourceSource)
                .where(
                    ResourceSource.website == website,
                    ResourceSource.external_post_id == external_post_id,
                )
                .with_for_update()
            )
            if source is None:
                raise SourceRejectionProblem(status_code=404, code="source_not_found")
            existing = session.scalar(
                select(SourceRejection)
                .where(
                    SourceRejection.website == website,
                    SourceRejection.external_post_id == external_post_id,
                )
                .with_for_update()
            )
            source.magnet_key_id = None
            source.magnet_nonce = None
            source.magnet_ciphertext = None
            source.identification_status = "rejected"
            if existing is None:
                session.add(
                    SourceRejection(
                        id=uuid.uuid4(),
                        website=website,
                        external_post_id=external_post_id,
                        reason_code=reason_code,
                        rejected_at=_utc(self._now()),
                        last_seen_release_id=None,
                    )
                )


def _validate_rejection_input(
    website: str,
    external_post_id: int,
    reason_code: str,
) -> None:
    if (
        not website
        or len(website) > 32
        or not isinstance(external_post_id, int)
        or not -(2**63) <= external_post_id < 2**63
        or not reason_code
        or len(reason_code) > 128
        or not all(character.islower() or character.isdigit() or character == "_" for character in reason_code)
    ):
        raise SourceRejectionProblem(status_code=422, code="validation_failed")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("now must return a timezone-aware datetime")
    return value.astimezone(timezone.utc)
