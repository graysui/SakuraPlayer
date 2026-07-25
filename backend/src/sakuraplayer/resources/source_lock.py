from __future__ import annotations

from hashlib import sha256

from sqlalchemy import text
from sqlalchemy.orm import Session


def lock_source_keys(session: Session, keys: set[tuple[str, int]]) -> None:
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return
    for website, external_post_id in sorted(keys):
        session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _lock_key(website, external_post_id)},
        )


def _lock_key(website: str, external_post_id: int) -> int:
    digest = sha256(f"{website}:{external_post_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)
