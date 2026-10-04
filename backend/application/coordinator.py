"""Cross-domain transactions and ordering, without owning room or game rules."""

import json
import time

from backend.application.audio_leases import AudioLeases
from backend.application.launch_mode import LaunchMode
from backend.application.room_locks import RoomLocks
from backend.core.errors import DomainError
from backend.game.service import GameService
from backend.game.views import audio_manifest, game_view
from backend.rooms.demo import seed_demo, validate_pack_assets
from backend.rooms.service import RoomsService
from backend.storage.database import Database

DEFAULT_SETTINGS = {
    "round_count": 10,
    "answer_seconds": 20,
    "difficulty": "mixed",
    "decoys_enabled": True,
}


def now_ms():
    return time.time_ns() // 1_000_000


class Coordinator:
    def __init__(self, config, clock=now_ms, game=None):
        self.config, self.clock = config, clock
        self.launch_mode = LaunchMode(config.game_mode)
        self.db = Database(config.database_path)
        self.rooms = RoomsService(playtest=config.playtest)
        self.game = game or GameService(setup_timeout_ms=config.setup_timeout_ms)
        self.leases = AudioLeases()
        self._locks = RoomLocks()
        self._settings = {}

    def room_lock(self, room_id):
        return self._locks.hold(room_id)

    def initialize(self):
        validate_pack_assets(self.config.demo_pack_dir)
        self.db.initialize()
        with self.db.transaction() as conn:
            seed_demo(conn, self.config.demo_pack_dir / "demo_catalog.json")
            now = self.clock()
            for game in self.game.repo.active(conn):
                self.game.finish(conn, game["id"], now, "server_restart")
                self.rooms.set_state(conn, game["room_id"], "lobby")
        self.leases = AudioLeases()
        self._settings.clear()
        self.cleanup()

    def _reconcile(self, conn, room_id, now):
        latest = self.game.repo.latest(conn, room_id)
        room = self.rooms.room(conn, room_id, now)
        if (
            room["state"] == "playing"
            and latest
            and latest["status"] in ("completed", "aborted")
        ):
            if latest["status"] == "completed":
                self.rooms.complete(conn, room_id, latest["ended_at_ms"])
            else:
                self.rooms.set_state(conn, room_id, "lobby")

    def _advance(self, conn, room_id, now):
        game = self.game.repo.latest(conn, room_id)
        if not game or game["status"] in ("completed", "aborted"):
            return
        presence = self.rooms.host_presence(conn, room_id, now)
        if now >= presence["expires_at_ms"]:
            self.game.finish(conn, game["id"], now, "host_timeout")
        else:
            self.game.advance(
                conn,
                game["id"],
                now,
                presence["connected"],
                host_lease_id=self.leases.active_id(room_id, now),
                connected_player_ids=self.rooms.connected_player_ids(
                    conn, room_id, now
                ),
            )
        self._reconcile(conn, room_id, now)

    def _due(self, conn, room_id, now):
        game = self.game.repo.latest(conn, room_id)
        if not game or game["status"] in ("completed", "aborted"):
            return False
        presence = self.rooms.host_presence(conn, room_id, now)
        if now >= presence["expires_at_ms"]:
            return True
        if game["phase"] == "ready":
            attempt = self.game.repo.current(conn, game["id"])
            if now >= attempt["readiness_deadline_at_ms"]:
                return game["status"] == "preparing"
            return False
        return game["phase_ends_at_ms"] is not None and now >= game["phase_ends_at_ms"]

    def execute(self, room_id, token, operation, write=True):
        with self.room_lock(room_id):
            # Acceptance time is captured upon entering this room's command turn.
            now = self.clock()
            with self.db.read() as conn:
                self.launch_mode.require(self.rooms.room(conn, room_id, now)["mode"])
                player = self.rooms.authenticate(conn, room_id, token, now)
                due = self._due(conn, room_id, now)
                if not due and not write:
                    return operation(conn, player, now)
            if due:
                # Persist elapsed transitions even when the incoming command is invalid.
                with self.db.transaction() as conn:
                    self._advance(conn, room_id, now)
            context = self.db.transaction if write else self.db.read
            with context() as conn:
                player = self.rooms.authenticate(conn, room_id, token, now)
                result = operation(conn, player, now)
                if write:
                    self._reconcile(conn, room_id, now)
                return result

    def admission(self, operation):
        with self.room_lock("admission"), self.db.transaction() as conn:
            return operation(conn, self.clock())

    def settings(self, conn, room_id):
        if room_id in self._settings:
            return dict(self._settings[room_id])
        game = self.game.repo.latest(conn, room_id)
        frozen = json.loads(game["settings_json"]) if game else {}
        return {key: frozen.get(key, value) for key, value in DEFAULT_SETTINGS.items()}

    def change_settings(self, conn, room_id, player, payload, now):
        self.host(player)
        if self.rooms.room(conn, room_id, now)["state"] != "lobby":
            raise DomainError("room_locked", "Settings are locked during a game.", 409)
        settings = {**self.settings(conn, room_id), **payload}
        self.rooms.bump_revision(conn, room_id)
        self._settings[room_id] = settings
        return settings

    @staticmethod
    def host(player):
        if not player["is_host"]:
            raise DomainError("host_required", "Only the host can do this.", 403)

    def state(self, conn, room_id, player, now):
        lobby = self.rooms.lobby(conn, room_id, now)
        latest = self.game.repo.latest(conn, room_id)
        players = lobby["players"]
        if latest and latest["status"] in ("preparing", "playing"):
            connected = {p["id"]: p["connected"] for p in players}
            counts = {p["id"]: p["song_count"] for p in players}
            players = [
                {
                    "id": p["player_id"],
                    "nickname": p["nickname"],
                    "character_id": p["character_id"],
                    "is_host": bool(p["is_host"]),
                    "connected": connected.get(p["player_id"], False),
                    "music_status": "ready" if lobby["mode"] == "normal" else "demo",
                    "song_count": counts.get(p["player_id"], 0),
                }
                for p in self.game.repo.roster(conn, latest["id"])
            ]
        return {
            "server_now_ms": now,
            "room": {
                "id": room_id,
                **{
                    k: lobby[k]
                    for k in (
                        "code",
                        "mode",
                        "state",
                        "revision",
                        "maximum_players",
                        "minimum_players",
                        "playtest",
                    )
                },
                "expires_at_ms": lobby["expires_at_ms"],
            },
            "me": {k: player[k] for k in ("id", "nickname", "character_id", "is_host")},
            "players": players,
            "settings": self.settings(conn, room_id),
            "game": game_view(
                self.game.repo, conn, latest, player["id"], bool(player["is_host"])
            ),
        }

    def start(self, conn, room_id, player, payload, now):
        self.host(player)
        # Accepted duplicate Start must be found before revision/state checks.
        prior = self.game.repo.start_receipt(conn, room_id, payload["request_id"])
        if prior:
            return self.game.retry_receipt(
                conn, prior["id"], player["id"], "start", payload
            )
        if self.rooms.room(conn, room_id, now)["state"] != "lobby":
            raise DomainError("game_active", "A game is already running.", 409)
        self.leases.require(room_id, payload["lease_id"], now)
        snapshot = self.rooms.snapshot(conn, room_id)
        result = self.game.start(
            conn, snapshot, self.settings(conn, room_id), player["id"], payload, now
        )
        self.rooms.set_state(conn, room_id, "playing")
        return result

    def claim_audio(self, conn, room_id, player, payload, now):
        self.host(player)
        lease, displaced = self.leases.claim(
            room_id, payload["tab_id"], payload["takeover"], now
        )
        game = self.game.repo.latest(conn, room_id)
        attempt = self.game.repo.current(conn, game["id"]) if game else None
        if displaced and game and game["status"] in ("preparing", "playing"):
            self.game.invalidate_upcoming_host(conn, game["id"], player["id"])
        if (
            displaced
            and game
            and game["status"] in ("preparing", "playing")
            and attempt
            and attempt["status"] in ("ready", "playing")
        ):
            # Moving playback cannot replay an already exposed clip after refresh.
            failure = {
                "request_id": "takeover-" + lease,
                "readiness_generation": attempt["readiness_generation"],
                "reason": "audio_controller_changed",
            }
            self.game.audio_failure(
                conn, game["id"], attempt["id"], player["id"], failure, now
            )
        return {"lease_id": lease}

    def require_audio(self, room_id, player, lease_id, now):
        self.host(player)
        self.leases.require(room_id, lease_id, now)

    def validate_game_room(self, conn, room_id, game_id):
        game = self.game.repo.game(conn, game_id)
        if not game or game["room_id"] != room_id:
            raise DomainError("game_not_found", "Game not found in this room.", 404)
        return game

    def audio(self, conn, room_id, game_id, player, lease_id, now):
        self.require_audio(room_id, player, lease_id, now)
        game = self.validate_game_room(conn, room_id, game_id)
        return audio_manifest(game)

    def leave(self, conn, room_id, player, payload, now):
        game = self.game.repo.latest(conn, room_id)
        if player["is_host"]:
            if game:
                self.game.end(
                    conn, game["id"], player["id"], payload, now, kind="leave"
                )
            # Preserve the original host credential; it is not transferred.
        elif game and game["status"] in ("preparing", "playing"):
            # Preserve room credential as well as frozen roster for reconnect.
            pass
        else:
            self.rooms.remove_player(conn, room_id, player["id"], now)
        return {"accepted": True}

    def tick(self):
        now = self.clock()
        with self.db.read() as conn:
            ids = [g["room_id"] for g in self.game.repo.active(conn)]
        for room_id in ids:
            with self.room_lock(room_id):
                with self.db.transaction() as conn:
                    try:
                        self.rooms.room(conn, room_id, now)
                    except DomainError as exc:
                        if exc.code == "room_expired":
                            continue
                        raise
                    self._advance(conn, room_id, now)

    def cleanup(self):
        now = self.clock()
        with self.db.read() as conn:
            expired = self.rooms.expired_ids(conn, now)
        for room_id in expired:
            with self.room_lock(room_id), self.db.transaction() as conn:
                if room_id not in self.rooms.expired_ids(conn, now):
                    continue
                self.game.repo.delete_room_games(conn, room_id)
                self.rooms.delete(conn, room_id)
                self._settings.pop(room_id, None)
                self.leases.delete(room_id)
