from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from alembic import command
from sakuraplayer.cloud_cache.models import Notification
from sakuraplayer.cloud_cache.notifications import NotificationWriter
from sakuraplayer.events.models import DomainEvent
from sakuraplayer.events.outbox import (
    DomainEventWriter,
    EventCursorUnavailable,
    EventLog,
)
from sakuraplayer.events.snapshot import EventSnapshotService
from sakuraplayer.shared.migration import upgrade_database

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
NOW = datetime(2026, 7, 26, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def database_url() -> str:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task013_events_{uuid.uuid4().hex}"
    admin_url = base_url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    admin_engine.dispose()
    test_url = base_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    try:
        yield test_url
    finally:
        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.execute(text(f'DROP DATABASE "{database_name}"'))
        admin_engine.dispose()


def test_postgres_event_migration_sequence_and_recovery(database_url: str) -> None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "0012_ranking_snapshots")
    engine = create_engine(database_url, hide_parameters=True)
    with engine.connect() as connection:
        assert not {
            "connection_test_result",
            "domain_event",
            "event_sequence",
            "event_stream_version",
        } & set(inspect(connection).get_table_names())
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    with engine.connect() as connection:
        assert {
            "connection_test_result",
            "domain_event",
            "event_sequence",
            "event_stream_version",
        } <= set(inspect(connection).get_table_names())
        assert connection.scalar(text("SELECT current_value FROM event_sequence")) == 0

    writer = DomainEventWriter(now=lambda: NOW)
    aggregate_id = uuid.uuid4()
    barrier = Barrier(8)

    def append_event(index: int) -> tuple[int, int, uuid.UUID]:
        barrier.wait()
        with factory.begin() as session:
            event = writer.append(
                session,
                stream="metadata",
                aggregate_id=aggregate_id,
                event_type="metadata.job.stage_changed.v1",
                payload={
                    "id": str(aggregate_id),
                    "status": "running",
                    "stage": "images",
                    "attempt_no": index + 1,
                },
            )
        return event.sequence, event.stream_version, event.event_id

    with ThreadPoolExecutor(max_workers=8) as executor:
        appended = list(executor.map(append_event, range(8)))
    assert sorted(item[0] for item in appended) == list(range(1, 9))
    assert sorted(item[1] for item in appended) == list(range(1, 9))

    notification_resource_id = uuid.uuid4()
    notification_barrier = Barrier(2)
    notification_writer = NotificationWriter(writer, now=lambda: NOW)

    def create_notification(_index: int) -> uuid.UUID:
        notification_barrier.wait()
        with factory.begin() as session:
            notification = notification_writer.create(
                session,
                notification_type="cache_ready",
                resource_id=notification_resource_id,
                error_code=None,
                dedupe_key=f"cache:{notification_resource_id}:ready",
            )
        return notification.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        notification_ids = list(executor.map(create_notification, range(2)))
    assert len(set(notification_ids)) == 1
    with factory() as session:
        assert len(list(session.scalars(select(Notification)))) == 1

    rollback_id = uuid.uuid4()
    with pytest.raises(RuntimeError, match="rollback"):
        with factory.begin() as session:
            writer.append(
                session,
                stream="metadata",
                aggregate_id=rollback_id,
                event_type="metadata.job.queued.v1",
                payload={"id": str(rollback_id), "status": "queued"},
            )
            raise RuntimeError("rollback")
    with factory.begin() as session:
        after_rollback = writer.append(
            session,
            stream="metadata",
            aggregate_id=uuid.uuid4(),
            event_type="metadata.job.queued.v1",
            payload={"id": str(uuid.uuid4()), "status": "queued"},
        )
    assert after_rollback.sequence == 10
    with factory() as session:
        assert (
            session.scalar(
                select(DomainEvent).where(DomainEvent.aggregate_id == rollback_id)
            )
            is None
        )

    event_log = EventLog(factory, now=lambda: NOW)
    snapshot = EventSnapshotService(factory, event_log).get()
    assert snapshot.snapshot_version == 10
    assert snapshot.last_event_id == after_rollback.event_id
    first_event_id = min(appended, key=lambda item: item[0])[2]
    with pytest.raises(EventCursorUnavailable):
        EventLog(factory, now=lambda: NOW + timedelta(days=31)).read_after(
            first_event_id
        )
    engine.dispose()

    command.downgrade(config, "0012_ranking_snapshots")
    engine = create_engine(database_url, hide_parameters=True)
    with engine.connect() as connection:
        assert not {
            "connection_test_result",
            "domain_event",
            "event_sequence",
            "event_stream_version",
        } & set(inspect(connection).get_table_names())
    engine.dispose()
    upgrade_database(database_url, ALEMBIC_INI)
