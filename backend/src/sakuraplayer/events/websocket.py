from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

from sakuraplayer.catalog.metadata_api import MetadataJobOutput
from sakuraplayer.events.models import DomainEvent
from sakuraplayer.events.outbox import EventCursorUnavailable, EventLog
from sakuraplayer.events.snapshot import EventSnapshotService


class QueueSnapshotOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    metadata_queued: int
    metadata_running: int
    cache_queued: int
    cache_running: int
    cache_ready: int


class EventSnapshotOutput(BaseModel):
    snapshot_version: int
    last_event_id: uuid.UUID | None
    queues: QueueSnapshotOutput
    cache_jobs: list[dict[str, object]]
    metadata_jobs: list[MetadataJobOutput]
    cloud115_binding: dict[str, object]
    notifications: list[dict[str, object]]


def create_events_api(
    snapshot_service: EventSnapshotService,
    event_log: EventLog,
    *,
    current_admin_dependency: Callable[..., object],
    websocket_admin_dependency: Callable[..., object],
    poll_interval_seconds: float = 0.5,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/events", tags=["Events"])

    @router.get(
        "/snapshot",
        response_model=EventSnapshotOutput,
        dependencies=[Depends(current_admin_dependency)],
    )
    def event_snapshot() -> EventSnapshotOutput:
        view = snapshot_service.get()
        return EventSnapshotOutput(
            snapshot_version=view.snapshot_version,
            last_event_id=view.last_event_id,
            queues=QueueSnapshotOutput.model_validate(view.queues),
            cache_jobs=view.cache_jobs,
            metadata_jobs=[
                MetadataJobOutput(**item.__dict__) for item in view.metadata_jobs
            ],
            cloud115_binding=view.cloud115_binding,
            notifications=view.notifications,
        )

    @router.websocket("/ws")
    async def events_websocket(
        websocket: WebSocket,
        after_event_id: uuid.UUID | None = Query(default=None),
        _admin: object = Depends(websocket_admin_dependency),
    ) -> None:
        del _admin
        await websocket.accept()
        cursor = after_event_id
        try:
            cursor = await _send_available(websocket, event_log, cursor)
        except EventCursorUnavailable:
            await websocket.close(code=4409)
            return
        try:
            while True:
                try:
                    message = await asyncio.wait_for(
                        websocket.receive_json(),
                        timeout=poll_interval_seconds,
                    )
                except asyncio.TimeoutError:
                    try:
                        cursor = await _send_available(websocket, event_log, cursor)
                    except EventCursorUnavailable:
                        await websocket.close(code=4409)
                        return
                    continue
                if isinstance(message, dict) and message.get("type") == "ping":
                    await websocket.send_json(
                        {
                            "type": "pong",
                            "sent_at": message.get("sent_at"),
                            "server_at": datetime.now(timezone.utc)
                            .isoformat()
                            .replace("+00:00", "Z"),
                        }
                    )
        except WebSocketDisconnect:
            return

    return router


async def _send_available(
    websocket: WebSocket,
    event_log: EventLog,
    cursor: uuid.UUID | None,
) -> uuid.UUID | None:
    while True:
        events = await run_in_threadpool(event_log.read_after, cursor, limit=100)
        for event in events:
            await websocket.send_json(_event_payload(event))
            cursor = event.event_id
        if len(events) < 100:
            return cursor


def _event_payload(event: DomainEvent) -> dict[str, object]:
    return {
        "version": 1,
        "event_id": str(event.event_id),
        "sequence": event.sequence,
        "stream": event.stream,
        "stream_version": event.stream_version,
        "type": event.event_type,
        "occurred_at": _utc_iso(event.occurred_at),
        "resource": event.payload,
    }


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = ["EventSnapshotOutput", "QueueSnapshotOutput", "create_events_api"]
