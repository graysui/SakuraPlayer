from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.api.settings import (
    ConnectionTestOutput,
    SettingsOutput,
    SettingsService,
)
from sakuraplayer.catalog.metadata_state import ALL_STAGES
from sakuraplayer.catalog.models import MetadataJob, MetadataStage


ComponentName = Literal[
    "api",
    "scheduler",
    "worker",
    "postgres",
    "avdb",
    "javdb",
    "dmm",
    "gfriends",
    "ai",
    "cloud115",
]
ComponentStatus = Literal[
    "healthy",
    "degraded",
    "unavailable",
    "credentials_invalid",
    "unknown",
]


class ComponentDiagnosticOutput(BaseModel):
    component: ComponentName
    status: ComponentStatus
    error_code: str | None = None
    checked_at: datetime


class QueueDiagnosticOutput(BaseModel):
    metadata_queued: int = Field(ge=0)
    metadata_running: int = Field(ge=0, le=3)
    cache_queued: int = Field(default=0, ge=0, le=10)
    cache_running: int = Field(default=0, ge=0, le=2)
    cache_ready: int = Field(default=0, ge=0)


class FailureDiagnosticOutput(BaseModel):
    task_type: Literal["metadata"]
    task_id: uuid.UUID
    stage: str | None
    error_code: str
    elapsed_ms: int | None
    attempt_no: int
    occurred_at: datetime


class DiagnosticsOutput(BaseModel):
    generated_at: datetime
    components: list[ComponentDiagnosticOutput]
    queues: QueueDiagnosticOutput
    recent_failures: list[FailureDiagnosticOutput]
    connection_tests: list[ConnectionTestOutput]


class DiagnosticsService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: SettingsService,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._now = now or (lambda: datetime.now(timezone.utc))

    def get(self) -> DiagnosticsOutput:
        current = self._utc_now()
        with self._session_factory() as session:
            session.execute(text("SELECT 1"))
            counts = {
                status: int(count)
                for status, count in session.execute(
                    select(MetadataJob.status, func.count(MetadataJob.id)).group_by(
                        MetadataJob.status
                    )
                )
            }
            failures = list(
                session.scalars(
                    select(MetadataJob)
                    .where(
                        MetadataJob.status.in_(
                            ("failed", "completed_with_warnings")
                        )
                    )
                    .order_by(
                        MetadataJob.finished_at.desc(),
                        MetadataJob.id.desc(),
                    )
                    .limit(100)
                )
            )
            stages_by_job: dict[uuid.UUID, dict[str, MetadataStage]] = {
                job.id: {} for job in failures
            }
            if stages_by_job:
                for stage in session.scalars(
                    select(MetadataStage).where(
                        MetadataStage.job_id.in_(stages_by_job),
                        MetadataStage.status.in_(("warning", "failed")),
                    )
                ):
                    stages_by_job[stage.job_id][stage.stage] = stage
        settings = self._settings.get()
        components = [
            ComponentDiagnosticOutput(
                component="api", status="healthy", checked_at=current
            ),
            ComponentDiagnosticOutput(
                component="postgres", status="healthy", checked_at=current
            ),
            ComponentDiagnosticOutput(
                component="scheduler", status="unknown", checked_at=current
            ),
            ComponentDiagnosticOutput(
                component="worker", status="unknown", checked_at=current
            ),
            ComponentDiagnosticOutput(
                component="avdb",
                status=_avdb_component_status(settings),
                error_code=_avdb_error_code(settings),
                checked_at=current,
            ),
        ]
        for name, state in {
            "javdb": settings.javdb,
            "ai": settings.ai,
            **{
                name: state
                for name, state in settings.providers.items()
                if name in {"cloud115", "dmm", "gfriends"}
            },
        }.items():
            components.append(
                ComponentDiagnosticOutput(
                    component=name,
                    status=_component_status(state.status),
                    error_code=state.last_error_code,
                    checked_at=state.last_checked_at or current,
                )
            )
        components = list({item.component: item for item in components}.values())
        return DiagnosticsOutput(
            generated_at=current,
            components=components,
            queues=QueueDiagnosticOutput(
                metadata_queued=counts.get("queued", 0),
                metadata_running=counts.get("running", 0),
            ),
            recent_failures=[
                self._failure_output(job, stages_by_job[job.id])
                for job in failures
            ],
            connection_tests=list(self._settings.connection_results().values())[:5],
        )

    def _utc_now(self) -> datetime:
        current = self._now()
        if current.tzinfo is None:
            raise ValueError("diagnostics clock must be timezone-aware")
        return current.astimezone(timezone.utc)

    @staticmethod
    def _failure_output(
        job: MetadataJob,
        stages: dict[str, MetadataStage],
    ) -> FailureDiagnosticOutput:
        stage = next(
            (stages[name] for name in reversed(ALL_STAGES) if name in stages),
            None,
        )
        return FailureDiagnosticOutput(
            task_type="metadata",
            task_id=job.id,
            stage=stage.stage if stage is not None else None,
            error_code=(
                stage.failure_code
                if stage is not None and stage.failure_code is not None
                else job.failure_code or "internal_error"
            ),
            elapsed_ms=job.elapsed_ms,
            attempt_no=job.attempt_no,
            occurred_at=(
                _as_utc(stage.finished_at)
                if stage is not None and stage.finished_at is not None
                else _as_utc(job.finished_at or job.created_at)
            ),
        )


def create_diagnostics_api(
    service: DiagnosticsService,
    *,
    current_admin_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/admin",
        tags=["Admin"],
        dependencies=[Depends(current_admin_dependency)],
    )

    @router.get("/diagnostics", response_model=DiagnosticsOutput)
    def get_diagnostics() -> DiagnosticsOutput:
        return service.get()

    return router


def _component_status(status: str) -> ComponentStatus:
    return {
        "available": "healthy",
        "credentials_invalid": "credentials_invalid",
        "unavailable": "unavailable",
        "not_configured": "unknown",
        "unknown": "unknown",
    }.get(status, "unknown")


def _avdb_component_status(settings: SettingsOutput) -> ComponentStatus:
    states = {
        settings.avdb_sync.incremental_30d.status,
        settings.avdb_sync.full_reconcile.status,
    }
    if "failed" in states:
        return "degraded"
    if states & {"running", "succeeded"}:
        return "healthy"
    return "unknown"


def _avdb_error_code(settings: SettingsOutput) -> str | None:
    for state in (
        settings.avdb_sync.incremental_30d,
        settings.avdb_sync.full_reconcile,
    ):
        if state.last_error_code is not None:
            return state.last_error_code
    return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = ["DiagnosticsOutput", "DiagnosticsService", "create_diagnostics_api"]
