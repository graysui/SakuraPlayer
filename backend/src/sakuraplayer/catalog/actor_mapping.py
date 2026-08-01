from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.catalog.models import Actor, ActorAlias

_REQUIRED_ATTRIBUTES = frozenset({"zh_cn", "zh_tw", "jp", "keyword"})
_OPTIONAL_ATTRIBUTES = frozenset({"tmdb_id", "verified", "bio_graphy"})
_ALLOWED_ATTRIBUTES = _REQUIRED_ATTRIBUTES | _OPTIONAL_ATTRIBUTES
_ALLOWED_GROUPS = frozenset({"actor", "actor-blacklist"})


class ActorMappingProblem(ValueError):
    code = "provider_snapshot_invalid"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True)
class ActorMappingEntry:
    name_ja: str
    name_zh: str
    bio_zh: str | None
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class ActorMappingRebuildOutcome:
    matched_actors: int
    discarded_entries: int


def normalize_actor_alias(value: str) -> str:
    return " ".join(value.casefold().split())


def parse_actor_mapping(payload: bytes) -> tuple[ActorMappingEntry, ...]:
    try:
        root = ElementTree.fromstring(payload)
    except (DefusedXmlException, ElementTree.ParseError, ValueError):
        raise ActorMappingProblem from None
    if root.tag != "actor-mapping" or root.attrib or not list(root):
        raise ActorMappingProblem
    entries: list[ActorMappingEntry] = []
    for group in root:
        if (
            group.tag not in _ALLOWED_GROUPS
            or group.attrib
            or (group.tag == "actor" and not list(group))
        ):
            raise ActorMappingProblem
        for element in group:
            entry = _parse_entry(element)
            if group.tag == "actor":
                entries.append(entry)
    if not entries:
        raise ActorMappingProblem
    return tuple(entries)


def _parse_entry(element) -> ActorMappingEntry:
    if (
        element.tag != "a"
        or list(element)
        or set(element.attrib) - _ALLOWED_ATTRIBUTES
        or not _REQUIRED_ATTRIBUTES.issubset(element.attrib)
    ):
        raise ActorMappingProblem
    values = {key: value.strip() for key, value in element.attrib.items()}
    if any(
        not values[key] or len(values[key]) > 255 for key in ("jp", "zh_cn", "zh_tw")
    ):
        raise ActorMappingProblem
    if len(values["keyword"]) > 4096 or len(values.get("bio_graphy", "")) > 4096:
        raise ActorMappingProblem
    if "tmdb_id" in values and (
        not values["tmdb_id"].isdigit() or len(values["tmdb_id"]) > 32
    ):
        raise ActorMappingProblem
    if "verified" in values and values["verified"] != "1":
        raise ActorMappingProblem
    aliases: dict[str, str] = {}
    candidates = (
        *(part.strip() for part in values["keyword"].split(",")),
        values["zh_cn"],
        values["zh_tw"],
        values["jp"],
    )
    for alias in candidates:
        normalized = normalize_actor_alias(alias)
        if not normalized or len(alias) > 255:
            continue
        aliases.setdefault(normalized, alias)
    if normalize_actor_alias(values["jp"]) not in aliases:
        raise ActorMappingProblem
    bio = values.get("bio_graphy") or None
    return ActorMappingEntry(
        name_ja=values["jp"],
        name_zh=values["zh_cn"],
        bio_zh=bio,
        aliases=tuple(aliases.values()),
    )


class ActorMappingReconciler:
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
        entries: Iterable[ActorMappingEntry],
    ) -> ActorMappingRebuildOutcome:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            return self.rebuild_in_session(session, entries, current=current)

    def rebuild_in_session(
        self,
        session: Session,
        entries: Iterable[ActorMappingEntry],
        *,
        current: datetime | None = None,
    ) -> ActorMappingRebuildOutcome:
        entry_values = tuple(entries)
        timestamp = current or self._utc_now()
        if timestamp.tzinfo is None:
            raise ValueError("actor mapping clock must be timezone-aware")
        actors = list(
            session.scalars(select(Actor).order_by(Actor.id).with_for_update())
        )
        aliases = list(session.scalars(select(ActorAlias)))
        identity_index: dict[str, set[uuid.UUID]] = defaultdict(set)
        javdb_aliases: dict[uuid.UUID, set[str]] = defaultdict(set)
        for actor in actors:
            if actor.name_ja:
                identity_index[normalize_actor_alias(actor.name_ja)].add(actor.id)
        for alias in aliases:
            if alias.authority != "javdb":
                continue
            identity_index[alias.normalized_alias].add(alias.actor_id)
            javdb_aliases[alias.actor_id].add(alias.normalized_alias)

        entries_by_name: dict[str, list[ActorMappingEntry]] = defaultdict(list)
        for entry in entry_values:
            entries_by_name[normalize_actor_alias(entry.name_ja)].append(entry)
        candidates_by_actor: dict[uuid.UUID, list[ActorMappingEntry]] = defaultdict(
            list
        )
        for normalized_name, grouped in entries_by_name.items():
            actor_ids = identity_index.get(normalized_name, set())
            if len(grouped) == 1 and len(actor_ids) == 1:
                candidates_by_actor[next(iter(actor_ids))].append(grouped[0])
        matched = {
            actor_id: grouped[0]
            for actor_id, grouped in candidates_by_actor.items()
            if len(grouped) == 1
        }

        session.execute(
            delete(ActorAlias).where(ActorAlias.authority == "actor_mapping")
        )
        session.flush()
        actors_by_id = {actor.id: actor for actor in actors}
        for actor_id, entry in matched.items():
            actor = actors_by_id[actor_id]
            if entry.name_zh:
                actor.name_zh = entry.name_zh
            if entry.bio_zh:
                actor.bio_zh = entry.bio_zh
                actor.bio_zh_source = "actor_mapping"
            actor.updated_at = timestamp
            desired: dict[str, str] = {}
            for alias in entry.aliases:
                normalized = normalize_actor_alias(alias)
                if normalized and normalized not in javdb_aliases[actor_id]:
                    desired.setdefault(normalized, alias)
            session.add_all(
                ActorAlias(
                    actor_id=actor_id,
                    alias=alias,
                    normalized_alias=normalized,
                    authority="actor_mapping",
                )
                for normalized, alias in desired.items()
            )
        return ActorMappingRebuildOutcome(
            matched_actors=len(matched),
            discarded_entries=len(entry_values) - len(matched),
        )

    def _utc_now(self) -> datetime:
        current = self._now()
        if current.tzinfo is None:
            raise ValueError("actor mapping clock must be timezone-aware")
        return current.astimezone(timezone.utc)


__all__ = [
    "ActorMappingEntry",
    "ActorMappingProblem",
    "ActorMappingRebuildOutcome",
    "ActorMappingReconciler",
    "normalize_actor_alias",
    "parse_actor_mapping",
]
