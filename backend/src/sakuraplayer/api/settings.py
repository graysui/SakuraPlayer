from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic
from typing import Literal, Protocol

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.catalog.models import ActorMappingSnapshot, GfriendsSnapshot
from sakuraplayer.catalog.providers.javdb import (
    EncryptedJavdbCredentialStore,
    JavdbCredentials,
    MetadataProviderProblem,
)
from sakuraplayer.catalog.translation.config import (
    AiConfiguration,
    EncryptedAiConfigurationStore,
    TranslationConfigurationError,
)
from sakuraplayer.identity.api import ApiProblem
from sakuraplayer.identity.models import ConnectionTestResult
from sakuraplayer.identity.secrets import (
    ConcurrentSettingUpdate,
    EncryptedSettingRepository,
)
from sakuraplayer.resources.models import AvdbSyncRequest, AvdbSyncRun
from sakuraplayer.shared.redaction import stable_error_code


ConnectionTarget = Literal["cloud115", "javdb", "dmm", "gfriends", "ai"]
ConnectionStatus = Literal[
    "available", "unavailable", "credentials_invalid", "not_configured"
]
ProviderStatus = Literal[
    "available",
    "unavailable",
    "credentials_invalid",
    "not_configured",
    "unknown",
]
SyncStatus = Literal["never", "running", "succeeded", "failed"]


class SettingClearInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action: Literal["clear"]
    expected_version: int = Field(ge=1)


class JavdbReplaceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action: Literal["replace"]
    expected_version: int = Field(ge=0)
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


class AiReplaceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action: Literal["replace"]
    expected_version: int = Field(ge=0)
    base_url: str = Field(min_length=1, max_length=2048)
    api_key: str = Field(min_length=1, max_length=8192)
    model: str = Field(min_length=1, max_length=255)
    timeout_seconds: int = Field(ge=1, le=600)


class SettingsPatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    cache_ttl_hours: int | None = Field(default=None, ge=1, le=168)
    javdb: JavdbReplaceInput | SettingClearInput | None = None
    ai: AiReplaceInput | SettingClearInput | None = None

    @model_validator(mode="after")
    def require_non_null_command(self) -> "SettingsPatchInput":
        if not self.model_fields_set:
            raise ValueError("settings patch must not be empty")
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("settings commands cannot be null")
        return self


class ProviderStateOutput(BaseModel):
    configured: bool
    status: ProviderStatus
    last_checked_at: datetime | None = None
    last_error_code: str | None = None


class JavdbSettingsOutput(ProviderStateOutput):
    username: str | None
    password_configured: bool
    version: int


class AiSettingsOutput(ProviderStateOutput):
    base_url: str | None
    model: str | None
    timeout_seconds: int | None
    api_key_configured: bool
    version: int


class SyncRunStateOutput(BaseModel):
    status: SyncStatus
    release_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_successful_at: datetime | None = None
    next_scheduled_at: datetime | None = None
    last_error_code: str | None = None


class AvdbSyncStatusOutput(BaseModel):
    incremental_30d: SyncRunStateOutput
    full_reconcile: SyncRunStateOutput


class SettingsOutput(BaseModel):
    cache_ttl_hours: int
    ready_cache_limit: Literal[20] = 20
    metadata_concurrency: Literal[3] = 3
    metadata_timeout_seconds: Literal[600] = 600
    javdb: JavdbSettingsOutput
    ai: AiSettingsOutput
    providers: dict[str, ProviderStateOutput]
    avdb_sync: AvdbSyncStatusOutput


class ConnectionTestInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    target: ConnectionTarget


class ConnectionTestOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    target: ConnectionTarget
    status: ConnectionStatus
    error_code: str | None
    elapsed_ms: int
    checked_at: datetime


@dataclass(frozen=True)
class ProbeResult:
    status: ConnectionStatus
    error_code: str | None = None


class ConnectionProbe(Protocol):
    def __call__(self) -> ProbeResult: ...


class SettingsService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        repository: EncryptedSettingRepository,
        javdb_store: EncryptedJavdbCredentialStore,
        ai_store: EncryptedAiConfigurationStore,
        *,
        probes: Mapping[str, ConnectionProbe] | None = None,
        now: Callable[[], datetime] | None = None,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._repository = repository
        self._javdb_store = javdb_store
        self._ai_store = ai_store
        self._probes = dict(probes or {})
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._monotonic = monotonic_clock or monotonic

    def get(self) -> SettingsOutput:
        connection_results = self.connection_results()
        javdb = self._javdb_settings(connection_results.get("javdb"))
        ai = self._ai_settings(connection_results.get("ai"))
        with self._session_factory() as session:
            gfriends_ready = (
                session.scalar(
                    select(GfriendsSnapshot.id)
                    .where(GfriendsSnapshot.status == "current")
                    .limit(1)
                )
                is not None
            )
            actor_mapping_ready = (
                session.scalar(
                    select(ActorMappingSnapshot.id)
                    .where(ActorMappingSnapshot.status == "current")
                    .limit(1)
                )
                is not None
            )
            sync_status = AvdbSyncStatusOutput(
                incremental_30d=self._sync_state(session, "incremental_30d"),
                full_reconcile=self._sync_state(session, "full_reconcile"),
            )
        ttl = self._repository.get_public("cache.ttl_hours")
        ttl_hours = ttl.value if ttl is not None else 24
        if not isinstance(ttl_hours, int) or not 1 <= ttl_hours <= 168:
            ttl_hours = 24
        return SettingsOutput(
            cache_ttl_hours=ttl_hours,
            javdb=javdb,
            ai=ai,
            providers={
                "cloud115": self._provider_state(
                    configured=False,
                    result=connection_results.get("cloud115"),
                ),
                "dmm": self._provider_state(
                    configured=True,
                    result=connection_results.get("dmm"),
                ),
                "gfriends": self._provider_state(
                    configured=gfriends_ready,
                    result=connection_results.get("gfriends"),
                ),
                "actor_mapping": ProviderStateOutput(
                    configured=actor_mapping_ready,
                    status="available" if actor_mapping_ready else "unknown",
                ),
            },
            avdb_sync=sync_status,
        )

    def patch(self, command: SettingsPatchInput) -> SettingsOutput:
        if "cache_ttl_hours" in command.model_fields_set:
            assert command.cache_ttl_hours is not None
            self._repository.set_public("cache.ttl_hours", command.cache_ttl_hours)
        if "javdb" in command.model_fields_set:
            assert command.javdb is not None
            if isinstance(command.javdb, SettingClearInput):
                self._javdb_store.clear(
                    expected_version=command.javdb.expected_version
                )
            else:
                self._javdb_store.save(
                    JavdbCredentials(command.javdb.username, command.javdb.password),
                    expected_version=command.javdb.expected_version,
                )
            self._invalidate_connection_result("javdb")
        if "ai" in command.model_fields_set:
            assert command.ai is not None
            if isinstance(command.ai, SettingClearInput):
                self._ai_store.clear(expected_version=command.ai.expected_version)
            else:
                self._ai_store.save(
                    AiConfiguration(
                        base_url=command.ai.base_url,
                        api_key=command.ai.api_key,
                        model=command.ai.model,
                        timeout_seconds=command.ai.timeout_seconds,
                    ),
                    expected_version=command.ai.expected_version,
                )
            self._invalidate_connection_result("ai")
        return self.get()

    def test_connection(self, target: ConnectionTarget) -> ConnectionTestOutput:
        current = self._utc_now()
        started = self._monotonic()
        if target in {"cloud115", "javdb", "ai"} and not self._is_configured(target):
            result = ProbeResult("not_configured")
        else:
            probe = self._probes.get(target)
            if probe is None:
                result = ProbeResult("unavailable", "service_unavailable")
            else:
                try:
                    result = probe()
                except TimeoutError:
                    result = ProbeResult("unavailable", "service_unavailable")
                except Exception as error:
                    code = stable_error_code(getattr(error, "code", None))
                    result = ProbeResult(
                        "credentials_invalid"
                        if code in {
                            "javdb_credentials_invalid",
                            "cloud115_credentials_expired",
                        }
                        else "unavailable",
                        code,
                    )
        elapsed_ms = max(0, int((self._monotonic() - started) * 1000))
        output = ConnectionTestOutput(
            target=target,
            status=result.status,
            error_code=result.error_code,
            elapsed_ms=elapsed_ms,
            checked_at=current,
        )
        with self._session_factory.begin() as session:
            row = session.get(ConnectionTestResult, target, with_for_update=True)
            if row is None:
                row = ConnectionTestResult(target=target)
                session.add(row)
            row.status = output.status
            row.error_code = output.error_code
            row.elapsed_ms = output.elapsed_ms
            row.checked_at = output.checked_at
        return output

    def connection_results(self) -> dict[str, ConnectionTestOutput]:
        with self._session_factory() as session:
            return {
                row.target: ConnectionTestOutput(
                    target=row.target,
                    status=row.status,
                    error_code=row.error_code,
                    elapsed_ms=row.elapsed_ms,
                    checked_at=_as_utc(row.checked_at),
                )
                for row in session.scalars(select(ConnectionTestResult))
            }

    def _invalidate_connection_result(self, target: str) -> None:
        with self._session_factory.begin() as session:
            row = session.get(ConnectionTestResult, target, with_for_update=True)
            if row is not None:
                session.delete(row)

    def _javdb_settings(
        self,
        result: ConnectionTestOutput | None,
    ) -> JavdbSettingsOutput:
        status = self._repository.get_status("javdb.credentials")
        try:
            snapshot = self._javdb_store.load_snapshot()
        except MetadataProviderProblem:
            return JavdbSettingsOutput(
                configured=status is not None and status.configured,
                status="credentials_invalid",
                last_error_code="javdb_credentials_invalid",
                username=None,
                password_configured=status is not None and status.configured,
                version=status.version if status is not None else 0,
            )
        return JavdbSettingsOutput(
            configured=snapshot is not None,
            status=result.status if result is not None else "unknown",
            last_checked_at=result.checked_at if result is not None else None,
            last_error_code=result.error_code if result is not None else None,
            username=(snapshot.credentials.username if snapshot is not None else None),
            password_configured=snapshot is not None,
            version=(
                snapshot.version
                if snapshot is not None
                else status.version if status is not None else 0
            ),
        )

    def _ai_settings(
        self,
        result: ConnectionTestOutput | None,
    ) -> AiSettingsOutput:
        status = self._repository.get_status("ai.configuration")
        try:
            snapshot = self._ai_store.load()
        except TranslationConfigurationError:
            return AiSettingsOutput(
                configured=status is not None and status.configured,
                status="unavailable",
                last_error_code="translation_not_configured",
                base_url=None,
                model=None,
                timeout_seconds=None,
                api_key_configured=status is not None and status.configured,
                version=status.version if status is not None else 0,
            )
        return AiSettingsOutput(
            configured=snapshot is not None,
            status=result.status if result is not None else "unknown",
            last_checked_at=result.checked_at if result is not None else None,
            last_error_code=result.error_code if result is not None else None,
            base_url=snapshot.base_url if snapshot is not None else None,
            model=snapshot.model if snapshot is not None else None,
            timeout_seconds=snapshot.timeout_seconds if snapshot is not None else None,
            api_key_configured=snapshot is not None,
            version=(
                snapshot.version
                if snapshot is not None
                else status.version if status is not None else 0
            ),
        )

    def _is_configured(self, target: str) -> bool:
        if target == "javdb":
            status = self._repository.get_status("javdb.credentials")
            return status is not None and status.configured
        if target == "ai":
            status = self._repository.get_status("ai.configuration")
            return status is not None and status.configured
        return False

    @staticmethod
    def _provider_state(
        *,
        configured: bool,
        result: ConnectionTestOutput | None,
    ) -> ProviderStateOutput:
        return ProviderStateOutput(
            configured=configured,
            status=result.status if result is not None else "unknown",
            last_checked_at=result.checked_at if result is not None else None,
            last_error_code=result.error_code if result is not None else None,
        )

    @staticmethod
    def _sync_state(session: Session, mode: str) -> SyncRunStateOutput:
        latest = session.scalar(
            select(AvdbSyncRun)
            .where(AvdbSyncRun.mode == mode)
            .order_by(AvdbSyncRun.started_at.desc(), AvdbSyncRun.id.desc())
            .limit(1)
        )
        last_success = session.scalar(
            select(AvdbSyncRun.completed_at)
            .where(AvdbSyncRun.mode == mode, AvdbSyncRun.status == "completed")
            .order_by(AvdbSyncRun.completed_at.desc())
            .limit(1)
        )
        next_request = session.scalar(
            select(AvdbSyncRequest.scheduled_for)
            .where(AvdbSyncRequest.mode == mode, AvdbSyncRequest.status == "queued")
            .order_by(AvdbSyncRequest.scheduled_for)
            .limit(1)
        )
        if latest is None:
            return SyncRunStateOutput(
                status="never",
                last_successful_at=_as_utc_optional(last_success),
                next_scheduled_at=_as_utc_optional(next_request),
            )
        return SyncRunStateOutput(
            status={
                "completed": "succeeded",
                "running": "running",
                "failed": "failed",
            }[latest.status],
            release_id=latest.release_id,
            started_at=_as_utc(latest.started_at),
            completed_at=_as_utc_optional(latest.completed_at),
            last_successful_at=_as_utc_optional(last_success),
            next_scheduled_at=_as_utc_optional(next_request),
            last_error_code=latest.failure_code,
        )

    def _utc_now(self) -> datetime:
        current = self._now()
        if current.tzinfo is None:
            raise ValueError("settings clock must be timezone-aware")
        return current.astimezone(timezone.utc)


def create_settings_api(
    service: SettingsService,
    *,
    current_admin_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/settings",
        tags=["Admin"],
        dependencies=[Depends(current_admin_dependency)],
    )

    @router.get("", response_model=SettingsOutput)
    def get_settings() -> SettingsOutput:
        return service.get()

    @router.patch("", response_model=SettingsOutput)
    def update_settings(body: SettingsPatchInput) -> SettingsOutput:
        try:
            return service.patch(body)
        except ConcurrentSettingUpdate:
            raise ApiProblem(
                status_code=409,
                code="state_conflict",
                message="Settings changed concurrently",
            ) from None
        except (ValueError, MetadataProviderProblem, TranslationConfigurationError):
            raise ApiProblem(
                status_code=422,
                code="validation_failed",
                message="Settings are invalid",
            ) from None

    @router.post("/connection-tests", response_model=ConnectionTestOutput)
    def test_connection(body: ConnectionTestInput) -> ConnectionTestOutput:
        return service.test_connection(body.target)

    return router


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _as_utc_optional(value: datetime | None) -> datetime | None:
    return _as_utc(value) if value is not None else None


__all__ = [
    "AiReplaceInput",
    "ConnectionProbe",
    "ConnectionTestInput",
    "ConnectionTestOutput",
    "ProbeResult",
    "SettingsOutput",
    "SettingsPatchInput",
    "SettingsService",
    "create_settings_api",
]
