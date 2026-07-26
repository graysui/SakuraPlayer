from __future__ import annotations

from datetime import date
from dataclasses import dataclass, field
from decimal import Decimal
import json
import re
import uuid

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from sakuraplayer.catalog.providers._html import HtmlNode, parse_html
from sakuraplayer.identity.crypto import SecretDecryptionError
from sakuraplayer.identity.secrets import EncryptedSettingRepository, SecretSetting
from sakuraplayer.resources.number_normalizer import normalize_movie_number


_BASE_URL = "https://javdb.com"
_MAX_HTML_BYTES = 2 * 1024 * 1024
_MAX_JSON_BYTES = 2 * 1024 * 1024
_STABLE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SCORE = re.compile(r"([0-9]+(?:\.[0-9]+)?)")
_PUBLIC_RANKING_BOARDS = {"daily", "weekly", "monthly"}
_TOP250_PAGE_LIMIT = 50
_TOP250_MAX_PAGES = 5
_DEVICE_FIELDS = {
    "device_name": "meizu16sPro",
    "device_model": "meizu/16s Pro",
    "platform": "android",
    "system_version": "9",
    "app_channel": "official",
    "app_version": "official",
    "app_version_number": "1.9.29",
}


class MetadataProviderProblem(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class JavdbCredentials:
    username: str = field(repr=False)
    password: str = field(repr=False)


@dataclass(frozen=True)
class JavdbCredentialSnapshot:
    credentials: JavdbCredentials = field(repr=False)
    version: int


@dataclass(frozen=True)
class RankedMovieNumber:
    rank: int
    normalized_number: str

    def __post_init__(self) -> None:
        if self.rank < 1 or not self.normalized_number:
            raise ValueError("invalid ranked movie number")


class EncryptedJavdbCredentialStore:
    CREDENTIAL_KEY = "javdb.credentials"

    def __init__(self, repository: EncryptedSettingRepository) -> None:
        self._repository = repository

    def save(
        self,
        credentials: JavdbCredentials,
        *,
        expected_version: int,
    ) -> SecretSetting:
        username, password = _validate_credentials(
            credentials.username,
            credentials.password,
        )
        payload = json.dumps(
            {"username": username, "password": password},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return self._repository.create_or_compare_and_set_secret(
            self.CREDENTIAL_KEY,
            expected_version=expected_version,
            value=payload,
        )

    def load(self) -> JavdbCredentials | None:
        snapshot = self.load_snapshot()
        return snapshot.credentials if snapshot is not None else None

    def load_snapshot(self) -> JavdbCredentialSnapshot | None:
        try:
            setting = self._repository.get_secret(self.CREDENTIAL_KEY)
        except SecretDecryptionError:
            raise MetadataProviderProblem("javdb_credentials_invalid") from None
        if setting is None:
            return None
        if len(setting.value) > 4096:
            raise MetadataProviderProblem("javdb_credentials_invalid")
        try:
            payload = json.loads(setting.value.decode("utf-8"))
            if not isinstance(payload, dict) or set(payload) != {"username", "password"}:
                raise ValueError
            username_text = payload["username"]
            password_text = payload["password"]
            if not isinstance(username_text, str) or not isinstance(password_text, str):
                raise ValueError
            username_text = username_text.strip()
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            raise MetadataProviderProblem("javdb_credentials_invalid") from None
        try:
            username_text, password_text = _validate_credentials(
                username_text,
                password_text,
            )
        except ValueError:
            raise MetadataProviderProblem("javdb_credentials_invalid")
        return JavdbCredentialSnapshot(
            credentials=JavdbCredentials(
                username=username_text,
                password=password_text,
            ),
            version=setting.version,
        )

    def clear(self, *, expected_version: int) -> None:
        self._repository.delete_secret(
            self.CREDENTIAL_KEY,
            expected_version=expected_version,
        )


class CoreMovieCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    javdb_id: str = Field(min_length=1, max_length=128)
    normalized_number: str = Field(min_length=1, max_length=128)


def _validate_credentials(username: str, password: str) -> tuple[str, str]:
    normalized_username = username.strip()
    if (
        not normalized_username
        or not password
        or len(normalized_username) > 255
        or len(password) > 1024
    ):
        raise ValueError("invalid JavDB credentials")
    return normalized_username, password


class CoreActorMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    javdb_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    aliases: tuple[str, ...] = ()

    @field_validator("javdb_id", "name")
    @classmethod
    def strip_required(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("value is required")
        return normalized

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        result: list[str] = []
        for value in values:
            normalized = " ".join(value.split())
            if normalized and normalized not in result:
                result.append(normalized)
        return tuple(result)


class CoreMovieMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    javdb_id: str = Field(min_length=1, max_length=128)
    normalized_number: str = Field(min_length=1, max_length=128)
    title_original: str = Field(min_length=1)
    release_date: date | None = None
    maker: str | None = Field(default=None, max_length=255)
    series: str | None = Field(default=None, max_length=255)
    director: str | None = Field(default=None, max_length=255)
    actors: tuple[CoreActorMetadata, ...] = ()
    tags: tuple[str, ...] = ()
    score: Decimal | None = Field(default=None, ge=0, le=999.99)
    cover_url: str | None = None
    plot_urls: tuple[str, ...] = ()

    @field_validator("javdb_id", "normalized_number", "title_original")
    @classmethod
    def strip_movie_required(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("value is required")
        return normalized

    @field_validator("maker", "series", "director")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @field_validator("tags", "plot_urls")
    @classmethod
    def unique_text(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        result: list[str] = []
        for value in values:
            normalized = " ".join(value.split())
            if normalized and normalized not in result:
                result.append(normalized)
        return tuple(result)

    @field_validator("actors")
    @classmethod
    def unique_actors(
        cls,
        values: tuple[CoreActorMetadata, ...],
    ) -> tuple[CoreActorMetadata, ...]:
        actors: dict[str, CoreActorMetadata] = {}
        for actor in values:
            existing = actors.get(actor.javdb_id)
            if existing is None:
                actors[actor.javdb_id] = actor
                continue
            if existing.name != actor.name:
                raise ValueError("conflicting actor identity")
            aliases = tuple(dict.fromkeys((*existing.aliases, *actor.aliases)))
            actors[actor.javdb_id] = existing.model_copy(update={"aliases": aliases})
        return tuple(actors.values())


class JavdbProvider:
    def __init__(self, *, http_client: httpx.Client) -> None:
        self._http = http_client

    def search_movie(self, normalized_number: str) -> CoreMovieCandidate | None:
        number = " ".join(normalized_number.split()).upper()
        if not number or len(number) > 128:
            raise ValueError("invalid normalized movie number")
        response = self._request(
            "/search",
            params={"q": number, "f": "all"},
            not_found=True,
        )
        if response is None:
            return None
        root = parse_html(response)
        matches: list[CoreMovieCandidate] = []
        for anchor in root.descendants("a"):
            href = anchor.attrs.get("href", "")
            if "box" not in anchor.classes() or not href.startswith("/v/"):
                continue
            strong = next(anchor.descendants("strong"), None)
            candidate_number = strong.text().upper() if strong is not None else ""
            candidate_id = href.removeprefix("/v/").strip("/")
            if candidate_number == number and _STABLE_ID.fullmatch(candidate_id):
                matches.append(
                    CoreMovieCandidate(
                        javdb_id=candidate_id,
                        normalized_number=candidate_number,
                    )
                )
        if not matches:
            return None
        if len({item.javdb_id for item in matches}) != 1:
            raise MetadataProviderProblem("javdb_upstream_error")
        return matches[0]

    def fetch_movie(self, candidate_id: str) -> CoreMovieMetadata:
        if not _STABLE_ID.fullmatch(candidate_id):
            raise ValueError("invalid JavDB candidate id")
        response = self._request(f"/v/{candidate_id}", not_found=False)
        assert response is not None
        try:
            return self._parse_detail(candidate_id, parse_html(response))
        except (ValueError, TypeError):
            raise MetadataProviderProblem("javdb_upstream_error") from None

    def fetch_rankings(
        self,
        board: str,
        *,
        year: int | None,
        credentials: JavdbCredentials | None,
    ) -> tuple[RankedMovieNumber, ...]:
        if board in _PUBLIC_RANKING_BOARDS:
            if year is not None:
                raise ValueError("invalid ranking scope")
            payload = self._request_json(
                "GET",
                "/api/v1/rankings/playback",
                params={"filter_by": "all", "period": board},
                error_code="javdb_upstream_error",
            )
            movies = self._ranking_movies(payload, error_code="javdb_upstream_error")
            ranked = self._ranked_numbers(movies)
        elif board == "top250":
            if year is not None and not 2008 <= year <= 2200:
                raise ValueError("invalid ranking scope")
            if credentials is None:
                raise MetadataProviderProblem("javdb_credentials_invalid")
            token = self._login(credentials)
            ranked = self._fetch_top250(token=token, year=year)
        else:
            raise ValueError("invalid ranking scope")
        if not ranked:
            raise MetadataProviderProblem("javdb_upstream_error")
        return ranked

    def _login(self, credentials: JavdbCredentials) -> str:
        username, password = _validate_credentials(
            credentials.username,
            credentials.password,
        )
        device_uuid = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"https://javdb.com/accounts/{username}")
        )
        payload = self._request_json(
            "POST",
            "/api/v1/sessions",
            data={
                "username": username,
                "password": password,
                "device_uuid": device_uuid,
                **_DEVICE_FIELDS,
            },
            headers={
                "User-Agent": "Dart/3.5 (dart:io)",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            error_code="javdb_credentials_invalid",
        )
        data = payload.get("data")
        token = data.get("token") if isinstance(data, dict) else None
        if (
            payload.get("success") not in {None, 1}
            or not isinstance(token, str)
            or not token
            or len(token) > 4096
        ):
            raise MetadataProviderProblem("javdb_credentials_invalid")
        return token

    def _fetch_top250(
        self,
        *,
        token: str,
        year: int | None,
    ) -> tuple[RankedMovieNumber, ...]:
        accepted: list[RankedMovieNumber] = []
        seen: set[str] = set()
        for page in range(1, _TOP250_MAX_PAGES + 1):
            payload = self._request_json(
                "GET",
                "/api/v1/movies/top",
                params={
                    "start_rank": "1",
                    "type": "all" if year is None else "year",
                    "type_value": "" if year is None else str(year),
                    "ignore_watched": "false",
                    "page": str(page),
                    "limit": str(_TOP250_PAGE_LIMIT),
                },
                headers={"Authorization": f"Bearer {token}"},
                error_code="javdb_upstream_error",
            )
            movies = self._ranking_movies(payload, error_code="javdb_upstream_error")
            if not movies:
                break
            accepted.extend(
                self._ranked_numbers(
                    movies,
                    rank_offset=(page - 1) * _TOP250_PAGE_LIMIT,
                    seen=seen,
                )
            )
        return tuple(accepted)

    @staticmethod
    def _ranking_movies(payload: dict[str, object], *, error_code: str) -> list[object]:
        if payload.get("success") != 1:
            raise MetadataProviderProblem(error_code)
        data = payload.get("data")
        movies = data.get("movies") if isinstance(data, dict) else None
        if not isinstance(movies, list):
            raise MetadataProviderProblem(error_code)
        return movies

    @staticmethod
    def _ranked_numbers(
        movies: list[object],
        *,
        rank_offset: int = 0,
        seen: set[str] | None = None,
    ) -> tuple[RankedMovieNumber, ...]:
        known = seen if seen is not None else set()
        result: list[RankedMovieNumber] = []
        for position, item in enumerate(movies, start=1):
            raw_number = item.get("number") if isinstance(item, dict) else None
            number = normalize_movie_number(
                raw_number if isinstance(raw_number, str) else None
            )
            if number is None or number in known:
                continue
            known.add(number)
            result.append(
                RankedMovieNumber(
                    rank=rank_offset + position,
                    normalized_number=number,
                )
            )
        return tuple(result)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        error_code: str,
    ) -> dict[str, object]:
        try:
            response = self._http.request(
                method,
                f"{_BASE_URL}{path}",
                params=params,
                data=data,
                headers=headers,
                timeout=httpx.Timeout(30.0, connect=10.0, pool=10.0),
            )
        except httpx.HTTPError:
            raise MetadataProviderProblem(error_code) from None
        if response.status_code != 200 or len(response.content) > _MAX_JSON_BYTES:
            raise MetadataProviderProblem(error_code)
        try:
            payload = response.json()
        except (ValueError, UnicodeError):
            raise MetadataProviderProblem(error_code) from None
        if not isinstance(payload, dict):
            raise MetadataProviderProblem(error_code)
        return payload

    def _request(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        not_found: bool,
    ) -> str | None:
        try:
            response = self._http.get(
                f"{_BASE_URL}{path}",
                params=params,
                timeout=httpx.Timeout(30.0, connect=10.0, pool=10.0),
            )
        except httpx.HTTPError:
            raise MetadataProviderProblem("javdb_upstream_error") from None
        if response.status_code == 404 and not_found:
            return None
        if response.status_code != 200 or len(response.content) > _MAX_HTML_BYTES:
            raise MetadataProviderProblem("javdb_upstream_error")
        return response.text

    @staticmethod
    def _parse_detail(candidate_id: str, root: HtmlNode) -> CoreMovieMetadata:
        title_node = next(
            (
                node
                for node in root.descendants("h2")
                if {"title", "is-4"}.issubset(node.classes())
            ),
            None,
        )
        if title_node is None:
            raise ValueError("missing title")
        strong = next(title_node.descendants("strong"), None)
        span = next(title_node.descendants("span"), None)
        if strong is None or span is None:
            raise ValueError("missing movie identity")
        number = strong.text().upper()
        title = span.text()

        panels: dict[str, HtmlNode] = {}
        for panel in root.descendants("div"):
            if "panel-block" not in panel.classes():
                continue
            label = next(panel.descendants("strong"), None)
            if label is not None:
                panels[label.text().rstrip(":：")] = panel

        def value(*labels: str) -> str | None:
            for label in labels:
                panel = panels.get(label)
                if panel is None:
                    continue
                value_node = next(
                    (node for node in panel.descendants("span") if "value" in node.classes()),
                    None,
                )
                if value_node is not None:
                    return value_node.text() or None
            return None

        release_text = value("日期", "発売日")
        release_date = date.fromisoformat(release_text) if release_text else None
        score_text = value("評分", "评分")
        score_match = _SCORE.search(score_text or "")
        score = Decimal(score_match.group(1)) if score_match else None

        actors: list[CoreActorMetadata] = []
        actor_panel = panels.get("演員") or panels.get("演员")
        if actor_panel is not None:
            for anchor in actor_panel.descendants("a"):
                actor_id = anchor.attrs.get("href", "").removeprefix("/actors/").strip("/")
                if not _STABLE_ID.fullmatch(actor_id):
                    continue
                aliases = tuple(
                    item.strip()
                    for item in anchor.attrs.get("title", "").split(",")
                    if item.strip()
                )
                actors.append(
                    CoreActorMetadata(
                        javdb_id=actor_id,
                        name=anchor.text(),
                        aliases=aliases,
                    )
                )

        tags: list[str] = []
        tag_panel = panels.get("類別") or panels.get("类别")
        if tag_panel is not None:
            tags = [anchor.text() for anchor in tag_panel.descendants("a") if anchor.text()]

        cover_url = None
        for meta in root.descendants("meta"):
            if meta.attrs.get("property") == "og:image":
                cover_url = meta.attrs.get("content") or None
                break
        plot_urls = tuple(
            anchor.attrs["href"]
            for anchor in root.descendants("a")
            if "tile-item" in anchor.classes() and anchor.attrs.get("href")
        )
        return CoreMovieMetadata(
            javdb_id=candidate_id,
            normalized_number=number,
            title_original=title,
            release_date=release_date,
            maker=value("片商", "メーカー"),
            series=value("系列", "シリーズ"),
            director=value("導演", "导演"),
            actors=tuple(actors),
            tags=tuple(tags),
            score=score,
            cover_url=cover_url,
            plot_urls=plot_urls,
        )


__all__ = [
    "CoreActorMetadata",
    "CoreMovieCandidate",
    "CoreMovieMetadata",
    "EncryptedJavdbCredentialStore",
    "JavdbCredentials",
    "JavdbProvider",
    "MetadataProviderProblem",
    "RankedMovieNumber",
]
