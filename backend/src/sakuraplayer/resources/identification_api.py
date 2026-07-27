from __future__ import annotations

import base64
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, select, tuple_
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.identity.api import ApiProblem
from sakuraplayer.resources.models import Movie, ResourceSource, ResourceSourceLabel


class IdentificationProblem(RuntimeError):
    def __init__(self, *, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class PendingSourceView:
    id: uuid.UUID
    website: str
    external_post_id: int
    title: str
    raw_number: str | None
    publish_date: date | None
    section: str
    category: str | None
    resource_size_mb: int | None
    identification_status: str


@dataclass(frozen=True)
class PendingSourcePage:
    items: list[PendingSourceView]
    next_cursor: str | None


@dataclass(frozen=True)
class IdentifiedSourceView:
    id: uuid.UUID
    website: str
    external_post_id: int
    title: str
    publish_date: date | None
    category: str
    labels: list[str]
    resource_size_mb: int | None


class IdentificationService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_sources(
        self,
        *,
        identification_status: str,
        query: str | None,
        cursor: str | None,
        limit: int,
    ) -> PendingSourcePage:
        if identification_status not in {"pending", "manual"}:
            raise IdentificationProblem(status_code=422, code="validation_failed")
        normalized_query = query.strip().casefold() if query is not None else ""
        if len(normalized_query) > 200:
            raise IdentificationProblem(status_code=422, code="validation_failed")
        cursor_values = self._decode_cursor(
            cursor,
            status=identification_status,
            query=normalized_query,
        )
        statement = select(ResourceSource).where(
            ResourceSource.identification_status == identification_status
        )
        if normalized_query:
            escaped = _escape_like(normalized_query)
            conditions = [
                ResourceSource.title.ilike(f"%{escaped}%", escape="\\"),
                ResourceSource.raw_number.ilike(f"%{escaped}%", escape="\\"),
            ]
            if normalized_query.isdecimal():
                try:
                    post_id = int(normalized_query)
                except ValueError:
                    post_id = -1
                if -(2**63) <= post_id < 2**63:
                    conditions.append(ResourceSource.external_post_id == post_id)
            statement = statement.where(or_(*conditions))
        if cursor_values is not None:
            imported_at, source_id = cursor_values
            statement = statement.where(
                tuple_(ResourceSource.imported_at, ResourceSource.id)
                < tuple_(imported_at, source_id)
            )
        statement = statement.order_by(
            ResourceSource.imported_at.desc(),
            ResourceSource.id.desc(),
        ).limit(limit + 1)
        with self._session_factory() as session:
            sources = list(session.scalars(statement))
        has_more = len(sources) > limit
        visible = sources[:limit]
        next_cursor = None
        if has_more and visible:
            last = visible[-1]
            next_cursor = self._encode_cursor(
                last.imported_at,
                last.id,
                status=identification_status,
                query=normalized_query,
            )
        return PendingSourcePage(
            items=[_pending_view(source) for source in visible],
            next_cursor=next_cursor,
        )

    def identify(
        self,
        *,
        source_id: uuid.UUID,
        movie_id: uuid.UUID,
    ) -> IdentifiedSourceView:
        with self._session_factory.begin() as session:
            source = session.scalar(
                select(ResourceSource)
                .where(ResourceSource.id == source_id)
                .with_for_update()
            )
            if source is None or source.identification_status == "rejected":
                raise IdentificationProblem(status_code=404, code="source_not_found")
            if source.identification_status != "pending":
                raise IdentificationProblem(
                    status_code=409,
                    code="source_already_identified",
                )
            movie = session.get(Movie, movie_id, with_for_update=True)
            if movie is None:
                raise IdentificationProblem(status_code=404, code="resource_not_found")
            source.movie_id = movie.id
            source.normalized_number = movie.normalized_number
            source.identification_status = "manual"
            labels = sorted(
                session.scalars(
                    select(ResourceSourceLabel.label).where(
                        ResourceSourceLabel.source_id == source.id
                    )
                )
            )
            return IdentifiedSourceView(
                id=source.id,
                website=source.website,
                external_post_id=source.external_post_id,
                title=source.title,
                publish_date=source.publish_date,
                category=source.section,
                labels=labels,
                resource_size_mb=source.resource_size_mb,
            )

    @staticmethod
    def _encode_cursor(
        imported_at: datetime,
        source_id: uuid.UUID,
        *,
        status: str,
        query: str,
    ) -> str:
        payload = json.dumps(
            {
                "id": str(source_id),
                "imported_at": imported_at.isoformat(),
                "q": query,
                "status": status,
                "v": 1,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")

    @staticmethod
    def _decode_cursor(
        cursor: str | None,
        *,
        status: str,
        query: str,
    ) -> tuple[datetime, uuid.UUID] | None:
        if cursor is None:
            return None
        try:
            padding = "=" * (-len(cursor) % 4)
            raw = base64.b64decode(
                cursor + padding,
                altchars=b"-_",
                validate=True,
            )
            payload: Any = json.loads(raw.decode("utf-8"))
            if (
                not isinstance(payload, dict)
                or set(payload) != {"id", "imported_at", "q", "status", "v"}
                or payload["v"] != 1
                or not isinstance(payload["id"], str)
                or not isinstance(payload["imported_at"], str)
                or not isinstance(payload["q"], str)
                or not isinstance(payload["status"], str)
                or payload["status"] != status
                or payload["q"] != query
            ):
                raise ValueError
            imported_at = datetime.fromisoformat(payload["imported_at"])
            source_id = uuid.UUID(payload["id"])
            if imported_at.tzinfo is None:
                raise ValueError
            return imported_at, source_id
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            raise IdentificationProblem(
                status_code=422,
                code="validation_failed",
            ) from None


class PendingSourceOutput(BaseModel):
    id: uuid.UUID
    website: str
    external_post_id: int
    title: str
    raw_number: str | None
    publish_date: date | None
    section: str
    category: str | None
    resource_size_mb: int | None
    identification_status: str


class PendingSourcePageOutput(BaseModel):
    items: list[PendingSourceOutput]
    next_cursor: str | None


class IdentificationInput(BaseModel):
    movie_id: uuid.UUID


class MovieSourceOutput(BaseModel):
    id: uuid.UUID
    website: str
    external_post_id: int
    title: str
    publish_date: date | None
    category: str
    labels: list[str]
    resource_size_mb: int | None
    video_file_size_bytes: int | None
    availability: str


def create_identification_api(
    service: IdentificationService,
    *,
    current_admin_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/admin",
        tags=["Admin"],
        dependencies=[Depends(current_admin_dependency)],
    )

    @router.get("/resources", response_model=PendingSourcePageOutput)
    def list_resources(
        identification_status: str = Query(default="pending"),
        q: str | None = Query(default=None, max_length=200),
        cursor: str | None = None,
        limit: int = Query(default=24, ge=1, le=100),
    ) -> PendingSourcePageOutput:
        try:
            page = service.list_sources(
                identification_status=identification_status,
                query=q,
                cursor=cursor,
                limit=limit,
            )
        except IdentificationProblem as error:
            raise _api_problem(error) from None
        return PendingSourcePageOutput(
            items=[PendingSourceOutput(**item.__dict__) for item in page.items],
            next_cursor=page.next_cursor,
        )

    @router.put(
        "/resources/{source_id}/identification",
        response_model=MovieSourceOutput,
    )
    def identify_resource(
        source_id: uuid.UUID,
        body: IdentificationInput,
    ) -> MovieSourceOutput:
        try:
            source = service.identify(source_id=source_id, movie_id=body.movie_id)
        except IdentificationProblem as error:
            raise _api_problem(error) from None
        return MovieSourceOutput(
            **source.__dict__,
            video_file_size_bytes=None,
            availability="available",
        )

    return router


def _pending_view(source: ResourceSource) -> PendingSourceView:
    return PendingSourceView(
        id=source.id,
        website=source.website,
        external_post_id=source.external_post_id,
        title=source.title,
        raw_number=source.raw_number,
        publish_date=source.publish_date,
        section=source.section,
        category=source.category,
        resource_size_mb=source.resource_size_mb,
        identification_status=source.identification_status,
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _api_problem(error: IdentificationProblem) -> ApiProblem:
    messages = {
        "resource_not_found": "Movie was not found",
        "source_already_identified": "Source is already identified",
        "source_not_found": "Source was not found",
        "validation_failed": "Request validation failed",
    }
    return ApiProblem(
        status_code=error.status_code,
        code=error.code,
        message=messages[error.code],
    )
