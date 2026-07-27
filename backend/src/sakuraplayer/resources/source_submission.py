from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.identity.crypto import SecretCipher, SecretDecryptionError
from sakuraplayer.resources.models import ResourceSource
from sakuraplayer.resources.source_importer import source_magnet_context


class SourceSubmissionProblem(RuntimeError):
    def __init__(self, *, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class SourceSubmissionRef:
    source_id: uuid.UUID
    website: str
    external_post_id: int


@dataclass(frozen=True, slots=True)
class SourceSubmissionPayload(SourceSubmissionRef):
    magnet: str = field(repr=False)


class SourceSubmissionPort(Protocol):
    def validate_for_play(
        self,
        session: Session,
        *,
        movie_id: uuid.UUID,
        source_id: uuid.UUID,
    ) -> SourceSubmissionRef: ...

    def load_submission_payload(
        self,
        *,
        movie_id: uuid.UUID,
        source_id: uuid.UUID,
    ) -> SourceSubmissionPayload: ...


class SourceSubmissionService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        cipher: SecretCipher,
    ) -> None:
        self._session_factory = session_factory
        self._cipher = cipher

    def validate_for_play(
        self,
        session: Session,
        *,
        movie_id: uuid.UUID,
        source_id: uuid.UUID,
    ) -> SourceSubmissionRef:
        source = self._source_for_play(
            session,
            movie_id=movie_id,
            source_id=source_id,
        )
        return self._reference(source)

    def load_submission_payload(
        self,
        *,
        movie_id: uuid.UUID,
        source_id: uuid.UUID,
    ) -> SourceSubmissionPayload:
        with self._session_factory.begin() as session:
            source = self._source_for_play(
                session,
                movie_id=movie_id,
                source_id=source_id,
            )
            envelope = source.magnet_envelope
            assert envelope is not None
            try:
                magnet = self._cipher.decrypt(
                    envelope,
                    context=source_magnet_context(
                        source.website,
                        source.external_post_id,
                    ),
                ).decode("utf-8")
            except (SecretDecryptionError, UnicodeDecodeError):
                raise self._unavailable() from None
            if not magnet:
                raise self._unavailable()
            reference = self._reference(source)
            return SourceSubmissionPayload(
                source_id=reference.source_id,
                website=reference.website,
                external_post_id=reference.external_post_id,
                magnet=magnet,
            )

    @staticmethod
    def _source_for_play(
        session: Session,
        *,
        movie_id: uuid.UUID,
        source_id: uuid.UUID,
    ) -> ResourceSource:
        source = session.scalar(
            select(ResourceSource)
            .where(
                ResourceSource.id == source_id,
                ResourceSource.movie_id == movie_id,
            )
            .with_for_update()
        )
        if source is None or source.identification_status not in {
            "identified",
            "manual",
            "rejected",
        }:
            raise SourceSubmissionProblem(
                status_code=404,
                code="resource_not_found",
            )
        if source.identification_status == "rejected" or source.magnet_envelope is None:
            raise SourceSubmissionService._unavailable()
        return source

    @staticmethod
    def _reference(source: ResourceSource) -> SourceSubmissionRef:
        return SourceSubmissionRef(
            source_id=source.id,
            website=source.website,
            external_post_id=source.external_post_id,
        )

    @staticmethod
    def _unavailable() -> SourceSubmissionProblem:
        return SourceSubmissionProblem(
            status_code=422,
            code="source_permanently_unavailable",
        )


__all__ = [
    "SourceSubmissionPayload",
    "SourceSubmissionPort",
    "SourceSubmissionProblem",
    "SourceSubmissionRef",
    "SourceSubmissionService",
]
