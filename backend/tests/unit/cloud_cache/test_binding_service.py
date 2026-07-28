from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.cloud_cache.binding_service import (
    BindingProblem,
    BindingService,
    CredentialScope,
)
from sakuraplayer.cloud_cache.events import CacheEventPublisher
from sakuraplayer.cloud_cache.models import Cloud115Binding, Notification
from sakuraplayer.cloud_cache.notifications import NotificationWriter
from sakuraplayer.cloud_cache.ports.cloud115 import (
    Cloud115Problem,
    CloudCredentialStatus,
    CredentialProbe,
    DirectoryBreadcrumb,
    DirectoryInfo,
    QrLoginResult,
    RemoteDirectory,
)
from sakuraplayer.events.models import DomainEvent
from sakuraplayer.events.outbox import DomainEventWriter
from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.identity.models import Base, EncryptedSetting
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from tests.fakes.cloud115 import FakeCloud115

NOW = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)


def test_credential_scope_repr_is_secret_safe() -> None:
    scope = CredentialScope(
        cookies="UID=private-cookie",
        version=1,
        account_key="account-private",
        cache_root_cid="root-private",
        binding_status="active",
    )

    rendered = repr(scope)
    for secret in ("private-cookie", "account-private", "root-private"):
        assert secret not in rendered


@pytest.mark.asyncio
async def test_cache_operation_scope_refreshes_cookie_with_cas(tmp_path) -> None:
    fakes = [
        FakeCloud115(
            directories=[RemoteDirectory("root-1", "0", "SakuraPlayer-Cache")]
        ),
        FakeCloud115(credential_snapshot="UID=refreshed"),
    ]
    service, secrets, factory, engine = _service(tmp_path, fakes)
    try:
        await service.bind(QrLoginResult("account-1", "UID=old"))
        with factory() as session:
            binding = session.scalar(select(Cloud115Binding))
            assert binding is not None
            binding_id = binding.id

        async with service.cache_operation_scope(
            binding_id=binding_id,
            account_key="account-1",
            cache_root_cid="root-1",
        ) as cloud:
            assert cloud is fakes[1]

        assert secrets.get_secret("cloud115.cookie").value == b"UID=refreshed"
        assert service.get().status == "active"
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("problem", "expected_status"),
    [
        (Cloud115Problem("cloud115_credentials_expired"), "expired"),
        (Cloud115Problem("cloud115_unavailable"), "unavailable"),
    ],
)
async def test_cache_operation_scope_updates_only_matching_binding_problem(
    tmp_path,
    problem,
    expected_status,
) -> None:
    fakes = [
        FakeCloud115(
            directories=[RemoteDirectory("root-1", "0", "SakuraPlayer-Cache")]
        ),
        FakeCloud115(),
    ]
    service, _secrets, factory, engine = _service(tmp_path, fakes)
    try:
        await service.bind(QrLoginResult("account-1", "UID=old"))
        with factory() as session:
            binding = session.scalar(select(Cloud115Binding))
            assert binding is not None
            binding_id = binding.id

        with pytest.raises(Cloud115Problem) as raised:
            async with service.cache_operation_scope(
                binding_id=binding_id,
                account_key="account-1",
                cache_root_cid="root-1",
            ):
                raise problem

        assert raised.value.code == problem.code
        assert service.get().status == expected_status
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_cache_operation_scope_rejects_historic_binding_identity(
    tmp_path,
) -> None:
    fakes = [
        FakeCloud115(directories=[RemoteDirectory("root-1", "0", "SakuraPlayer-Cache")])
    ]
    service, _secrets, _factory, engine = _service(tmp_path, fakes)
    try:
        await service.bind(QrLoginResult("account-1", "UID=old"))
        with pytest.raises(Cloud115Problem) as raised:
            async with service.cache_operation_scope(
                binding_id=uuid.uuid4(),
                account_key="account-1",
                cache_root_cid="root-1",
            ):
                pytest.fail("historic binding must not open a cloud scope")
        assert raised.value.code == "cloud115_directory_not_found"
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_cache_operation_scope_maps_credential_version_drift_to_cloud_problem(
    tmp_path,
) -> None:
    fakes = [
        FakeCloud115(directories=[RemoteDirectory("root-1", "0", "SakuraPlayer-Cache")])
    ]
    service, _secrets, factory, engine = _service(tmp_path, fakes)
    try:
        await service.bind(QrLoginResult("account-1", "UID=old"))
        with factory.begin() as session:
            binding = session.scalar(select(Cloud115Binding))
            assert binding is not None
            binding_id = binding.id
            binding.credential_version += 1

        with pytest.raises(Cloud115Problem) as raised:
            async with service.cache_operation_scope(
                binding_id=binding_id,
                account_key="account-1",
                cache_root_cid="root-1",
            ):
                pytest.fail("invalid credentials must not open a cloud scope")
        assert raised.value.code == "cloud115_protocol_error"
    finally:
        engine.dispose()


def _service(tmp_path, fakes, *, active=False, event_publisher=None):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'binding.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    secrets = EncryptedSettingRepository(
        factory,
        SecretCipher(
            InMemorySecretKeyProvider(
                active_key_id="test-v1", keys={"test-v1": b"k" * 32}
            )
        ),
        now=lambda: NOW,
    )
    scripted = iter(fakes)

    @asynccontextmanager
    async def cloud_factory(_cookies: str | None):
        yield next(scripted)

    service = BindingService(
        factory,
        secrets,
        cloud_factory,
        active_cache_jobs=lambda _session: active,
        now=lambda: NOW,
        event_publisher=event_publisher,
    )
    return service, secrets, factory, engine


@pytest.mark.asyncio
async def test_expired_credential_event_and_notification_are_not_duplicated(
    tmp_path,
) -> None:
    writer = DomainEventWriter(now=lambda: NOW)
    publisher = CacheEventPublisher(
        writer,
        NotificationWriter(writer, now=lambda: NOW),
    )
    fakes = [
        FakeCloud115(
            directories=[RemoteDirectory("root-1", "0", "SakuraPlayer-Cache")]
        ),
        FakeCloud115(
            credential_probes=[CredentialProbe(CloudCredentialStatus.EXPIRED)]
        ),
        FakeCloud115(
            credential_probes=[CredentialProbe(CloudCredentialStatus.EXPIRED)]
        ),
    ]
    service, _secrets, factory, engine = _service(
        tmp_path,
        fakes,
        event_publisher=publisher,
    )
    try:
        await service.bind(QrLoginResult("account-1", "UID=old"))
        assert (await service.probe()).status == "expired"
        assert (await service.probe()).status == "expired"

        with factory() as session:
            assert [
                event.event_type
                for event in session.scalars(
                    select(DomainEvent).order_by(DomainEvent.sequence)
                )
            ] == [
                "credential.cloud115.changed.v1",
                "credential.cloud115.changed.v1",
                "notification.created.v1",
            ]
            assert len(list(session.scalars(select(Notification)))) == 1
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_bind_encrypts_cookie_and_returns_redacted_view(tmp_path) -> None:
    fake = FakeCloud115(
        directories=[RemoteDirectory("root-private", "0", "SakuraPlayer-Cache")]
    )
    service, secrets, factory, engine = _service(tmp_path, [fake])
    try:
        view = await service.bind(
            QrLoginResult("account-private", "UID=private-cookie; CID=secret")
        )
        assert view.bound is True
        assert view.status == "active"
        assert view.cache_root_ready is True
        assert "account-private" not in repr(view)
        assert "root-private" not in repr(view)
        assert "private-cookie" not in repr(view)
        assert secrets.get_secret("cloud115.cookie").value.startswith(b"UID=")
        with factory() as session:
            binding = session.scalar(select(Cloud115Binding))
            setting = session.get(EncryptedSetting, "cloud115.cookie")
            assert binding.credential_version == setting.version == 1
            assert b"private-cookie" not in setting.ciphertext
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_bind_rejects_oversized_root_cid_as_protocol_error(tmp_path) -> None:
    fake = FakeCloud115(
        directories=[RemoteDirectory("r" * 65, "0", "SakuraPlayer-Cache")]
    )
    service, secrets, _factory, engine = _service(tmp_path, [fake])
    try:
        with pytest.raises(Cloud115Problem) as raised:
            await service.bind(QrLoginResult("account-1", "UID=private-cookie"))
        assert raised.value.code == "cloud115_protocol_error"
        assert secrets.get_secret("cloud115.cookie") is None
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_binding_version_mismatch_uses_public_state_conflict(tmp_path) -> None:
    fake = FakeCloud115(
        directories=[RemoteDirectory("root-1", "0", "SakuraPlayer-Cache")]
    )
    service, _secrets, factory, engine = _service(tmp_path, [fake])
    try:
        await service.bind(QrLoginResult("account-1", "UID=private-cookie"))
        with factory.begin() as session:
            binding = session.scalar(select(Cloud115Binding))
            assert binding is not None
            binding.credential_version += 1

        with pytest.raises(BindingProblem) as raised:
            await service.probe()
        assert raised.value.code == "state_conflict"
        assert raised.value.status_code == 409
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_same_account_rebind_increments_atomic_version(tmp_path) -> None:
    roots = [
        FakeCloud115(
            directories=[RemoteDirectory("root-1", "0", "SakuraPlayer-Cache")]
        ),
        FakeCloud115(
            directories=[RemoteDirectory("root-1", "0", "SakuraPlayer-Cache")]
        ),
    ]
    service, secrets, factory, engine = _service(tmp_path, roots)
    try:
        await service.bind(QrLoginResult("account-1", "UID=old"))
        await service.bind(QrLoginResult("account-1", "UID=new"))
        assert secrets.get_secret("cloud115.cookie").value == b"UID=new"
        with factory() as session:
            binding = session.scalar(select(Cloud115Binding))
            assert binding.credential_version == 2
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_different_account_cannot_replace_binding(tmp_path) -> None:
    fake = FakeCloud115(
        directories=[RemoteDirectory("root-1", "0", "SakuraPlayer-Cache")]
    )
    service, secrets, _factory, engine = _service(tmp_path, [fake])
    try:
        await service.bind(QrLoginResult("account-1", "UID=old"))
        with pytest.raises(BindingProblem) as conflict:
            await service.bind(QrLoginResult("account-2", "UID=new"))
        assert conflict.value.code == "cloud115_binding_exists"
        assert secrets.get_secret("cloud115.cookie").value == b"UID=old"
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_probe_marks_expired_but_unavailable_is_distinct(tmp_path) -> None:
    fakes = [
        FakeCloud115(
            directories=[RemoteDirectory("root-1", "0", "SakuraPlayer-Cache")]
        ),
        FakeCloud115(
            credential_probes=[CredentialProbe(CloudCredentialStatus.UNAVAILABLE)]
        ),
        FakeCloud115(
            credential_probes=[CredentialProbe(CloudCredentialStatus.EXPIRED)]
        ),
    ]
    service, _secrets, _factory, engine = _service(tmp_path, fakes)
    try:
        await service.bind(QrLoginResult("account-1", "UID=old"))
        last_verified = service.get().last_verified_at
        unavailable = await service.probe()
        assert unavailable.status == "unavailable"
        assert unavailable.last_verified_at == last_verified
        expired = await service.probe()
        assert expired.status == "expired"
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_old_probe_snapshot_cannot_overwrite_rebind(tmp_path) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class DelayedProbeFake(FakeCloud115):
        async def probe_credentials(self) -> CredentialProbe:
            started.set()
            await release.wait()
            return CredentialProbe(CloudCredentialStatus.UNAVAILABLE, "UID=old-refresh")

    fakes = [
        FakeCloud115(
            directories=[RemoteDirectory("root-1", "0", "SakuraPlayer-Cache")]
        ),
        DelayedProbeFake(),
        FakeCloud115(
            directories=[RemoteDirectory("root-1", "0", "SakuraPlayer-Cache")]
        ),
    ]
    service, secrets, factory, engine = _service(tmp_path, fakes)
    try:
        await service.bind(QrLoginResult("account-1", "UID=old"))
        old_probe = asyncio.create_task(service.probe())
        await started.wait()
        await service.bind(QrLoginResult("account-1", "UID=new-scan"))
        release.set()
        result = await old_probe

        assert result.status == "active"
        assert secrets.get_secret("cloud115.cookie").value == b"UID=new-scan"
        with factory() as session:
            binding = session.scalar(select(Cloud115Binding))
            assert binding.credential_version == 2
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_probe_marks_moved_root_detached_without_scanning(tmp_path) -> None:
    moved = DirectoryInfo(
        cid="root-1",
        parent_cid="other-parent",
        name="SakuraPlayer-Cache",
        path=(DirectoryBreadcrumb("other-parent", "Other"),),
    )
    fakes = [
        FakeCloud115(
            directories=[RemoteDirectory("root-1", "0", "SakuraPlayer-Cache")]
        ),
        FakeCloud115(
            credential_probes=[CredentialProbe(CloudCredentialStatus.ALIVE)],
            directory_infos=[moved],
        ),
    ]
    service, _secrets, _factory, engine = _service(tmp_path, fakes)
    try:
        await service.bind(QrLoginResult("account-1", "UID=old"))
        detached = await service.probe()
        assert detached.status == "detached"
        assert detached.cache_root_ready is False
        assert [call.operation for call in fakes[1].calls] == [
            "probe_credentials",
            "directory_info",
            "credential_snapshot",
        ]
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_unavailable_probe_does_not_restore_detached_root(tmp_path) -> None:
    moved = DirectoryInfo(
        cid="root-1",
        parent_cid="other-parent",
        name="SakuraPlayer-Cache",
        path=(DirectoryBreadcrumb("other-parent", "Other"),),
    )
    fakes = [
        FakeCloud115(
            directories=[RemoteDirectory("root-1", "0", "SakuraPlayer-Cache")]
        ),
        FakeCloud115(
            credential_probes=[CredentialProbe(CloudCredentialStatus.ALIVE)],
            directory_infos=[moved],
        ),
        FakeCloud115(
            credential_probes=[CredentialProbe(CloudCredentialStatus.UNAVAILABLE)]
        ),
    ]
    service, _secrets, _factory, engine = _service(tmp_path, fakes)
    try:
        await service.bind(QrLoginResult("account-1", "UID=old"))
        assert (await service.probe()).status == "detached"
        unavailable = await service.probe()
        assert unavailable.status == "detached"
        assert unavailable.cache_root_ready is False
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_remove_is_blocked_by_active_cache_job_guard(tmp_path) -> None:
    fake = FakeCloud115(
        directories=[RemoteDirectory("root-1", "0", "SakuraPlayer-Cache")]
    )
    service, secrets, _factory, engine = _service(tmp_path, [fake], active=True)
    try:
        await service.bind(QrLoginResult("account-1", "UID=old"))
        with pytest.raises(BindingProblem) as active:
            service.remove()
        assert active.value.code == "cloud115_rebind_has_active_jobs"
        assert secrets.get_secret("cloud115.cookie") is not None
    finally:
        engine.dispose()
