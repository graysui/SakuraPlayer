from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from sakuraplayer.resources.sync_service import AvdbSyncService

TARGET_RESOURCE_COUNT = 289_858


def test_target_scale_row_generator_is_consumed_in_bounded_batches() -> None:
    service = AvdbSyncService(sessionmaker(), batch_size=1_000)
    generated_rows = ({"tid": index} for index in range(TARGET_RESOURCE_COUNT))

    batch_count = 0
    imported_count = 0
    largest_batch = 0
    for batch in service._batches(generated_rows):
        batch_count += 1
        imported_count += len(batch)
        largest_batch = max(largest_batch, len(batch))

    assert imported_count == TARGET_RESOURCE_COUNT
    assert batch_count == 290
    assert largest_batch == 1_000
