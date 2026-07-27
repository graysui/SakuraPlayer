from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.cloud_cache.models import Cloud115Binding
from sakuraplayer.cloud_cache.ports.cloud115 import (
    Cloud115Port,
    Cloud115Problem,
    CloudCredentialStatus,
    QrLoginResult,
)
from sakuraplayer.identity.models import EncryptedSetting
from sakuraplayer.identity.secrets import (
    ConcurrentSettingUpdate,
    EncryptedSettingRepository,
)

COOKIE_SETTING_KEY = "cloud115.cookie"
CACHE_ROOT_PARENT_CID = "0"
CACHE_ROOT_NAME = "SakuraPlayer-Cache"
_BINDING_LOCK_KEY = 115_102

Cloud115ScopeFactory = Callable[[str | None], AbstractAsyncContextManager[Cloud115Port]]
ActiveCacheJobGuard = Callable[[Session], bool]


class BindingProblem(RuntimeError):
    def __init__(self, code: str, status_code: int) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class BindingView:
    bound: bool
    status: str
    display_name: str | None = None
    cache_root_ready: bool = False
    last_verified_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CredentialScope:
    cookies: str = field(repr=False)
    version: int
    account_key: str = field(repr=False)
    cache_root_cid: str = field(repr=False)
    binding_status: str


class BindingService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        secrets: EncryptedSettingRepository,
        cloud_factory: Cloud115ScopeFactory,
        *,
        active_cache_jobs: ActiveCacheJobGuard | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._secrets = secrets
        self._cloud_factory = cloud_factory
        self._active_cache_jobs = active_cache_jobs or (lambda _session: False)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._bind_lock = asyncio.Lock()

    def get(self) -> BindingView:
        with self._session_factory() as session:
            binding = self._binding(session)
            return self._view(binding)

    async def bind(self, result: QrLoginResult) -> BindingView:
        self._validate_login_result(result)
        async with self._bind_lock:
            with self._session_factory() as session:
                existing = self._binding(session)
                if existing is not None and existing.account_key != result.account_key:
                    raise BindingProblem("cloud115_binding_exists", 409)
            async with self._cloud_factory(result.cookie_snapshot) as cloud:
                root = await cloud.find_or_create_directory(
                    CACHE_ROOT_PARENT_CID, CACHE_ROOT_NAME
                )
            if (
                root.parent_cid != CACHE_ROOT_PARENT_CID
                or root.name != CACHE_ROOT_NAME
                or not root.cid
                or len(root.cid) > 64
            ):
                raise Cloud115Problem("cloud115_protocol_error")
            with self._session_factory() as session, session.begin():
                self._lock(session)
                binding = self._binding(session, with_for_update=True)
                if binding is not None and binding.account_key != result.account_key:
                    raise BindingProblem("cloud115_binding_exists", 409)
                setting = session.get(EncryptedSetting, COOKIE_SETTING_KEY)
                expected_version = (
                    binding.credential_version
                    if binding is not None
                    else setting.version
                    if setting is not None
                    else 0
                )
                try:
                    saved = self._secrets.compare_and_set_secret_in_session(
                        session,
                        COOKIE_SETTING_KEY,
                        expected_version=expected_version,
                        value=result.cookie_snapshot.encode("utf-8"),
                    )
                except ConcurrentSettingUpdate:
                    raise BindingProblem("state_conflict", 409) from None
                current = self._now()
                if binding is None:
                    binding = Cloud115Binding(
                        id=uuid.uuid4(),
                        singleton_key=True,
                        account_key=result.account_key,
                        display_name=None,
                        cookie_setting_key=COOKIE_SETTING_KEY,
                        login_app="alipaymini",
                        cache_root_cid=root.cid,
                        status="active",
                        credential_version=saved.version,
                        last_verified_at=current,
                        created_at=current,
                        updated_at=current,
                    )
                    session.add(binding)
                else:
                    binding.cache_root_cid = root.cid
                    binding.status = "active"
                    binding.credential_version = saved.version
                    binding.last_verified_at = current
                    binding.updated_at = current
                session.flush()
                return self._view(binding)

    async def probe(self) -> BindingView:
        scope = self._credential_scope()
        if scope is None:
            return BindingView(bound=False, status="unbound")
        async with self._cloud_factory(scope.cookies) as cloud:
            result = await cloud.probe_credentials()
            root_detached = False
            if result.status == CloudCredentialStatus.ALIVE:
                try:
                    info = await cloud.directory_info(scope.cache_root_cid)
                    root_detached = (
                        info.parent_cid != CACHE_ROOT_PARENT_CID
                        or info.name != CACHE_ROOT_NAME
                    )
                except Cloud115Problem as error:
                    if error.code != "cloud115_directory_not_found":
                        raise
                    root_detached = True
            snapshot = result.cookie_snapshot or cloud.credential_snapshot()
        status = {
            CloudCredentialStatus.ALIVE: "active",
            CloudCredentialStatus.EXPIRED: "expired",
            CloudCredentialStatus.UNAVAILABLE: "unavailable",
        }[result.status]
        if root_detached:
            status = "detached"
        elif (
            result.status == CloudCredentialStatus.UNAVAILABLE
            and scope.binding_status == "detached"
        ):
            status = "detached"
        return self._finish_scope(
            scope,
            status=status,
            snapshot=snapshot,
            verified=result.status != CloudCredentialStatus.UNAVAILABLE,
        )

    async def validate_root(self) -> BindingView:
        scope = self._credential_scope()
        if scope is None:
            return BindingView(bound=False, status="unbound")
        status = "active"
        verified = True
        try:
            async with self._cloud_factory(scope.cookies) as cloud:
                info = await cloud.directory_info(scope.cache_root_cid)
                snapshot = cloud.credential_snapshot()
            if info.parent_cid != CACHE_ROOT_PARENT_CID or info.name != CACHE_ROOT_NAME:
                status = "detached"
        except Cloud115Problem as error:
            if error.code != "cloud115_directory_not_found":
                raise
            status = "detached"
            snapshot = None
        return self._finish_scope(
            scope, status=status, snapshot=snapshot, verified=verified
        )

    @asynccontextmanager
    async def cache_operation_scope(
        self,
        *,
        binding_id: uuid.UUID,
        account_key: str,
        cache_root_cid: str,
    ) -> AsyncIterator[Cloud115Port]:
        scope = self._credential_scope(
            binding_id=binding_id,
            account_key=account_key,
            cache_root_cid=cache_root_cid,
        )
        assert scope is not None
        cloud: Cloud115Port | None = None
        try:
            async with self._cloud_factory(scope.cookies) as cloud:
                yield cloud
        except Cloud115Problem as error:
            snapshot = cloud.credential_snapshot() if cloud is not None else None
            if error.code == "cloud115_credentials_expired":
                status = "expired"
                verified = True
            elif error.code in {"cloud115_unavailable", "cloud115_rate_limited"}:
                status = "unavailable"
                verified = False
            else:
                status = "active"
                verified = True
            self._finish_scope(
                scope,
                status=status,
                snapshot=snapshot,
                verified=verified,
            )
            raise
        else:
            assert cloud is not None
            self._finish_scope(
                scope,
                status="active",
                snapshot=cloud.credential_snapshot(),
                verified=True,
            )

    def remove(self) -> None:
        with self._session_factory() as session, session.begin():
            self._lock(session)
            if self._active_cache_jobs(session):
                raise BindingProblem("cloud115_rebind_has_active_jobs", 409)
            binding = self._binding(session, with_for_update=True)
            if binding is None:
                return
            self._secrets.delete_secret_in_session(
                session,
                COOKIE_SETTING_KEY,
                expected_version=binding.credential_version,
            )
            session.delete(binding)

    def _credential_scope(
        self,
        *,
        binding_id: uuid.UUID | None = None,
        account_key: str | None = None,
        cache_root_cid: str | None = None,
    ) -> CredentialScope | None:
        with self._session_factory() as session:
            binding = self._binding(session)
            if binding is None:
                if binding_id is not None:
                    raise Cloud115Problem("cloud115_directory_not_found")
                return None
            if binding_id is not None and (
                binding.id != binding_id
                or binding.account_key != account_key
                or binding.cache_root_cid != cache_root_cid
            ):
                raise Cloud115Problem("cloud115_directory_not_found")
            if binding_id is not None:
                if binding.status == "expired":
                    raise Cloud115Problem("cloud115_credentials_expired")
                if binding.status == "detached":
                    raise Cloud115Problem("cloud115_directory_not_found")
                if binding.status not in {"active", "unavailable"}:
                    raise Cloud115Problem("cloud115_protocol_error")
            setting = self._secrets.get_secret_in_session(session, COOKIE_SETTING_KEY)
            if setting is None or setting.version != binding.credential_version:
                if binding_id is not None:
                    raise Cloud115Problem("cloud115_protocol_error")
                raise BindingProblem("state_conflict", 409)
            try:
                cookies = setting.value.decode("utf-8")
            except UnicodeDecodeError:
                if binding_id is not None:
                    raise Cloud115Problem("cloud115_protocol_error") from None
                raise BindingProblem("cloud115_protocol_error", 502) from None
            return CredentialScope(
                cookies=cookies,
                version=setting.version,
                account_key=binding.account_key,
                cache_root_cid=binding.cache_root_cid,
                binding_status=binding.status,
            )

    def _finish_scope(
        self,
        scope: CredentialScope,
        *,
        status: str,
        snapshot: str | None,
        verified: bool,
    ) -> BindingView:
        with self._session_factory() as session, session.begin():
            binding = self._binding(session, with_for_update=True)
            if (
                binding is None
                or binding.account_key != scope.account_key
                or binding.credential_version != scope.version
            ):
                return self._view(binding)
            if snapshot is not None and snapshot != scope.cookies:
                try:
                    saved = self._secrets.compare_and_set_secret_in_session(
                        session,
                        COOKIE_SETTING_KEY,
                        expected_version=scope.version,
                        value=snapshot.encode("utf-8"),
                    )
                except ConcurrentSettingUpdate:
                    return self._view(binding)
                binding.credential_version = saved.version
            binding.status = status
            current = self._now()
            if verified:
                binding.last_verified_at = current
            binding.updated_at = current
            session.flush()
            return self._view(binding)

    @staticmethod
    def _binding(
        session: Session, *, with_for_update: bool = False
    ) -> Cloud115Binding | None:
        statement = select(Cloud115Binding).where(
            Cloud115Binding.singleton_key.is_(True)
        )
        if with_for_update:
            statement = statement.with_for_update()
        return session.scalar(statement)

    @staticmethod
    def _lock(session: Session) -> None:
        if session.bind is not None and session.bind.dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": _BINDING_LOCK_KEY},
            )

    @staticmethod
    def _validate_login_result(result: QrLoginResult) -> None:
        if (
            not result.account_key
            or len(result.account_key) > 128
            or not result.cookie_snapshot
            or len(result.cookie_snapshot.encode("utf-8")) > 65_536
        ):
            raise BindingProblem("cloud115_protocol_error", 502)

    @staticmethod
    def _view(binding: Cloud115Binding | None) -> BindingView:
        if binding is None:
            return BindingView(bound=False, status="unbound")
        return BindingView(
            bound=True,
            status=binding.status,
            display_name=binding.display_name,
            cache_root_ready=binding.status != "detached",
            last_verified_at=binding.last_verified_at,
        )


__all__ = [
    "ActiveCacheJobGuard",
    "BindingProblem",
    "BindingService",
    "BindingView",
    "Cloud115ScopeFactory",
    "CredentialScope",
]
