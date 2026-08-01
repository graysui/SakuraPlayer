from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from sakuraplayer.identity.crypto import SecretDecryptionError
from sakuraplayer.identity.secrets import EncryptedSettingRepository, SecretSetting
from sakuraplayer.resources.number_normalizer import normalize_movie_number

DEFAULT_JAVDB_HOST = "jdforrepam.com"
_MAX_JSON_BYTES = 2 * 1024 * 1024
_STABLE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_DNS_HOSTNAME = re.compile(
    r"(?=^.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
_SIGNATURE_SUFFIX = (
    "71cf27bb3c0bcdf207b64abecddc970098c7421ee7203b9cdae54478478a199e7"
    "d5a6e1a57691123c1a931c057842fb73ba3b3c83bcd69c17ccf174081e3d8aa"
)
_SEARCH_PARAMS = {
    "from_recent": "false",
    "type": "movie",
    "movie_type": "all",
    "movie_sort_by": "relevance",
    "movie_filter_by": "all",
    "page": "1",
    "limit": "24",
}
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
            if not isinstance(payload, dict) or set(payload) != {
                "username",
                "password",
            }:
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
    def __init__(
        self,
        *,
        http_client: httpx.Client,
        host: str = DEFAULT_JAVDB_HOST,
        timestamp: Callable[[], int | float] | None = None,
    ) -> None:
        normalized_host = host.strip().lower()
        if not _DNS_HOSTNAME.fullmatch(normalized_host):
            raise ValueError("invalid JavDB host")
        self._http = http_client
        self._host = normalized_host
        self._base_url = f"https://{normalized_host}"
        self._timestamp = timestamp or time.time

    def search_movie(self, normalized_number: str) -> CoreMovieCandidate | None:
        number = normalize_movie_number(normalized_number)
        if number is None or len(number) > 128:
            raise ValueError("invalid normalized movie number")
        payload = self._request_json(
            "GET",
            "/api/v2/search",
            params={"q": number, **_SEARCH_PARAMS},
            error_code="javdb_upstream_error",
        )
        matches: list[CoreMovieCandidate] = []
        for item in self._movie_list(payload):
            if not isinstance(item, dict):
                continue
            candidate_id = item.get("id")
            candidate_number = normalize_movie_number(
                item.get("number") if isinstance(item.get("number"), str) else None
            )
            if (
                candidate_number == number
                and isinstance(candidate_id, str)
                and _STABLE_ID.fullmatch(candidate_id)
            ):
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
        payload = self._request_json(
            "GET",
            f"/api/v4/movies/{candidate_id}",
            params={"from_rankings": "true"},
            error_code="javdb_upstream_error",
        )
        try:
            return self._parse_detail(candidate_id, payload)
        except (ValueError, TypeError, ArithmeticError):
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
            error_code="javdb_upstream_error",
            status_error_codes={
                401: "javdb_credentials_invalid",
                403: "javdb_credentials_invalid",
            },
        )
        data = payload.get("data")
        token = data.get("token") if isinstance(data, dict) else None
        if payload.get("success") not in {None, 1}:
            raise MetadataProviderProblem("javdb_credentials_invalid")
        if not isinstance(token, str) or not token or len(token) > 4096:
            raise MetadataProviderProblem("javdb_upstream_error")
        return token

    def probe_credentials(self, credentials: JavdbCredentials) -> None:
        self._login(credentials)

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
    def _movie_list(payload: dict[str, object]) -> list[object]:
        return JavdbProvider._ranking_movies(
            payload,
            error_code="javdb_upstream_error",
        )

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
        status_error_codes: dict[int, str] | None = None,
    ) -> dict[str, object]:
        try:
            response = self._http.request(
                method,
                f"{self._base_url}{path}",
                params=params,
                data=data,
                headers=self._request_headers(headers),
                timeout=httpx.Timeout(30.0, connect=10.0, pool=10.0),
            )
        except httpx.HTTPError:
            raise MetadataProviderProblem(error_code) from None
        if response.status_code != 200:
            raise MetadataProviderProblem(
                (status_error_codes or {}).get(response.status_code, error_code)
            )
        if len(response.content) > _MAX_JSON_BYTES:
            raise MetadataProviderProblem(error_code)
        try:
            payload = response.json()
        except (ValueError, UnicodeError):
            raise MetadataProviderProblem(error_code) from None
        if not isinstance(payload, dict):
            raise MetadataProviderProblem(error_code)
        return payload

    def _request_headers(self, extra: dict[str, str] | None) -> dict[str, str]:
        current_timestamp = int(self._timestamp())
        digest = hashlib.md5(  # noqa: S324 - required by the upstream protocol
            f"{current_timestamp}{_SIGNATURE_SUFFIX}".encode("ascii"),
            usedforsecurity=False,
        ).hexdigest()
        headers = {
            "Connection": "keep-alive",
            "Accept-Language": "zh-TW",
            "Host": self._host,
            "jdsignature": f"{current_timestamp}.lpw6vgqzsp.{digest}",
        }
        headers.update(extra or {})
        return headers

    @staticmethod
    def _parse_detail(
        candidate_id: str,
        payload: dict[str, object],
    ) -> CoreMovieMetadata:
        if payload.get("success") != 1:
            raise ValueError("unsuccessful detail")
        data = payload.get("data")
        movie = data.get("movie") if isinstance(data, dict) else None
        if not isinstance(movie, dict) or movie.get("id") != candidate_id:
            raise ValueError("invalid movie identity")
        number = normalize_movie_number(
            movie.get("number") if isinstance(movie.get("number"), str) else None
        )
        title = JavdbProvider._optional_text(movie, "title")
        if number is None or title is None:
            raise ValueError("missing movie fields")
        release_text = JavdbProvider._optional_text(movie, "release_date")
        score_value = movie.get("score")
        score = Decimal(str(score_value)) if score_value is not None else None
        return CoreMovieMetadata(
            javdb_id=candidate_id,
            normalized_number=number,
            title_original=title,
            release_date=date.fromisoformat(release_text) if release_text else None,
            maker=JavdbProvider._optional_text(movie, "maker_name"),
            series=JavdbProvider._optional_text(movie, "series_name"),
            director=JavdbProvider._optional_text(movie, "director_name"),
            actors=JavdbProvider._actors(movie, candidate_id),
            tags=JavdbProvider._tags(movie, candidate_id),
            score=score,
            cover_url=JavdbProvider._normalize_image_url(
                JavdbProvider._optional_text(movie, "cover_url")
            ),
            plot_urls=JavdbProvider._plot_urls(movie, candidate_id),
        )

    @staticmethod
    def _actors(
        movie: dict[str, object], candidate_id: str
    ) -> tuple[CoreActorMetadata, ...]:
        actors: list[CoreActorMetadata] = []
        for item in JavdbProvider._optional_list(movie, "actors", candidate_id):
            if not isinstance(item, dict):
                continue
            actor_id = item.get("id")
            name = JavdbProvider._optional_text(item, "name")
            if (
                not isinstance(actor_id, str)
                or not _STABLE_ID.fullmatch(actor_id)
                or name is None
            ):
                continue
            aliases: list[str] = []
            other_name = JavdbProvider._optional_text(item, "other_name")
            if other_name is not None:
                aliases.extend(
                    value.strip() for value in other_name.split(",") if value.strip()
                )
            traditional_name = JavdbProvider._optional_text(item, "name_zht")
            if traditional_name is not None and traditional_name not in aliases:
                aliases.append(traditional_name)
            actors.append(
                CoreActorMetadata(
                    javdb_id=actor_id,
                    name=name,
                    aliases=tuple(aliases),
                )
            )
        return tuple(actors)

    @staticmethod
    def _tags(movie: dict[str, object], candidate_id: str) -> tuple[str, ...]:
        tags: list[str] = []
        for item in JavdbProvider._optional_list(movie, "tags", candidate_id):
            if not isinstance(item, dict):
                continue
            name = JavdbProvider._optional_text(item, "name")
            if name is not None:
                tags.append(name)
        return tuple(tags)

    @staticmethod
    def _plot_urls(movie: dict[str, object], candidate_id: str) -> tuple[str, ...]:
        urls: list[str] = []
        for item in JavdbProvider._optional_list(movie, "preview_images", candidate_id):
            if not isinstance(item, dict):
                continue
            url = JavdbProvider._normalize_image_url(
                JavdbProvider._optional_text(item, "large_url")
            )
            if url is not None:
                urls.append(url)
        return tuple(urls)

    @staticmethod
    def _optional_list(
        value: dict[str, object],
        field_name: str,
        candidate_id: str,
    ) -> list[object]:
        raw = value.get(field_name)
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise ValueError(f"invalid {field_name} for {candidate_id}")
        return raw

    @staticmethod
    def _optional_text(value: dict[str, object], field_name: str) -> str | None:
        raw = value.get(field_name)
        if raw is None:
            return None
        if not isinstance(raw, str):
            raise ValueError(f"invalid {field_name}")
        normalized = " ".join(raw.split())
        return normalized or None

    @staticmethod
    def _normalize_image_url(value: str | None) -> str | None:
        if value is None:
            return None
        for segment in ("covers", "samples", "avatars"):
            marker = f"{segment}/"
            if marker in value:
                return f"https://c0.jdbstatic.com/{marker}{value.split(marker, 1)[1]}"
        return value


__all__ = [
    "CoreActorMetadata",
    "CoreMovieCandidate",
    "CoreMovieMetadata",
    "DEFAULT_JAVDB_HOST",
    "EncryptedJavdbCredentialStore",
    "JavdbCredentials",
    "JavdbProvider",
    "MetadataProviderProblem",
    "RankedMovieNumber",
]
