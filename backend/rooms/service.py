"""Admission, room-scoped identity, presence and immutable snapshot exports."""

import hashlib
import json
import secrets
import sqlite3

from backend.core.errors import DomainError
from . import demo, repository

RETENTION_MS = 30 * 24 * 60 * 60 * 1000
HOST_GRACE_MS = 60_000
CONNECTED_MS = 15_000
ROOM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
COLOR_PRESETS = frozenset({"coral", "periwinkle", "lavender", "lemon", "lilac", "sage", "sky", "rose"})


def _nickname(value: str) -> tuple[str, str]:
    if not isinstance(value, str):
        raise DomainError("invalid_nickname", "Nickname must be text")
    value = value.strip()
    if not 1 <= len(value) <= 24 or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise DomainError("invalid_nickname", "Nickname must contain 1–24 visible characters")
    return value, value.casefold()


def _character(value: str) -> str:
    if not isinstance(value, str) or value not in COLOR_PRESETS:
        raise DomainError("invalid_character", "Choose a supported blob color")
    return value


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class RoomsService:
    def room(self, conn: sqlite3.Connection, room_id: str, now_ms: int) -> dict:
        room = repository.room(conn, room_id)
        if room is None:
            raise DomainError("room_not_found", "Room not found", 404)
        expiry = (room["last_completed_at_ms"] if room["last_completed_at_ms"] is not None else room["created_at_ms"]) + RETENTION_MS
        if now_ms >= expiry:
            raise DomainError("room_expired", "This room has expired", 410)
        return room

    def resolve_code(self, conn: sqlite3.Connection, code: str, now_ms: int) -> dict:
        if not isinstance(code, str):
            raise DomainError("room_not_found", "Room not found", 404)
        row = repository.room_by_code(conn, code.strip().upper())
        if row is None:
            raise DomainError("room_not_found", "Room not found", 404)
        room = self.room(conn, row["id"], now_ms)
        return {"room_id": room["id"], "code": room["code"], "mode": room["mode"],
                "join_available": room["state"] == "lobby" and len(repository.players(conn, room["id"])) < 10}

    def create(self, conn: sqlite3.Connection, nickname: str, character_id: str, mode: str, now_ms: int) -> dict:
        if mode not in {"demo", "normal"}:
            raise DomainError("invalid_mode", "Choose Normal or Demo")
        if mode == "normal":
            raise DomainError("provider_unavailable", "Normal mode is unavailable until a music provider is connected", 503)
        nickname, nickname_key = _nickname(nickname)
        character_id = _character(character_id)
        room_id = secrets.token_hex(16)
        for _ in range(100):
            code = "".join(secrets.choice(ROOM_ALPHABET) for _ in range(6))
            if repository.room_by_code(conn, code) is None:
                break
        else:
            raise DomainError("room_capacity", "Unable to allocate a room code", 503)
        repository.create_room(conn, room_id, code, mode, now_ms)
        return self._add_player(conn, room_id, nickname, nickname_key, character_id, now_ms, is_host=True)

    def join(self, conn: sqlite3.Connection, room_id: str, nickname: str, character_id: str, now_ms: int) -> dict:
        room = self.room(conn, room_id, now_ms)
        if room["mode"] != "demo":
            raise DomainError("provider_unavailable", "Normal mode requires verified music-provider admission", 503)
        self._require_lobby(room)
        if len(repository.players(conn, room_id)) >= 10:
            raise DomainError("room_full", "This room already has ten players", 409)
        nickname, nickname_key = _nickname(nickname)
        character_id = _character(character_id)
        if repository.nickname_taken(conn, room_id, nickname_key):
            raise DomainError("nickname_taken", "That nickname is already in use", 409)
        return self._add_player(conn, room_id, nickname, nickname_key, character_id, now_ms, is_host=False)

    def _add_player(self, conn, room_id, nickname, nickname_key, character_id, now_ms, *, is_host):
        player_id, token = secrets.token_hex(16), secrets.token_urlsafe(32)
        repository.add_player(
            conn, room_id=room_id, player_id=player_id, nickname=nickname,
            nickname_key=nickname_key, character_id=character_id, music_status="demo",
            token_hash=_token_hash(token), is_host=is_host, now_ms=now_ms,
        )
        demo.assign(conn, room_id, player_id)
        repository.bump_revision(conn, room_id)
        return {"room": repository.room(conn, room_id), "player": repository.player(conn, room_id, player_id), "token": token}

    def authenticate(self, conn: sqlite3.Connection, room_id: str, token: str, now_ms: int) -> dict:
        self.room(conn, room_id, now_ms)
        if not isinstance(token, str) or not token or len(token) > 256:
            raise DomainError("unauthorized", "A valid room session is required", 401)
        player = repository.player_by_token_hash(conn, room_id, _token_hash(token))
        if player is None:
            raise DomainError("unauthorized", "A valid room session is required", 401)
        return player

    def heartbeat(self, conn: sqlite3.Connection, room_id: str, player_id: str, now_ms: int) -> dict:
        room = self.room(conn, room_id, now_ms)
        player = self._player(conn, room_id, player_id)
        if room["state"] == "playing" and player["is_host"] and now_ms >= player["last_seen_at_ms"] + HOST_GRACE_MS:
            raise DomainError("host_expired", "The host's reconnect grace has expired", 409)
        repository.record_heartbeat(conn, room_id, player_id, now_ms)
        return repository.player(conn, room_id, player_id)

    def update_player(self, conn: sqlite3.Connection, room_id: str, player_id: str,
                      nickname: str, character_id: str, now_ms: int) -> dict:
        self._require_lobby(self.room(conn, room_id, now_ms))
        self._player(conn, room_id, player_id)
        nickname, nickname_key = _nickname(nickname)
        character_id = _character(character_id)
        if repository.nickname_taken(conn, room_id, nickname_key, exclude_player_id=player_id):
            raise DomainError("nickname_taken", "That nickname is already in use", 409)
        repository.update_identity(conn, room_id, player_id, nickname, nickname_key, character_id)
        repository.bump_revision(conn, room_id)
        return repository.player(conn, room_id, player_id)

    def remove_player(self, conn: sqlite3.Connection, room_id: str, player_id: str, now_ms: int) -> None:
        self._require_lobby(self.room(conn, room_id, now_ms))
        self._player(conn, room_id, player_id)
        repository.remove_player(conn, room_id, player_id)
        # Unreferenced songs cannot create false listeners or influence later selection.
        repository.prune_unreferenced_songs(conn, room_id)
        repository.bump_revision(conn, room_id)

    def lobby(self, conn: sqlite3.Connection, room_id: str, now_ms: int) -> dict:
        room = self.room(conn, room_id, now_ms)
        counts = repository.song_counts(conn, room_id)
        players = [{"id": p["id"], "nickname": p["nickname"], "character_id": p["character_id"],
                    "is_host": bool(p["is_host"]), "connected": now_ms - p["last_seen_at_ms"] < CONNECTED_MS,
                    "music_status": p["music_status"], "song_count": counts.get(p["id"], 0)}
                   for p in repository.players(conn, room_id)]
        return {"room_id": room_id, "code": room["code"], "mode": room["mode"], "state": room["state"],
                "revision": room["revision"], "players": players,
                "expires_at_ms": (room["last_completed_at_ms"] if room["last_completed_at_ms"] is not None else room["created_at_ms"]) + RETENTION_MS}

    def snapshot(self, conn: sqlite3.Connection, room_id: str) -> dict:
        room = repository.room(conn, room_id)
        if room is None:
            raise DomainError("room_not_found", "Room not found", 404)
        roster = [{"id": p["id"], "player_id": p["id"], "nickname": p["nickname"], "character_id": p["character_id"],
                   "is_host": bool(p["is_host"]), "music_status": p["music_status"], "last_seen_at_ms": p["last_seen_at_ms"]}
                  for p in repository.players(conn, room_id)]
        memberships: dict[str, list] = {}
        for row in repository.song_memberships(conn, room_id):
            memberships.setdefault(row["song_id"], []).append({"player_id": row["player_id"], "familiarity": row["familiarity"]})
        songs = [{"song_key": s["id"], "isrc": s["isrc"], "title": s["title"], "artist": s["artist"],
                  "artists": json.loads(s["artists_json"]), "preview_url": s["preview_url"], "artwork_url": s["artwork_url"],
                  "listeners": memberships.get(s["id"], [])}
                 for s in repository.songs(conn, room_id)]
        if room["mode"] == "demo":
            songs.extend(demo.decoys(conn))
        return {"room_id": room_id, "revision": room["revision"], "mode": room["mode"],
                "host_id": next((p["id"] for p in roster if p["is_host"]), None), "players": roster, "songs": songs}

    def set_state(self, conn: sqlite3.Connection, room_id: str, state: str) -> None:
        if state not in {"lobby", "playing"}:
            raise ValueError("Invalid room state")
        repository.set_state(conn, room_id, state)

    def host_presence(self, conn: sqlite3.Connection, room_id: str, now_ms: int) -> dict:
        self.room(conn, room_id, now_ms)
        row = repository.host(conn, room_id)
        if row is None:
            raise DomainError("host_missing", "This room has no host", 409)
        return {"player_id": row["id"], "connected": now_ms - row["last_seen_at_ms"] < CONNECTED_MS,
                "expires_at_ms": row["last_seen_at_ms"] + HOST_GRACE_MS}

    def bump_revision(self, conn: sqlite3.Connection, room_id: str) -> None:
        repository.bump_revision(conn, room_id)

    def complete(self, conn: sqlite3.Connection, room_id: str, now_ms: int) -> None:
        repository.complete_room(conn, room_id, now_ms)

    def expired_ids(self, conn: sqlite3.Connection, now_ms: int) -> list[str]:
        return repository.expired_room_ids(conn, now_ms, RETENTION_MS)

    def delete(self, conn: sqlite3.Connection, room_id: str) -> None:
        repository.delete_room(conn, room_id)

    @staticmethod
    def _require_lobby(room: dict) -> None:
        if room["state"] != "lobby":
            raise DomainError("room_locked", "Membership and character changes are locked during a game", 409)

    @staticmethod
    def _player(conn, room_id, player_id):
        player = repository.player(conn, room_id, player_id)
        if player is None:
            raise DomainError("unauthorized", "Player is not a member of this room", 401)
        return player
