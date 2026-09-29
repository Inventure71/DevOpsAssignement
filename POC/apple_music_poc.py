#!/usr/bin/env python3
"""Throwaway Apple Music feasibility lab for docs/04_POC.md.

Secrets, authorization tokens, upstream payloads, and results live in memory
only. Uvicorn access logging is disabled so request metadata cannot accidentally
become a substitute persistence layer.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import ipaddress
import json
import os
import re
import secrets
import socket
import time
import unicodedata
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, urlencode, urljoin, urlparse

import httpx
import jwt
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field


APPLE_API = "https://api.music.apple.com"
ITUNES_API = "https://itunes.apple.com"
DEEZER_API = "https://api.deezer.com"
SPOTIFY_API = "https://api.spotify.com"
SPOTIFY_ACCOUNTS = "https://accounts.spotify.com"
SESSION_COOKIE = "repeat_poc_session"
INDEX_PATH = Path(__file__).with_name("index.html")
ISRC_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}\d{7}$")


class ProviderError(RuntimeError):
    def __init__(self, provider: str, status: int, message: str) -> None:
        super().__init__(message)
        self.provider = provider
        self.status = status
        self.message = message


@dataclass(frozen=True)
class Config:
    team_id: str | None
    key_id: str | None
    private_key_path: Path | None
    storefront: str = "us"
    max_items_per_list: int = 0
    spotify_client_id: str | None = None
    spotify_redirect_uri: str = "http://127.0.0.1:8765/callback"

    @classmethod
    def from_environment(cls) -> "Config":
        raw_path = os.getenv("APPLE_PRIVATE_KEY_PATH")
        raw_max = os.getenv("POC_MAX_ITEMS_PER_LIST", "0")
        try:
            max_items = max(0, int(raw_max))
        except ValueError as exc:
            raise ValueError("POC_MAX_ITEMS_PER_LIST must be a non-negative integer") from exc
        storefront = os.getenv("APPLE_STOREFRONT", "us").strip().lower()
        if not re.fullmatch(r"[a-z]{2}", storefront):
            raise ValueError("APPLE_STOREFRONT must be a two-letter storefront code")
        spotify_redirect = os.getenv(
            "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8765/callback"
        )
        parsed_redirect = urlparse(spotify_redirect)
        if (
            parsed_redirect.scheme != "http"
            or parsed_redirect.hostname != "127.0.0.1"
            or parsed_redirect.port is None
            or parsed_redirect.path != "/callback"
            or parsed_redirect.query
            or parsed_redirect.fragment
        ):
            raise ValueError(
                "SPOTIFY_REDIRECT_URI must be an http://127.0.0.1:<port>/callback URL"
            )
        return cls(
            team_id=os.getenv("APPLE_TEAM_ID"),
            key_id=os.getenv("APPLE_KEY_ID"),
            private_key_path=Path(raw_path).expanduser() if raw_path else None,
            storefront=storefront,
            max_items_per_list=max_items,
            spotify_client_id=os.getenv("SPOTIFY_CLIENT_ID"),
            spotify_redirect_uri=spotify_redirect,
        )

    def apple_missing(self) -> list[str]:
        missing: list[str] = []
        if not self.team_id:
            missing.append("APPLE_TEAM_ID")
        if not self.key_id:
            missing.append("APPLE_KEY_ID")
        if not self.private_key_path:
            missing.append("APPLE_PRIVATE_KEY_PATH")
        elif not self.private_key_path.is_file():
            missing.append("APPLE_PRIVATE_KEY_PATH (file not found)")
        return missing

    @property
    def spotify_ready(self) -> bool:
        # The local browser flow uses Authorization Code with PKCE. A client
        # secret is neither required nor retained for this public-client flow.
        return bool(self.spotify_client_id)


@dataclass(frozen=True)
class Song:
    source: str
    resource_id: str
    title: str
    artist: str
    isrc: str | None
    embedded_preview_url: str | None = None

    @property
    def identity(self) -> str:
        if self.isrc:
            return f"isrc:{self.isrc.upper()}"
        return f"text:{normalise_text(self.title)}|{normalise_text(self.artist)}"


@dataclass(frozen=True)
class PreviewResult:
    identity: str
    title: str
    artist: str
    isrc: str | None
    source: str | None
    url: str | None


@dataclass
class SessionData:
    music_user_token: str | None = None
    spotify_access_token: str | None = None
    spotify_refresh_token: str | None = None
    spotify_expires_at: float = 0
    spotify_state: str | None = None
    spotify_code_verifier: str | None = None
    songs: list[Song] = field(default_factory=list)
    song_provider: str | None = None
    previews: list[PreviewResult] = field(default_factory=list)
    played_samples: set[str] = field(default_factory=set)
    report: dict[str, Any] = field(default_factory=dict)
    updated_at: float = field(default_factory=time.time)


@dataclass
class SyncRun:
    run_id: str
    preview_url: str
    title: str
    start_at_ms: int | None
    created_at: float
    observations: dict[str, dict[str, Any]] = field(default_factory=dict)


class UserTokenBody(BaseModel):
    token: str = Field(min_length=20, max_length=8192)
    transport: str = Field(default="http", max_length=16)


class AuthorizationFailureBody(BaseModel):
    transport: str = Field(default="http", max_length=16)
    reason: str = Field(min_length=1, max_length=300)


class CatalogBody(BaseModel):
    term: str = Field(default="Billie Eilish", min_length=1, max_length=100)


class PlaybackBody(BaseModel):
    identity: str = Field(min_length=1, max_length=300)


class SyncCreateBody(BaseModel):
    preview_url: str = Field(min_length=10, max_length=2048)
    title: str = Field(default="Preview", max_length=200)


class SyncScheduleBody(BaseModel):
    delay_ms: int = Field(default=3000, ge=3000, le=15000)


class SyncObservationBody(BaseModel):
    client_id: str = Field(min_length=8, max_length=100)
    estimated_server_start_ms: float
    scheduled_server_start_ms: float
    clock_offset_ms: float
    best_rtt_ms: float = Field(ge=0, le=60_000)
    audio_current_time: float = Field(ge=0, le=120)
    audible: bool | None = None


SESSIONS: dict[str, SessionData] = {}
SYNC_RUNS: dict[str, SyncRun] = {}


def normalise_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"\s*[\[(]\s*(?:feat\.?|ft\.?).*?[\])]", "", value, flags=re.I)
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def percentage(numerator: int, denominator: int) -> float:
    return round((100 * numerator / denominator), 1) if denominator else 0.0


def deduplicate_songs(songs: Iterable[Song]) -> list[Song]:
    song_list = list(songs)
    isrc_songs: dict[str, Song] = {}
    catalog_to_isrc: dict[str, str] = {}
    text_to_isrcs: dict[str, set[str]] = {}
    for song in song_list:
        if not song.isrc:
            continue
        isrc_key = f"isrc:{song.isrc.upper()}"
        isrc_songs.setdefault(isrc_key, song)
        if song.resource_id:
            catalog_to_isrc[song.resource_id] = isrc_key
        text_key = f"text:{normalise_text(song.title)}|{normalise_text(song.artist)}"
        text_to_isrcs.setdefault(text_key, set()).add(isrc_key)

    unique: dict[str, Song] = {}
    for song in song_list:
        if song.isrc:
            unique.setdefault(song.identity, isrc_songs[song.identity])
            continue
        text_key = song.identity
        catalog_match = catalog_to_isrc.get(song.resource_id) if song.resource_id else None
        text_matches = text_to_isrcs.get(text_key, set())
        if catalog_match:
            unique.setdefault(catalog_match, isrc_songs[catalog_match])
        elif len(text_matches) == 1:
            isrc_key = next(iter(text_matches))
            unique.setdefault(isrc_key, isrc_songs[isrc_key])
        else:
            # Multiple recordings with the same title/artist are ambiguous;
            # keep the ISRC-less item distinct rather than merging incorrectly.
            unique.setdefault(text_key, song)
    return list(unique.values())


def first_preview(attributes: dict[str, Any]) -> str | None:
    previews = attributes.get("previews") or []
    if previews and isinstance(previews[0], dict):
        value = previews[0].get("url")
        return value if isinstance(value, str) and value.startswith("https://") else None
    return None


def song_from_resource(resource: dict[str, Any], source: str) -> Song | None:
    resource_type = resource.get("type")
    attributes = resource.get("attributes") or {}
    catalog_attributes: dict[str, Any] = {}
    catalog_id: str | None = None
    if resource_type == "library-songs":
        catalog_items = (
            resource.get("relationships", {}).get("catalog", {}).get("data", [])
        )
        if catalog_items:
            catalog = catalog_items[0]
            catalog_id = catalog.get("id")
            catalog_attributes = catalog.get("attributes") or {}
        play_params = attributes.get("playParams") or {}
        catalog_id = catalog_id or play_params.get("catalogId")
    elif resource_type != "songs":
        return None

    title = attributes.get("name") or catalog_attributes.get("name")
    artist = attributes.get("artistName") or catalog_attributes.get("artistName")
    if not isinstance(title, str) or not isinstance(artist, str):
        return None
    raw_isrc = catalog_attributes.get("isrc") or attributes.get("isrc")
    isrc = str(raw_isrc).upper() if raw_isrc else None
    if isrc and not ISRC_RE.fullmatch(isrc):
        isrc = None
    return Song(
        source=source,
        resource_id=str(catalog_id or resource.get("id") or ""),
        title=title,
        artist=artist,
        isrc=isrc,
        embedded_preview_url=first_preview(catalog_attributes) or first_preview(attributes),
    )


def song_from_spotify_track(track: dict[str, Any], source: str) -> Song | None:
    title = track.get("name")
    artists = track.get("artists") or []
    artist = next(
        (
            item.get("name")
            for item in artists
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ),
        None,
    )
    if (
        not isinstance(title, str)
        or not title.strip()
        or not artist
        or not artist.strip()
    ):
        return None
    raw_isrc = (track.get("external_ids") or {}).get("isrc")
    isrc = str(raw_isrc).upper() if raw_isrc else None
    if isrc and not ISRC_RE.fullmatch(isrc):
        isrc = None
    return Song(
        source=source,
        resource_id=str(track.get("id") or ""),
        title=title,
        artist=artist,
        isrc=isrc,
        # Spotify preview_url is deprecated and must not contaminate the
        # Apple -> iTunes -> Deezer coverage measurement.
        embedded_preview_url=None,
    )


def activate_song_corpus(
    session: SessionData, provider: str, songs: Iterable[Song]
) -> None:
    session.songs = list(songs)
    session.song_provider = provider
    session.previews.clear()
    session.played_samples.clear()
    # These results describe the previous corpus and would be misleading after
    # switching from Apple to Spotify (or back again).
    session.report.pop("q4", None)
    session.report.pop("q5", None)


def make_developer_token(config: Config, *, origin: str | None = None, now: int | None = None) -> str:
    missing = config.apple_missing()
    if missing:
        raise ValueError("Missing Apple configuration: " + ", ".join(missing))
    issued_at = int(time.time()) if now is None else now
    claims: dict[str, Any] = {
        "iss": config.team_id,
        "iat": issued_at,
        "exp": issued_at + (6 * 60 * 60),
    }
    if origin:
        claims["origin"] = [origin]
    # The key is read only for signing and is never retained in application state.
    private_key = config.private_key_path.read_bytes()  # type: ignore[union-attr]
    return jwt.encode(claims, private_key, algorithm="ES256", headers={"kid": config.key_id})


def is_loopback(request: Request) -> bool:
    if request.client is None:
        return False
    try:
        return ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        return request.client.host == "localhost"


def safe_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProviderError):
        return HTTPException(exc.status if 400 <= exc.status < 500 else 502, exc.message)
    if isinstance(exc, ValueError):
        return HTTPException(503, str(exc))
    return HTTPException(502, "The upstream service request failed")


def get_session(request: Request, response: Response) -> SessionData:
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id or session_id not in SESSIONS:
        session_id = secrets.token_urlsafe(24)
        SESSIONS[session_id] = SessionData()
        response.set_cookie(
            SESSION_COOKIE,
            session_id,
            httponly=True,
            # OAuth redirects are top-level cross-site navigations. Lax keeps
            # the CSRF state cookie available for Spotify's GET callback.
            samesite="lax",
            secure=False,
            max_age=8 * 60 * 60,
        )
    session = SESSIONS[session_id]
    session.updated_at = time.time()
    return session


async def request_json(
    client: httpx.AsyncClient,
    provider: str,
    method: str,
    url: str,
    **kwargs: Any,
) -> dict[str, Any]:
    for attempt in range(3):
        try:
            result = await client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            if attempt == 2:
                raise ProviderError(provider, 502, f"{provider} could not be reached") from exc
            await asyncio.sleep(0.25 * (attempt + 1))
            continue
        if result.status_code == 429 and attempt < 2:
            raw_delay = result.headers.get("retry-after", "1")
            try:
                delay = min(3.0, max(0.25, float(raw_delay)))
            except ValueError:
                delay = 1.0
            await asyncio.sleep(delay)
            continue
        if result.status_code >= 400:
            raise ProviderError(
                provider,
                result.status_code,
                f"{provider} returned HTTP {result.status_code}",
            )
        try:
            payload = result.json()
        except ValueError as exc:
            raise ProviderError(provider, 502, f"{provider} returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ProviderError(provider, 502, f"{provider} returned an unexpected response")
        return payload
    raise ProviderError(provider, 502, f"{provider} request failed")


def apple_headers(config: Config, user_token: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {make_developer_token(config)}"}
    if user_token:
        headers["Music-User-Token"] = user_token
    return headers


async def fetch_apple_pages(
    client: httpx.AsyncClient,
    config: Config,
    path: str,
    *,
    user_token: str,
    params: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = time.perf_counter()
    items: list[dict[str, Any]] = []
    page_sizes: list[int] = []
    next_path: str | None = path
    next_params: dict[str, Any] | None = params
    seen: set[str] = set()
    truncated = False
    total_available: int | None = None

    while next_path:
        parsed = urlparse(next_path)
        if parsed.scheme or parsed.netloc:
            if (
                parsed.scheme != "https"
                or parsed.hostname != "api.music.apple.com"
                or parsed.port is not None
            ):
                raise ProviderError("Apple Music", 502, "Apple returned an unsafe next-page URL")
            request_url = next_path
        else:
            if not next_path.startswith("/v1/"):
                raise ProviderError("Apple Music", 502, "Apple returned an invalid next-page path")
            request_url = urljoin(APPLE_API, next_path)
        marker = request_url + json.dumps(next_params, sort_keys=True)
        if marker in seen:
            raise ProviderError("Apple Music", 502, "Apple returned a pagination loop")
        seen.add(marker)
        payload = await request_json(
            client,
            "Apple Music",
            "GET",
            request_url,
            headers=apple_headers(config, user_token),
            params=next_params,
        )
        page = payload.get("data") or []
        if not isinstance(page, list):
            raise ProviderError("Apple Music", 502, "Apple returned an invalid collection")
        page_sizes.append(len(page))
        items.extend(item for item in page if isinstance(item, dict))
        meta_total = (payload.get("meta") or {}).get("total")
        if isinstance(meta_total, int):
            total_available = meta_total
        next_value = payload.get("next")
        next_path = next_value if isinstance(next_value, str) else None
        next_params = None
        if config.max_items_per_list and len(items) >= config.max_items_per_list:
            exceeded_cap = len(items) > config.max_items_per_list
            items = items[: config.max_items_per_list]
            truncated = next_path is not None or exceeded_cap
            break

    metrics = {
        "resource_count": len(items),
        "pages": len(page_sizes),
        "page_sizes": page_sizes,
        "total_available": total_available,
        "truncated": truncated,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
    }
    return items, metrics


async def catalog_search(
    client: httpx.AsyncClient, config: Config, term: str
) -> list[dict[str, Any]]:
    payload = await request_json(
        client,
        "Apple Music",
        "GET",
        f"{APPLE_API}/v1/catalog/{config.storefront}/search",
        headers=apple_headers(config),
        params={"term": term, "types": "songs", "limit": 5},
    )
    songs = (payload.get("results") or {}).get("songs", {}).get("data", [])
    safe_rows: list[dict[str, Any]] = []
    for item in songs if isinstance(songs, list) else []:
        attributes = item.get("attributes") or {}
        safe_rows.append(
            {
                "name": attributes.get("name"),
                "artist": attributes.get("artistName"),
                "isrc": attributes.get("isrc"),
                "has_preview": bool(first_preview(attributes)),
            }
        )
    return safe_rows


async def listening_probe(
    client: httpx.AsyncClient, config: Config, user_token: str
) -> tuple[dict[str, Any], list[Song]]:
    definitions = [
        (
            "heavy_rotation",
            "/v1/me/history/heavy-rotation",
            {"limit": 30},
            30,
        ),
        (
            "recently_played",
            "/v1/me/recent/played/tracks",
            {
                "types": "songs,library-songs",
                "include[library-songs]": "catalog",
                "limit": 30,
            },
            30,
        ),
        (
            "library",
            "/v1/me/library/songs",
            {"include": "catalog", "limit": 100},
            100,
        ),
    ]
    report: dict[str, Any] = {}
    all_songs: list[Song] = []
    for name, path, params, requested_limit in definitions:
        resources, metrics = await fetch_apple_pages(
            client, config, path, user_token=user_token, params=params
        )
        songs = [song for item in resources if (song := song_from_resource(item, name))]
        resource_types = Counter(str(item.get("type", "unknown")) for item in resources)
        isrc_count = sum(song.isrc is not None for song in songs)
        report[name] = {
            **metrics,
            "requested_page_limit": requested_limit,
            "resource_types": dict(sorted(resource_types.items())),
            "song_count": len(songs),
            "isrc_count": isrc_count,
            "isrc_percent": percentage(isrc_count, len(songs)),
            "status": "data" if resources else "empty",
        }
        all_songs.extend(songs)
    unique = deduplicate_songs(all_songs)
    report["unique_songs"] = len(unique)
    report["passes"] = len(unique) >= 10 and all(
        report[name]["status"] in {"data", "empty"}
        for name, *_ in definitions
    )
    return report, unique


def chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


async def apple_preview_map(
    client: httpx.AsyncClient, config: Config, isrcs: list[str]
) -> tuple[dict[str, str], set[str], int]:
    found: dict[str, str] = {}
    matched: set[str] = set()
    errors = 0
    semaphore = asyncio.Semaphore(5)

    async def fetch_batch(batch: list[str]) -> None:
        nonlocal errors
        try:
            async with semaphore:
                payload = await request_json(
                    client,
                    "Apple Music",
                    "GET",
                    f"{APPLE_API}/v1/catalog/{config.storefront}/songs",
                    headers=apple_headers(config),
                    params={"filter[isrc]": ",".join(batch)},
                )
        except ProviderError:
            errors += 1
            return
        candidates = payload.get("data") or []
        # Sorting makes selection deterministic when one ISRC maps to editions.
        for item in sorted(candidates, key=lambda value: str(value.get("id", ""))):
            attributes = item.get("attributes") or {}
            candidate_isrc = str(attributes.get("isrc") or "").upper()
            preview = first_preview(attributes)
            if candidate_isrc in batch:
                matched.add(candidate_isrc)
                if preview and candidate_isrc not in found:
                    found[candidate_isrc] = preview

    await asyncio.gather(*(fetch_batch(batch) for batch in chunks(isrcs, 25)))
    return found, matched, errors


async def itunes_preview(
    client: httpx.AsyncClient, song: Song, semaphore: asyncio.Semaphore
) -> tuple[str | None, bool]:
    try:
        async with semaphore:
            payload = await request_json(
                client,
                "iTunes Search",
                "GET",
                f"{ITUNES_API}/search",
                params={"term": f"{song.title} {song.artist}", "entity": "song", "limit": 5},
            )
    except ProviderError:
        return None, True
    expected_title = normalise_text(song.title)
    expected_artist = normalise_text(song.artist)
    for candidate in payload.get("results") or []:
        if not isinstance(candidate, dict):
            continue
        title_matches = normalise_text(str(candidate.get("trackName") or "")) == expected_title
        artist_matches = normalise_text(str(candidate.get("artistName") or "")) == expected_artist
        preview = candidate.get("previewUrl")
        if title_matches and artist_matches and isinstance(preview, str) and preview.startswith("https://"):
            return preview, False
    return None, False


async def deezer_preview(
    client: httpx.AsyncClient, song: Song, semaphore: asyncio.Semaphore
) -> tuple[str | None, bool]:
    if not song.isrc:
        return None, False
    try:
        async with semaphore:
            payload = await request_json(
                client,
                "Deezer",
                "GET",
                f"{DEEZER_API}/track/isrc:{quote(song.isrc, safe='')}",
            )
    except ProviderError:
        return None, True
    if "error" in payload:
        return None, True
    preview = payload.get("preview")
    if isinstance(preview, str) and preview.startswith("https://"):
        return preview, False
    return None, False


def preview_metrics(results: list[PreviewResult]) -> dict[str, Any]:
    total = len(results)
    apple = sum(result.source == "apple" for result in results)
    itunes = sum(result.source == "itunes" for result in results)
    deezer = sum(result.source == "deezer" for result in results)
    return {
        "total_songs": total,
        "apple_count": apple,
        "apple_percent": percentage(apple, total),
        "after_itunes_count": apple + itunes,
        "after_itunes_percent": percentage(apple + itunes, total),
        "after_deezer_count": apple + itunes + deezer,
        "after_deezer_percent": percentage(apple + itunes + deezer, total),
        "unresolved_count": total - apple - itunes - deezer,
        "coverage_passes": percentage(apple + itunes + deezer, total) >= 80,
    }


async def preview_probe(
    client: httpx.AsyncClient, config: Config, songs: list[Song]
) -> tuple[dict[str, Any], list[PreviewResult]]:
    unique_isrcs = sorted({song.isrc for song in songs if song.isrc})
    apple_urls, apple_matches, apple_errors = await apple_preview_map(
        client, config, unique_isrcs
    )
    results: dict[str, PreviewResult] = {}
    unresolved: list[Song] = []
    for song in songs:
        url = apple_urls.get(song.isrc or "")
        if url:
            results[song.identity] = PreviewResult(
                song.identity, song.title, song.artist, song.isrc, "apple", url
            )
        else:
            unresolved.append(song)

    semaphore = asyncio.Semaphore(8)
    itunes_results = await asyncio.gather(
        *(itunes_preview(client, song, semaphore) for song in unresolved)
    )
    still_unresolved: list[Song] = []
    itunes_errors = 0
    for song, (url, had_error) in zip(unresolved, itunes_results, strict=True):
        itunes_errors += had_error
        if url:
            results[song.identity] = PreviewResult(
                song.identity, song.title, song.artist, song.isrc, "itunes", url
            )
        else:
            still_unresolved.append(song)

    deezer_results = await asyncio.gather(
        *(deezer_preview(client, song, semaphore) for song in still_unresolved)
    )
    deezer_errors = 0
    for song, (url, had_error) in zip(still_unresolved, deezer_results, strict=True):
        deezer_errors += had_error
        results[song.identity] = PreviewResult(
            song.identity,
            song.title,
            song.artist,
            song.isrc,
            "deezer" if url else None,
            url,
        )

    ordered = [results[song.identity] for song in songs]
    metrics = preview_metrics(ordered)
    metrics["apple_lookup_eligible_count"] = len(unique_isrcs)
    metrics["apple_catalog_match_count"] = len(apple_matches)
    metrics["apple_catalog_match_percent"] = percentage(len(apple_matches), len(songs))
    metrics["provider_errors"] = {
        "apple_batches": apple_errors,
        "itunes_songs": itunes_errors,
        "deezer_songs": deezer_errors,
    }
    metrics["manual_playback_confirmed"] = 0
    metrics["three_clip_check_passes"] = False
    return metrics, ordered


async def chart_probe(client: httpx.AsyncClient, config: Config) -> dict[str, Any]:
    started = time.perf_counter()
    payload = await request_json(
        client,
        "Apple Music",
        "GET",
        f"{APPLE_API}/v1/catalog/{config.storefront}/charts",
        headers=apple_headers(config),
        params={"types": "songs", "limit": 50},
    )
    charts = (payload.get("results") or {}).get("songs") or []
    songs: list[dict[str, Any]] = []
    for chart in charts if isinstance(charts, list) else []:
        songs.extend(item for item in (chart.get("data") or []) if isinstance(item, dict))
    isrc_count = 0
    preview_count = 0
    both_count = 0
    for item in songs:
        attributes = item.get("attributes") or {}
        has_isrc = bool(attributes.get("isrc"))
        has_preview = bool(first_preview(attributes))
        isrc_count += has_isrc
        preview_count += has_preview
        both_count += has_isrc and has_preview
    return {
        "song_count": len(songs),
        "isrc_count": isrc_count,
        "isrc_percent": percentage(isrc_count, len(songs)),
        "preview_count": preview_count,
        "preview_percent": percentage(preview_count, len(songs)),
        "isrc_and_preview_count": both_count,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "passes": both_count >= 30,
    }


def sync_summary(sync_run: SyncRun) -> dict[str, Any]:
    observations = list(sync_run.observations.values())
    starts = [item["estimated_server_start_ms"] for item in observations]
    drift = round(max(starts) - min(starts), 1) if len(starts) >= 2 else None
    start_errors = [
        abs(item["estimated_server_start_ms"] - item["scheduled_server_start_ms"])
        for item in observations
    ]
    max_start_error = round(max(start_errors), 1) if len(start_errors) >= 2 else None
    audible_count = sum(item.get("audible") is True for item in observations)
    timing_passes = (
        drift is not None
        and drift <= 300
        and max_start_error is not None
        and max_start_error <= 300
    )
    public_observations = [
        {
            "client_id": item["client_id"],
            "start_error_ms": round(
                item["estimated_server_start_ms"] - item["scheduled_server_start_ms"], 1
            ),
            "best_rtt_ms": round(item["best_rtt_ms"], 1),
            "audio_current_time": round(item["audio_current_time"], 3),
            "audible": item.get("audible"),
        }
        for item in observations
    ]
    return {
        "run_id": sync_run.run_id,
        "title": sync_run.title,
        "start_at_ms": sync_run.start_at_ms,
        "observation_count": len(observations),
        "audible_confirmed_count": audible_count,
        "observations": public_observations,
        "inter_device_drift_ms": drift,
        "max_absolute_start_error_ms": max_start_error,
        "timing_passes": timing_passes,
        "awaiting_audibility": len(observations) >= 2 and audible_count < 2,
        "passes": timing_passes and audible_count >= 2,
    }


def validate_preview_url(value: str) -> str:
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").lower()
    allowed = (
        hostname.endswith(".apple.com")
        or hostname.endswith(".mzstatic.com")
        or hostname.endswith(".itunes.apple.com")
        or hostname.endswith(".deezer.com")
        or hostname.endswith(".dzcdn.net")
    )
    if parsed.scheme != "https" or not allowed:
        raise HTTPException(400, "Use an HTTPS Apple, iTunes, or Deezer preview URL")
    return value


def spotify_pkce_pair() -> tuple[str, str]:
    """Return a one-time RFC 7636 verifier and its unpadded S256 challenge."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return verifier, challenge


async def spotify_access_token(
    client: httpx.AsyncClient, config: Config, session: SessionData
) -> str:
    if session.spotify_access_token and session.spotify_expires_at > time.time() + 30:
        return session.spotify_access_token
    if not session.spotify_refresh_token or not config.spotify_ready:
        raise HTTPException(401, "Sign in with Spotify first")
    payload = await request_json(
        client,
        "Spotify",
        "POST",
        f"{SPOTIFY_ACCOUNTS}/api/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": session.spotify_refresh_token,
            "client_id": config.spotify_client_id,
        },
    )
    session.spotify_access_token = payload.get("access_token")
    session.spotify_expires_at = time.time() + int(payload.get("expires_in", 3600))
    if not session.spotify_access_token:
        raise HTTPException(502, "Spotify did not return an access token")
    return session.spotify_access_token


async def spotify_probe(
    client: httpx.AsyncClient, config: Config, session: SessionData
) -> tuple[dict[str, Any], list[Song]]:
    token = await spotify_access_token(client, config, session)
    headers = {"Authorization": f"Bearer {token}"}
    result: dict[str, Any] = {"top_tracks": {}}
    all_songs: list[Song] = []
    sources_by_identity: dict[str, list[str]] = {}

    def collect(tracks: list[dict[str, Any]], source: str) -> list[Song]:
        songs = [
            song
            for track in tracks
            if (song := song_from_spotify_track(track, source)) is not None
        ]
        for song in songs:
            sources = sources_by_identity.setdefault(song.identity, [])
            label = source.removeprefix("spotify_")
            if label not in sources:
                sources.append(label)
        all_songs.extend(songs)
        return songs

    for time_range in ("short_term", "medium_term", "long_term"):
        payload = await request_json(
            client,
            "Spotify",
            "GET",
            f"{SPOTIFY_API}/v1/me/top/tracks",
            headers=headers,
            params={"time_range": time_range, "limit": 50},
        )
        tracks = [item for item in payload.get("items") or [] if isinstance(item, dict)]
        songs = collect(tracks, f"spotify_top_{time_range}")
        with_isrc = sum(song.isrc is not None for song in songs)
        result["top_tracks"][time_range] = {
            "count": len(tracks),
            "usable_song_count": len(songs),
            "isrc_count": with_isrc,
            "isrc_percent": percentage(with_isrc, len(songs)),
        }
    recent_payload = await request_json(
        client,
        "Spotify",
        "GET",
        f"{SPOTIFY_API}/v1/me/player/recently-played",
        headers=headers,
        params={"limit": 50},
    )
    recent = [
        item.get("track")
        for item in recent_payload.get("items") or []
        if isinstance(item, dict) and isinstance(item.get("track"), dict)
    ]
    recent_songs = collect(recent, "spotify_recently_played")
    recent_isrc = sum(song.isrc is not None for song in recent_songs)
    result["recently_played"] = {
        "count": len(recent),
        "usable_song_count": len(recent_songs),
        "isrc_count": recent_isrc,
        "isrc_percent": percentage(recent_isrc, len(recent_songs)),
    }
    unique = deduplicate_songs(all_songs)
    unique_isrc = sum(song.isrc is not None for song in unique)
    result["unique_songs"] = len(unique)
    result["unique_isrc_count"] = unique_isrc
    result["unique_isrc_percent"] = percentage(unique_isrc, len(unique))
    result["passes"] = any(
        details["count"] > 0 and details["isrc_count"] > 0
        for details in result["top_tracks"].values()
    )

    def source_labels(song: Song) -> list[str]:
        keys = [
            song.identity,
            f"text:{normalise_text(song.title)}|{normalise_text(song.artist)}",
        ]
        labels: list[str] = []
        for key in keys:
            for label in sources_by_identity.get(key, []):
                if label not in labels:
                    labels.append(label)
        return labels

    result["songs"] = [
        {
            "title": song.title,
            "artist": song.artist,
            "isrc": song.isrc,
            "sources": source_labels(song),
        }
        for song in unique
    ]
    return result, unique


def report_markdown(report: dict[str, Any]) -> str:
    def state(question: str) -> str:
        value = report.get(question)
        if not value:
            return "NOT RUN"
        if question == "q4" and value.get("coverage_passes") is True:
            return "PASS" if value.get("three_clip_check_passes") is True else "PENDING PLAYBACK"
        if value.get("passes") is True:
            return "PASS"
        return "FAIL / INVESTIGATE"

    q3 = report.get("q3", {})
    q4 = report.get("q4", {})
    q5 = report.get("q5", {})
    q6 = report.get("q6", {})
    q7 = report.get("q7", {})

    def error_note(value: dict[str, Any]) -> str:
        return f"; error {value['error']}" if value.get("error") else ""

    lines = [
        "# PoC run (sanitized, in-memory)",
        "",
        f"- Q1: {state('q1')} — {len(report.get('q1', {}).get('songs', []))} catalog results{error_note(report.get('q1', {}))}",
        f"- Q2: {state('q2')} — transport {report.get('q2', {}).get('transport', 'not recorded')}{error_note(report.get('q2', {}))}",
        f"- Q3: {state('q3')} — {q3.get('unique_songs', 0)} unique songs{error_note(q3)}",
    ]
    if q3:
        for label, key in (
            ("heavy rotation", "heavy_rotation"),
            ("recently played", "recently_played"),
            ("library", "library"),
        ):
            details = q3.get(key, {})
            lines.append(
                f"  - {label}: {details.get('song_count', 0)} songs / "
                f"{details.get('resource_count', 0)} resources; pages "
                f"{details.get('page_sizes', [])} at requested limit "
                f"{details.get('requested_page_limit', 'n/a')}; available "
                f"{details.get('total_available', 'unknown')}; ISRC "
                f"{details.get('isrc_percent', 0)}%; "
                f"{details.get('elapsed_ms', 0)} ms; truncated {details.get('truncated', False)}; "
                f"types {details.get('resource_types', {})}"
            )
    lines.extend(
        [
        f"- Q4: {state('q4')} — input {q4.get('input_provider', 'not selected')} ({q4.get('input_song_count', 0)} songs); Apple catalog match {q4.get('apple_catalog_match_percent', 0)}%, Apple preview {q4.get('apple_percent', 0)}%, +iTunes {q4.get('after_itunes_percent', 0)}%, +Deezer {q4.get('after_deezer_percent', 0)}%; manual clips {q4.get('manual_playback_confirmed', 0)}/3; provider errors {q4.get('provider_errors', {})}{error_note(q4)}",
        f"- Q5: {state('q5')} — drift {q5.get('inter_device_drift_ms', 'not measured')} ms; max start error {q5.get('max_absolute_start_error_ms', 'not measured')} ms; audible {q5.get('audible_confirmed_count', 0)}/2 across {q5.get('observation_count', 0)} devices",
        f"- Q6 (optional): {state('q6')} — {q6.get('unique_songs', 0)} unique Spotify songs; ISRC {q6.get('unique_isrc_percent', 0)}%{error_note(q6)}",
        f"- Q7: {state('q7')} — {q7.get('song_count', 0)} chart songs; ISRC {q7.get('isrc_percent', 0)}%; previews {q7.get('preview_percent', 0)}%; {q7.get('isrc_and_preview_count', 0)} with both; {q7.get('elapsed_ms', 0)} ms{error_note(q7)}",
        ]
    )
    return "\n".join(lines)


def create_app(config: Config, *, lan_enabled: bool = False) -> FastAPI:
    @asynccontextmanager
    async def lifespan(running_app: FastAPI) -> Any:
        running_app.state.http = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=10.0),
            follow_redirects=False,
            headers={"User-Agent": "WhosOnRepeat-PoC/1.0"},
        )
        try:
            yield
        finally:
            await running_app.state.http.aclose()

    app = FastAPI(
        title="Who's On Repeat — feasibility lab",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def no_store(request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> Response:
        response = HTMLResponse(INDEX_PATH.read_text(encoding="utf-8"))
        get_session(request, response)
        return response

    @app.get("/api/health")
    async def health(request: Request, response: Response) -> dict[str, Any]:
        session = get_session(request, response)
        return {
            "ok": True,
            "apple_configured": not config.apple_missing(),
            "apple_missing": config.apple_missing(),
            "spotify_configured": config.spotify_ready,
            "spotify_authorized": bool(
                session.spotify_access_token or session.spotify_refresh_token
            ),
            "song_provider": session.song_provider,
            "song_count": len(session.songs),
            "storefront": config.storefront,
            "loopback_client": is_loopback(request),
            "max_items_per_list": config.max_items_per_list or None,
            "lan_sync_enabled": lan_enabled,
            "lan_sync_origins": (
                lan_addresses(request.url.port or 80) if lan_enabled else []
            ),
            "server_time_ms": round(time.time() * 1000, 3),
        }

    @app.get("/api/time")
    async def server_time() -> dict[str, float]:
        return {"server_time_ms": time.time() * 1000}

    @app.get("/api/apple/music-kit-config")
    async def music_kit_config(request: Request, response: Response) -> dict[str, Any]:
        if not is_loopback(request):
            raise HTTPException(403, "Apple sign-in is restricted to a loopback browser")
        get_session(request, response)
        try:
            origin = f"{request.url.scheme}://{request.url.netloc}"
            token = make_developer_token(config, origin=origin)
        except Exception as exc:
            raise safe_error(exc) from exc
        return {"developerToken": token, "storefront": config.storefront}

    @app.post("/api/apple/user-token")
    async def accept_user_token(
        body: UserTokenBody, request: Request, response: Response
    ) -> dict[str, bool]:
        if not is_loopback(request):
            raise HTTPException(403, "Apple user tokens are accepted only from loopback")
        session = get_session(request, response)
        session.music_user_token = body.token
        session.report["q2"] = {
            "passes": True,
            "transport": body.transport,
            "loopback": True,
        }
        return {"accepted": True}

    @app.post("/api/apple/authorization-failure")
    async def record_authorization_failure(
        body: AuthorizationFailureBody, request: Request, response: Response
    ) -> dict[str, bool]:
        if not is_loopback(request):
            raise HTTPException(403, "Apple authorization results are accepted only from loopback")
        session = get_session(request, response)
        session.report["q2"] = {
            "passes": False,
            "transport": body.transport,
            "error": body.reason,
        }
        return {"recorded": True}

    @app.post("/api/apple/catalog-test")
    async def run_catalog(
        body: CatalogBody, request: Request, response: Response
    ) -> dict[str, Any]:
        session = get_session(request, response)
        try:
            songs = await catalog_search(app.state.http, config, body.term)
        except Exception as exc:
            public_error = safe_error(exc)
            session.report["q1"] = {"passes": False, "error": public_error.detail}
            raise public_error from exc
        result = {"passes": bool(songs), "songs": songs}
        session.report["q1"] = result
        return result

    @app.post("/api/apple/listening-data")
    async def run_listening(request: Request, response: Response) -> dict[str, Any]:
        session = get_session(request, response)
        if not session.music_user_token:
            raise HTTPException(401, "Sign in with Apple Music first")
        try:
            result, songs = await listening_probe(
                app.state.http, config, session.music_user_token
            )
        except Exception as exc:
            public_error = safe_error(exc)
            session.report["q3"] = {"passes": False, "error": public_error.detail}
            raise public_error from exc
        activate_song_corpus(session, "apple_personal", songs)
        session.report["q3"] = result
        return result

    @app.post("/api/apple/previews")
    async def run_previews(request: Request, response: Response) -> dict[str, Any]:
        session = get_session(request, response)
        if not session.songs:
            raise HTTPException(409, "Run an Apple or Spotify song import first")
        try:
            metrics, previews = await preview_probe(app.state.http, config, session.songs)
        except Exception as exc:
            public_error = safe_error(exc)
            session.report["q4"] = {"passes": False, "error": public_error.detail}
            raise public_error from exc
        metrics["input_provider"] = session.song_provider or "unknown"
        metrics["input_song_count"] = len(session.songs)
        session.previews = previews
        session.played_samples.clear()
        session.report["q4"] = metrics
        samples = [asdict(item) for item in previews if item.url][:3]
        return {**metrics, "samples": samples}

    @app.post("/api/apple/previews/played")
    async def mark_played(
        body: PlaybackBody, request: Request, response: Response
    ) -> dict[str, Any]:
        session = get_session(request, response)
        valid = {item.identity for item in session.previews if item.url}
        if body.identity not in valid:
            raise HTTPException(404, "Unknown preview sample")
        session.played_samples.add(body.identity)
        q4 = session.report.setdefault("q4", {})
        q4["manual_playback_confirmed"] = len(session.played_samples)
        q4["three_clip_check_passes"] = len(session.played_samples) >= 3
        q4["passes"] = bool(q4.get("coverage_passes")) and len(session.played_samples) >= 3
        return {
            "manual_playback_confirmed": len(session.played_samples),
            "three_clip_check_passes": len(session.played_samples) >= 3,
        }

    @app.post("/api/apple/charts")
    async def run_charts(request: Request, response: Response) -> dict[str, Any]:
        session = get_session(request, response)
        try:
            result = await chart_probe(app.state.http, config)
        except Exception as exc:
            public_error = safe_error(exc)
            session.report["q7"] = {"passes": False, "error": public_error.detail}
            raise public_error from exc
        session.report["q7"] = result
        return result

    @app.post("/api/sync/runs")
    async def create_sync(
        body: SyncCreateBody, request: Request, response: Response
    ) -> dict[str, Any]:
        session = get_session(request, response)
        preview_url = validate_preview_url(body.preview_url)
        run_id = secrets.token_urlsafe(6)
        sync_run = SyncRun(
            run_id=run_id,
            preview_url=preview_url,
            title=body.title,
            start_at_ms=None,
            created_at=time.time(),
        )
        SYNC_RUNS[run_id] = sync_run
        session.report["q5"] = sync_summary(sync_run)
        return {
            **sync_summary(sync_run),
            "preview_url": preview_url,
        }

    @app.post("/api/sync/runs/{run_id}/schedule")
    async def schedule_sync(run_id: str, body: SyncScheduleBody) -> dict[str, Any]:
        sync_run = SYNC_RUNS.get(run_id)
        if not sync_run or time.time() - sync_run.created_at > 30 * 60:
            raise HTTPException(404, "Sync run not found or expired")
        sync_run.start_at_ms = round(time.time() * 1000) + body.delay_ms
        sync_run.observations.clear()
        return {**sync_summary(sync_run), "preview_url": sync_run.preview_url}

    @app.get("/api/sync/runs/{run_id}")
    async def get_sync(
        run_id: str, request: Request, response: Response
    ) -> dict[str, Any]:
        sync_run = SYNC_RUNS.get(run_id)
        if not sync_run or time.time() - sync_run.created_at > 30 * 60:
            raise HTTPException(404, "Sync run not found or expired")
        summary = sync_summary(sync_run)
        get_session(request, response).report["q5"] = summary
        return {**summary, "preview_url": sync_run.preview_url}

    @app.post("/api/sync/runs/{run_id}/observations")
    async def observe_sync(
        run_id: str, body: SyncObservationBody, request: Request, response: Response
    ) -> dict[str, Any]:
        sync_run = SYNC_RUNS.get(run_id)
        if not sync_run:
            raise HTTPException(404, "Sync run not found")
        if sync_run.start_at_ms is None:
            raise HTTPException(409, "Sync run has not been scheduled")
        observation = body.model_dump()
        observation["scheduled_server_start_ms"] = sync_run.start_at_ms
        sync_run.observations[body.client_id] = observation
        summary = sync_summary(sync_run)
        session = get_session(request, response)
        session.report["q5"] = summary
        return summary

    @app.get("/api/report")
    async def get_report(request: Request, response: Response) -> dict[str, Any]:
        session = get_session(request, response)
        return {"report": session.report, "markdown": report_markdown(session.report)}

    @app.get("/api/spotify/login")
    async def spotify_login(request: Request, response: Response) -> Response:
        if not is_loopback(request):
            raise HTTPException(403, "Spotify sign-in is restricted to a loopback browser")
        if not config.spotify_ready:
            raise HTTPException(503, "Spotify environment variables are not configured")
        session = get_session(request, response)
        state = secrets.token_urlsafe(24)
        verifier, challenge = spotify_pkce_pair()
        session.spotify_state = state
        session.spotify_code_verifier = verifier
        params = {
            "client_id": config.spotify_client_id,
            "response_type": "code",
            "redirect_uri": config.spotify_redirect_uri,
            "scope": "user-top-read user-read-recently-played",
            "state": state,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "show_dialog": "true",
        }
        redirect = RedirectResponse(f"{SPOTIFY_ACCOUNTS}/authorize?{urlencode(params)}", 302)
        if SESSION_COOKIE in response.headers.get("set-cookie", ""):
            redirect.headers.append("set-cookie", response.headers["set-cookie"])
        return redirect

    @app.get("/callback")
    async def spotify_callback(
        request: Request,
        response: Response,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
    ) -> Response:
        session = get_session(request, response)
        state_is_valid = bool(
            state
            and session.spotify_state
            and secrets.compare_digest(state, session.spotify_state)
        )
        verifier = session.spotify_code_verifier
        session.spotify_state = None
        session.spotify_code_verifier = None
        if not state_is_valid:
            raise HTTPException(400, "Spotify callback state is invalid")
        if error:
            return RedirectResponse(f"/?spotify_error={quote(error, safe='')}", 303)
        if not code:
            raise HTTPException(400, "Spotify callback code is missing")
        if not verifier:
            raise HTTPException(400, "Spotify PKCE verifier is missing")
        try:
            payload = await request_json(
                app.state.http,
                "Spotify",
                "POST",
                f"{SPOTIFY_ACCOUNTS}/api/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": config.spotify_redirect_uri,
                    "client_id": config.spotify_client_id,
                    "code_verifier": verifier,
                },
            )
        except Exception as exc:
            raise safe_error(exc) from exc
        session.spotify_access_token = payload.get("access_token")
        session.spotify_refresh_token = payload.get("refresh_token")
        session.spotify_expires_at = time.time() + int(payload.get("expires_in", 3600))
        redirect = RedirectResponse("/?spotify=connected", 303)
        if SESSION_COOKIE in response.headers.get("set-cookie", ""):
            redirect.headers.append("set-cookie", response.headers["set-cookie"])
        return redirect

    @app.post("/api/spotify/probe")
    async def run_spotify(request: Request, response: Response) -> dict[str, Any]:
        session = get_session(request, response)
        try:
            result, songs = await spotify_probe(app.state.http, config, session)
        except HTTPException:
            raise
        except Exception as exc:
            public_error = safe_error(exc)
            session.report["q6"] = {"passes": False, "error": public_error.detail}
            raise public_error from exc
        activate_song_corpus(session, "spotify", songs)
        # Song titles are returned to this local browser but excluded from the
        # copied aggregate report.
        session.report["q6"] = {
            key: value for key, value in result.items() if key != "songs"
        }
        return result

    return app


def lan_addresses(port: int) -> list[str]:
    found: set[str] = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            address = probe.getsockname()[0]
            if not ipaddress.ip_address(address).is_loopback:
                found.add(f"http://{address}:{port}")
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if not ipaddress.ip_address(address).is_loopback:
                found.add(f"http://{address}:{port}")
    except OSError:
        pass
    return sorted(found)


async def catalog_cli(config: Config, term: str) -> int:
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        try:
            rows = await catalog_search(client, config, term)
        except Exception as exc:
            # This message contains variable names/status only, never key or token values.
            print(json.dumps({"error": safe_error(exc).detail}))
            return 1
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 0 if rows else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve = subparsers.add_parser("serve", help="Run the local browser lab")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    catalog = subparsers.add_parser("catalog-test", help="Run the safe Q1 catalog check")
    catalog.add_argument("--term", default="Billie Eilish")
    args = parser.parse_args()
    try:
        config = Config.from_environment()
    except ValueError as exc:
        print(f"Configuration error: {exc}")
        return 2

    if args.command == "catalog-test":
        return asyncio.run(catalog_cli(config, args.term))

    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        print("LAN mode enabled. Use only on a trusted network.")
        for address in lan_addresses(args.port):
            print(f"Sync device URL: {address}")
        print("Apple and Spotify token routes still accept loopback clients only.")
    print(f"Local lab: http://127.0.0.1:{args.port}")
    uvicorn.run(
        create_app(
            config,
            lan_enabled=args.host not in {"127.0.0.1", "::1", "localhost"},
        ),
        host=args.host,
        port=args.port,
        access_log=False,
        log_level="warning",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
