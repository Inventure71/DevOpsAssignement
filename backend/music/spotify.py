"""Spotify authorization, bounded listening imports, and app catalog metadata."""

import base64
import threading
import time
from urllib.parse import urlencode, urlsplit

from backend.music.http import JsonHttpTransport, MusicProviderError, ProviderHttpError


API_URL = "https://api.spotify.com/v1"
TOKEN_URL = "https://accounts.spotify.com/api/token"
SCOPES = "user-top-read user-read-recently-played"
_LEVELS = ("easy", "medium", "hard")


def normalize_track(track):
    """Preserve all credited artists; reject local or incomplete catalog records."""
    if not isinstance(track, dict) or track.get("is_local"):
        return None
    identifier, title = track.get("id"), track.get("name")
    if not isinstance(identifier, str) or not identifier or not isinstance(title, str) or not title.strip():
        return None
    artists = []
    for row in track.get("artists", []) if isinstance(track.get("artists"), list) else []:
        if (isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"]
                and isinstance(row.get("name"), str) and row["name"].strip()):
            credit = {"artist_key": "spotify:artist:" + row["id"], "name": row["name"][:300]}
            if credit not in artists:
                artists.append(credit)
    if not artists:
        return None
    external = track.get("external_ids")
    isrc = external.get("isrc") if isinstance(external, dict) else None
    album = track.get("album")
    images = album.get("images", []) if isinstance(album, dict) else []
    if not isinstance(images, list):
        images = []
    artwork = next((row["url"] for row in images if isinstance(row, dict)
                    and isinstance(row.get("url"), str) and row["url"].startswith("https://")), None)
    return {"song_key": "spotify:track:" + identifier, "title": title[:300],
            "artist": ", ".join(credit["name"] for credit in artists)[:300], "artists": artists,
            "isrc": isrc.strip().upper() if isinstance(isrc, str) and isrc.strip() else None,
            "artwork_url": artwork}


def _invalid_response():
    return MusicProviderError("spotify_invalid_response",
                              "Spotify returned an incomplete response. Try again shortly.", 503)


class SpotifyClient:
    """Provider facts only: no room persistence, playback, or long-lived user tokens."""

    def __init__(self, client_id, client_secret, redirect_uri, market="ES", transport=None,
                 clock=time.monotonic):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.market = market
        self.transport = transport or JsonHttpTransport()
        self.clock = clock
        self._token_lock = threading.Lock()
        self._app_token = None
        self._app_token_expires = 0

    @property
    def configured(self):
        try:
            redirect = urlsplit(self.redirect_uri or "")
            redirect.port  # Validate a supplied port without constructing a request.
            valid_redirect = (redirect.scheme == "https" or
                              (redirect.scheme == "http" and redirect.hostname in ("127.0.0.1", "::1")))
            valid_redirect = (valid_redirect and bool(redirect.hostname) and not redirect.fragment
                              and redirect.username is None and redirect.password is None)
        except ValueError:
            valid_redirect = False
        return bool(self.client_id and valid_redirect)

    @property
    def search_configured(self):
        return bool(self.configured and self.client_secret)

    def _require_configuration(self):
        if not self.configured:
            raise MusicProviderError("spotify_not_configured", "Spotify is not configured on this server.", 503)

    def authorization_url(self, state, challenge):
        self._require_configuration()
        return "https://accounts.spotify.com/authorize?" + urlencode({
            "client_id": self.client_id, "response_type": "code", "redirect_uri": self.redirect_uri,
            "scope": SCOPES, "state": state, "code_challenge_method": "S256", "code_challenge": challenge})

    def _request(self, method, url, headers=None, data=None):
        try:
            return self.transport.request(method, url, headers=headers, data=data)
        except ProviderHttpError as error:
            if error.status == 403:
                raise MusicProviderError("spotify_account_not_allowed",
                    "Spotify refused access. Check that this account is on the app's five-account allowlist.", 403) from None
            if error.status == 401:
                raise MusicProviderError("spotify_authorization_expired",
                    "Spotify authorization expired or was rejected. Connect Spotify again.", 401) from None
            if error.status == 429:
                seconds = error.retry_after or 30
                raise MusicProviderError("spotify_rate_limited", "Spotify is busy. Try again shortly.", 429,
                                         {"retry_after_seconds": seconds}) from None
            if error.status == 400 and url == TOKEN_URL:
                raise MusicProviderError("spotify_authorization_failed",
                    "Spotify authorization could not be completed. Connect Spotify again.", 400) from None
            raise MusicProviderError("spotify_unavailable", "Spotify is unavailable. Try again shortly.", 503) from None

    def exchange_code(self, code, verifier):
        self._require_configuration()
        payload = self._request("POST", TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"},
            urlencode({"grant_type": "authorization_code", "code": code, "code_verifier": verifier,
                       "client_id": self.client_id, "redirect_uri": self.redirect_uri}).encode())
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise _invalid_response()
        return token

    def _get(self, path, token, params=None):
        url = API_URL + path + ("?" + urlencode(params) if params else "")
        return self._request("GET", url, {"Authorization": "Bearer " + token})

    def profile(self, token):
        self._require_configuration()
        account_id = self._get("/me", token).get("id")
        if not isinstance(account_id, str) or not account_id:
            raise _invalid_response()
        return account_id

    def listening(self, token):
        self._require_configuration()
        songs = {}
        for window in ("short_term", "medium_term", "long_term"):
            payload = self._get("/me/top/tracks", token, {"time_range": window, "limit": 50, "offset": 0})
            rows = payload.get("items")
            if not isinstance(rows, list):
                raise _invalid_response()
            for rank, track in enumerate(rows[:50], 1):
                level = ("easy" if window == "short_term" and rank <= 20 else
                         "hard" if window == "long_term" else "medium")
                self._merge(songs, track, window, rank, level)
        payload = self._get("/me/player/recently-played", token, {"limit": 50})
        rows = payload.get("items")
        if not isinstance(rows, list):
            raise _invalid_response()
        for rank, row in enumerate(rows[:50], 1):
            if isinstance(row, dict):
                self._merge(songs, row.get("track"), "recently_played", rank, "medium")
        # Round-robin strata keep long-term-only candidates even when recent lists are full.
        buckets = {level: [song for song in songs.values() if song["familiarity"] == level] for level in _LEVELS}
        selected = []
        while len(selected) < 60 and any(buckets.values()):
            for level in _LEVELS:
                if buckets[level] and len(selected) < 60:
                    selected.append(buckets[level].pop(0))
        return selected

    @staticmethod
    def _merge(songs, track, source, rank, level):
        song = normalize_track(track)
        if song is None:
            return
        key = song["isrc"] or song["song_key"]
        evidence = {"source": source, "rank": rank}
        existing = songs.get(key)
        if existing is None:
            songs[key] = song | {"familiarity": level, "source_evidence": [evidence]}
            return
        if _LEVELS.index(level) < _LEVELS.index(existing["familiarity"]):
            existing["familiarity"] = level
        if evidence not in existing["source_evidence"]:
            existing["source_evidence"].append(evidence)
        for artist in song["artists"]:
            if artist not in existing["artists"]:
                existing["artists"].append(artist)
        existing["artist"] = ", ".join(artist["name"] for artist in existing["artists"])[:300]
        if not existing["artwork_url"]:
            existing["artwork_url"] = song["artwork_url"]

    def _catalog_token(self):
        if not self.search_configured:
            raise MusicProviderError("spotify_search_not_configured",
                "Spotify catalog search requires a server-side client secret. Configure it or use Apple catalog search.", 503)
        with self._token_lock:
            if self._app_token and self.clock() < self._app_token_expires:
                return self._app_token
            credentials = base64.b64encode((self.client_id + ":" + self.client_secret).encode()).decode()
            payload = self._request("POST", TOKEN_URL,
                {"Authorization": "Basic " + credentials, "Content-Type": "application/x-www-form-urlencoded"},
                b"grant_type=client_credentials")
            token, expires = payload.get("access_token"), payload.get("expires_in")
            if (not isinstance(token, str) or not token or isinstance(expires, bool)
                    or not isinstance(expires, (int, float)) or not 0 < expires <= 86_400):
                raise _invalid_response()
            self._app_token, self._app_token_expires = token, self.clock() + max(0, expires - 30)
            return token

    def _search(self, query, offset=0):
        token = self._catalog_token()
        params = {"q": query, "type": "track", "market": self.market, "limit": 10, "offset": offset}
        try:
            payload = self._get("/search", token, params)
        except MusicProviderError as error:
            if error.code != "spotify_authorization_expired":
                raise
            # Cached app tokens may be revoked before their advertised expiry.
            # Refresh once; never retry personal requests with someone else's token.
            with self._token_lock:
                if self._app_token == token:
                    self._app_token = None
                    self._app_token_expires = 0
            payload = self._get("/search", self._catalog_token(), params)
        tracks = payload.get("tracks")
        rows = tracks.get("items") if isinstance(tracks, dict) else None
        if not isinstance(rows, list):
            raise _invalid_response()
        songs = []
        seen = set()
        for track in rows[:10]:
            song = normalize_track(track)
            if song and song["song_key"] not in seen:
                seen.add(song["song_key"])
                songs.append(song)
        return songs

    def search(self, query):
        return self._search(query)

    def decoys(self):
        songs = {}
        for offset in (0, 10, 20):
            for song in self._search("year:2010-2025", offset):
                songs.setdefault(song["isrc"] or song["song_key"], song)
        return list(songs.values())
