from pathlib import Path

from sakuraplayer.events import models as event_models
from sakuraplayer.identity.models import Base


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_event_models_are_registered() -> None:
    assert event_models.DomainEvent.__tablename__ == "domain_event"
    assert event_models.EventSequence.__tablename__ == "event_sequence"
    assert event_models.EventStreamVersion.__tablename__ == "event_stream_version"
    assert {
        "domain_event",
        "event_sequence",
        "event_stream_version",
        "connection_test_result",
    } <= set(Base.metadata.tables)


def test_task_013_migration_owns_event_schema() -> None:
    migration = (
        BACKEND_ROOT
        / "alembic"
        / "versions"
        / "0013_events_settings_diagnostics.py"
    )

    assert migration.exists()
    source = migration.read_text(encoding="utf-8")
    assert 'revision: str = "0013_events_settings_diagnostics"' in source
    assert (
        'down_revision: Union[str, Sequence[str], None] = "0012_ranking_snapshots"'
        in source
    )
    for expected in (
        '"event_sequence"',
        '"event_stream_version"',
        '"domain_event"',
        '"connection_test_result"',
        "uq_domain_event_sequence",
        "uq_domain_event_stream_version",
        "ix_domain_event_delivery",
        "ck_domain_event_stream",
    ):
        assert expected in source
    assert 'op.drop_table("domain_event")' in source
    assert 'op.drop_table("event_sequence")' in source
    assert 'op.drop_table("event_stream_version")' in source


def test_event_model_column_shapes() -> None:
    sequence = Base.metadata.tables["event_sequence"].columns
    event = Base.metadata.tables["domain_event"].columns
    stream_version = Base.metadata.tables["event_stream_version"].columns
    connection_test = Base.metadata.tables["connection_test_result"].columns

    assert set(sequence.keys()) == {"singleton_key", "current_value"}
    assert set(stream_version.keys()) == {
        "stream",
        "aggregate_id",
        "current_version",
    }
    assert set(event.keys()) == {
        "event_id",
        "sequence",
        "stream",
        "aggregate_id",
        "stream_version",
        "event_type",
        "payload",
        "occurred_at",
        "expires_at",
    }
    assert set(connection_test.keys()) == {
        "target",
        "status",
        "error_code",
        "elapsed_ms",
        "checked_at",
    }
