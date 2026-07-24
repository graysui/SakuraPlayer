from __future__ import annotations

import pytest

from sakuraplayer.shared.schema_guard import (
    SchemaGuardError,
    SchemaState,
    validate_schema_for_migration,
    validate_schema_state,
)


def test_current_head_is_accepted() -> None:
    validate_schema_state(
        SchemaState(current_revisions=frozenset({"0001"}), has_user_tables=False),
        known_revisions=frozenset({"0001"}),
        expected_heads=frozenset({"0001"}),
    )


def test_empty_unmigrated_database_requires_migration() -> None:
    with pytest.raises(SchemaGuardError) as error:
        validate_schema_state(
            SchemaState(current_revisions=None, has_user_tables=False),
            known_revisions=frozenset({"0001"}),
            expected_heads=frozenset({"0001"}),
        )

    assert error.value.code == "schema_migration_required"


def test_known_older_revision_requires_migration() -> None:
    with pytest.raises(SchemaGuardError) as error:
        validate_schema_state(
            SchemaState(current_revisions=frozenset({"0000"}), has_user_tables=False),
            known_revisions=frozenset({"0000", "0001"}),
            expected_heads=frozenset({"0001"}),
        )

    assert error.value.code == "schema_migration_required"


@pytest.mark.parametrize(
    "state",
    [
        SchemaState(current_revisions=None, has_user_tables=True),
        SchemaState(current_revisions=frozenset({"other"}), has_user_tables=False),
        SchemaState(
            current_revisions=frozenset({"0000", "0001"}),
            has_user_tables=False,
        ),
        SchemaState(current_revisions=frozenset(), has_user_tables=False),
        SchemaState(
            current_revisions=frozenset({"0001"}),
            has_user_tables=False,
            version_row_count=2,
        ),
    ],
)
def test_unknown_or_abnormal_schema_is_rejected(state: SchemaState) -> None:
    with pytest.raises(SchemaGuardError) as error:
        validate_schema_state(
            state,
            known_revisions=frozenset({"0000", "0001"}),
            expected_heads=frozenset({"0001"}),
        )

    assert error.value.code == "schema_revision_unknown"
    assert "0000" not in str(error.value)
    assert "other" not in str(error.value)


def test_empty_database_is_allowed_to_run_initial_migration() -> None:
    validate_schema_for_migration(
        SchemaState(current_revisions=None, has_user_tables=False),
        known_revisions=frozenset({"0001"}),
    )


def test_known_older_revision_is_allowed_to_migrate() -> None:
    validate_schema_for_migration(
        SchemaState(current_revisions=frozenset({"0000"}), has_user_tables=True),
        known_revisions=frozenset({"0000", "0001"}),
    )


@pytest.mark.parametrize(
    "state",
    [
        SchemaState(current_revisions=None, has_user_tables=True),
        SchemaState(current_revisions=frozenset({"other"}), has_user_tables=True),
        SchemaState(current_revisions=frozenset(), has_user_tables=True),
        SchemaState(
            current_revisions=frozenset({"0000", "0001"}),
            has_user_tables=True,
        ),
        SchemaState(
            current_revisions=frozenset({"0001"}),
            has_user_tables=True,
            version_row_count=2,
        ),
    ],
)
def test_migration_refuses_unknown_or_abnormal_schema(state: SchemaState) -> None:
    with pytest.raises(SchemaGuardError) as error:
        validate_schema_for_migration(
            state,
            known_revisions=frozenset({"0000", "0001"}),
        )

    assert error.value.code == "schema_revision_unknown"
