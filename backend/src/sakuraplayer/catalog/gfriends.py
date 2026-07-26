from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
import json
from urllib.parse import parse_qsl, quote, unquote, urlsplit
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.catalog.actor_mapping import normalize_actor_alias
from sakuraplayer.catalog.models import (
    Actor,
    ActorAlias,
    GfriendsActorAsset,
    GfriendsSnapshot,
)


GFRIENDS_CONTENT_BASE_URL = (
    "https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content"
)
_ALLOWED_TOP_LEVEL = frozenset({"Content", "Information"})
_ALLOWED_EXTENSIONS = (".jpg", ".png")
_MAX_ENTRIES = 500_000


class GfriendsProblem(ValueError):
    code = "provider_snapshot_invalid"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True)
class GfriendsEntry:
    match_name: str
    url: str


@dataclass(frozen=True)
class GfriendsRebuildOutcome:
    matched_actors: int
    asset_count: int
    discarded_entries: int


def parse_gfriends(payload: bytes) -> tuple[GfriendsEntry, ...]:
    try:
        document = json.loads(payload, object_pairs_hook=_object_without_duplicates)
    except (GfriendsProblem, json.JSONDecodeError, UnicodeDecodeError, TypeError):
        raise GfriendsProblem from None
    if (
        not isinstance(document, dict)
        or set(document) - _ALLOWED_TOP_LEVEL
        or not isinstance(document.get("Content"), dict)
    ):
        raise GfriendsProblem
    entries: list[GfriendsEntry] = []
    for directory, mapping in document["Content"].items():
        safe_directory = _validate_segment(directory)
        if not isinstance(mapping, dict):
            raise GfriendsProblem
        for alias_file, target in mapping.items():
            safe_alias = _validate_segment(alias_file)
            if not isinstance(target, str):
                raise GfriendsProblem
            match_name = _image_stem(safe_alias)
            target_file, query = _parse_target(target)
            url = (
                f"{GFRIENDS_CONTENT_BASE_URL}/"
                f"{quote(safe_directory, safe='-._~()')}/"
                f"{quote(target_file, safe='-._~()')}"
                f"{query}"
            )
            entries.append(GfriendsEntry(match_name=match_name, url=url))
            if len(entries) > _MAX_ENTRIES:
                raise GfriendsProblem
    return tuple(sorted(entries, key=lambda entry: (entry.match_name, entry.url)))


def _object_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise GfriendsProblem
        result[key] = value
    return result


def _validate_segment(value: object) -> str:
    if not isinstance(value, str):
        raise GfriendsProblem
    decoded = unquote(value)
    parsed = urlsplit(decoded)
    if (
        not decoded
        or len(decoded) > 255
        or decoded in {".", ".."}
        or "/" in decoded
        or "\\" in decoded
        or "\x00" in decoded
        or parsed.scheme
        or parsed.netloc
    ):
        raise GfriendsProblem
    return decoded


def _image_stem(filename: str) -> str:
    folded = filename.casefold()
    for extension in _ALLOWED_EXTENSIONS:
        if folded.endswith(extension):
            stem = filename[: -len(extension)].strip()
            if stem:
                return stem
    raise GfriendsProblem


def _parse_target(value: str) -> tuple[str, str]:
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        raise GfriendsProblem
    target_file = _validate_segment(parsed.path)
    _image_stem(target_file)
    if not parsed.query:
        return target_file, ""
    query = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    if len(query) != 1 or query[0][0] != "t" or not query[0][1].isdigit():
        raise GfriendsProblem
    return target_file, f"?t={query[0][1]}"


class GfriendsAssetReconciler:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._now = now or (lambda: datetime.now(timezone.utc))

    def rebuild(
        self,
        entries: Iterable[GfriendsEntry],
        *,
        snapshot_id: uuid.UUID,
    ) -> GfriendsRebuildOutcome:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            return self.rebuild_in_session(
                session,
                entries,
                snapshot_id=snapshot_id,
                current=current,
            )

    def rebuild_in_session(
        self,
        session: Session,
        entries: Iterable[GfriendsEntry],
        *,
        snapshot_id: uuid.UUID,
        current: datetime | None = None,
    ) -> GfriendsRebuildOutcome:
        entry_values = tuple(entries)
        timestamp = current or self._utc_now()
        if timestamp.tzinfo is None:
            raise ValueError("GFriends clock must be timezone-aware")
        snapshot = session.scalar(
            select(GfriendsSnapshot)
            .where(
                GfriendsSnapshot.id == snapshot_id,
                GfriendsSnapshot.status == "current",
            )
            .with_for_update()
        )
        if snapshot is None:
            raise GfriendsProblem
        actors = list(session.scalars(select(Actor).order_by(Actor.id).with_for_update()))
        aliases = list(session.scalars(select(ActorAlias)))
        name_index: dict[str, set[uuid.UUID]] = defaultdict(set)
        for actor in actors:
            for name in (actor.name_ja, actor.name_zh):
                if name:
                    name_index[normalize_actor_alias(name)].add(actor.id)
        for alias in aliases:
            name_index[alias.normalized_alias].add(alias.actor_id)

        candidates: list[tuple[GfriendsEntry, uuid.UUID]] = []
        owners_by_url: dict[str, set[uuid.UUID]] = defaultdict(set)
        for entry in entry_values:
            actor_ids = name_index.get(normalize_actor_alias(entry.match_name), set())
            if len(actor_ids) != 1:
                continue
            actor_id = next(iter(actor_ids))
            candidates.append((entry, actor_id))
            owners_by_url[entry.url].add(actor_id)

        desired: dict[uuid.UUID, dict[str, str]] = defaultdict(dict)
        accepted_entries = 0
        for entry, actor_id in candidates:
            if len(owners_by_url[entry.url]) != 1:
                continue
            accepted_entries += 1
            current_match = desired[actor_id].get(entry.url)
            if current_match is None or entry.match_name < current_match:
                desired[actor_id][entry.url] = entry.match_name

        session.execute(delete(GfriendsActorAsset))
        session.flush()
        asset_count = 0
        for actor_id, assets in sorted(desired.items(), key=lambda item: str(item[0])):
            for position, (url, match_name) in enumerate(sorted(assets.items())):
                session.add(
                    GfriendsActorAsset(
                        id=uuid.uuid4(),
                        actor_id=actor_id,
                        snapshot_id=snapshot_id,
                        asset_kind="profile" if position == 0 else "gallery",
                        position=position,
                        url=url,
                        match_name=match_name,
                        created_at=timestamp,
                    )
                )
                asset_count += 1
        return GfriendsRebuildOutcome(
            matched_actors=len(desired),
            asset_count=asset_count,
            discarded_entries=len(entry_values) - accepted_entries,
        )

    def _utc_now(self) -> datetime:
        current = self._now()
        if current.tzinfo is None:
            raise ValueError("GFriends clock must be timezone-aware")
        return current.astimezone(timezone.utc)


__all__ = [
    "GFRIENDS_CONTENT_BASE_URL",
    "GfriendsAssetReconciler",
    "GfriendsEntry",
    "GfriendsProblem",
    "GfriendsRebuildOutcome",
    "parse_gfriends",
]
