"""Room use cases and cross-domain command ordering."""

from backend.application.music_admission import MusicAdmissionHandler
from backend.catalog.selection import CatalogSelections
from backend.core.errors import DomainError


class RoomCommands:
    def __init__(self, coordinator, search, admission_handler=None, on_leave=None):
        self.c, self.search = coordinator, search
        self.on_leave = on_leave
        self.admission_handler = admission_handler or MusicAdmissionHandler(coordinator)
        self.selections = CatalogSelections(
            search.tokens,
            search.provider_results,
            search.result,
            links=search.store.links if search.store else None,
            scope=search.provider_scope,
            clock=search.clock,
        )

    def create(self, payload):
        self.c.launch_mode.require(payload["mode"])
        if payload["mode"] != "demo":
            raise DomainError(
                "music_sign_in_required",
                "Connect your music to create a Real room.",
                409,
            )
        with self.c.db.read() as conn:
            self.c.rooms.check_admission(
                conn, payload["nickname"], payload["character_id"], self.c.clock()
            )
        imported = self.c.prepare_demo_import()
        return self.admission_handler(payload, imported, lambda: True)

    def resolve(self, code):
        with self.c.db.read() as conn:
            result = self.c.rooms.resolve_code(conn, code, self.c.clock())
            result["join_available"] = result["join_available"] and (
                self.c.launch_mode.available(result["mode"])
            )
            return result

    def history(self, code):
        with self.c.db.read() as conn:
            room = self.c.rooms.resolve_code(conn, code, self.c.clock())
            return {"games": self.c.game.repo.history(conn, room["room_id"])}

    def join(self, room_id, token, payload):
        if token:

            def existing(conn, actor, now):
                room = self.c.rooms.room(conn, room_id, now)
                return {
                    "room_id": room_id,
                    "code": room["code"],
                    "player_id": actor["id"],
                }

            try:
                return self.c.execute(room_id, token, existing, write=False), None
            except DomainError as exc:
                if exc.code != "unauthorized":
                    raise
        with self.c.db.read() as conn:
            room = self.c.rooms.check_admission(
                conn,
                payload["nickname"],
                payload["character_id"],
                self.c.clock(),
                room_id=room_id,
            )
            self.c.launch_mode.require(room["mode"])
        if room["mode"] != "demo":
            raise DomainError(
                "music_sign_in_required",
                "Connect your music before joining this Real room.",
                409,
            )
        imported = self.c.prepare_demo_import(include_decoys=False)
        admission = self.admission_handler(
            payload | {"room_id": room_id, "mode": "demo"}, imported, lambda: True
        )
        return self.admission_result(admission), admission

    @staticmethod
    def admission_result(admission):
        return {
            "room_id": admission["room"]["id"],
            "code": admission["room"]["code"],
            "player_id": admission["player"]["id"],
        }

    def music_session_valid(self, admission):
        """A completed receipt may deliver only a still-valid room membership."""
        try:
            return self.c.execute(
                admission["room"]["id"],
                admission["token"],
                lambda conn, actor, now: True,
                write=False,
            )
        except DomainError as error:
            if error.code in {
                "room_expired",
                "unauthorized",
                "room_not_found",
                "mode_unavailable",
            }:
                return False
            raise

    def state(self, room_id, token):
        return self.c.execute(
            room_id,
            token,
            lambda conn, actor, now: self.c.state(conn, room_id, actor, now),
            write=False,
        )

    def search_songs(self, room_id, token, query, *, local_first=False):
        def context(conn, actor, now):
            room = self.c.rooms.room(conn, room_id, now)
            fixtures = (
                self.c.rooms.search_fixtures(conn) if room["mode"] == "demo" else []
            )
            return fixtures, room["mode"] == "demo", now

        fixtures, demo, now = self.c.execute(room_id, token, context, write=False)
        # Slow external I/O runs after room serialization and the DB read end.
        return self.search.search(
            room_id,
            query,
            now,
            fixtures=fixtures,
            local_first=local_first,
            fixtures_only=demo,
        )

    def resolve_selection(self, room_id, token, selection):
        now = self.c.execute(room_id, token, lambda conn, actor, now: now, write=False)
        return self.selections.resolve(room_id, selection, now)

    def heartbeat(self, room_id, token):
        def operation(conn, actor, now):
            self.c.rooms.heartbeat(conn, room_id, actor["id"], now)
            return {"accepted": True, "server_now_ms": now}

        return self.c.execute(room_id, token, operation)

    def update_player(self, room_id, token, payload):
        def operation(conn, actor, now):
            updated = self.c.rooms.update_player(
                conn,
                room_id,
                actor["id"],
                payload["nickname"],
                payload["character_id"],
                now,
            )
            return {key: updated[key] for key in ("id", "nickname", "character_id")}

        return self.c.execute(room_id, token, operation)

    def settings(self, room_id, token, payload):
        return self.c.execute(
            room_id,
            token,
            lambda conn, actor, now: self.c.change_settings(
                conn, room_id, actor, payload, now
            ),
        )

    def leave(self, room_id, token, payload):
        def operation(conn, actor, now):
            return self.c.leave(conn, room_id, actor, payload, now), actor["id"]

        result, player_id = self.c.execute(
            room_id,
            token,
            operation,
        )
        # Call after releasing the room lock; completion takes receipt then room.
        if self.on_leave:
            self.on_leave(room_id, player_id)
        return result

    def check_music_admission(self, payload):
        self.c.launch_mode.require("normal")
        with self.c.db.read() as conn:
            room = self.c.rooms.check_admission(
                conn,
                payload["nickname"],
                payload["character_id"],
                self.c.clock(),
                room_id=payload.get("room_id"),
            )
            if room and room["mode"] != "normal":
                raise DomainError(
                    "invalid_music_room",
                    "Demo rooms do not require a music account.",
                    409,
                )


class GameCommands:
    def __init__(self, coordinator, tokens):
        self.c, self.tokens = coordinator, tokens

    def start(self, room_id, token, payload):
        return self.c.execute(
            room_id,
            token,
            lambda conn, actor, now: self.c.start(conn, room_id, actor, payload, now),
        )

    def claim_audio(self, room_id, token, payload):
        return self.c.execute(
            room_id,
            token,
            lambda conn, actor, now: self.c.claim_audio(
                conn, room_id, actor, payload, now
            ),
        )

    def audio(self, room_id, token, game_id, lease_id):
        return self.c.execute(
            room_id,
            token,
            lambda conn, actor, now: self.c.audio(
                conn, room_id, game_id, actor, lease_id, now
            ),
            write=False,
        )

    def _execute(self, room_id, token, game_id, operation):
        def scoped(conn, actor, now):
            self.c.validate_game_room(conn, room_id, game_id)
            return operation(conn, actor, now)

        return self.c.execute(room_id, token, scoped)

    def preload(self, room_id, token, game_id, payload):
        def operation(conn, actor, now):
            self.c.require_audio(room_id, actor, payload["lease_id"], now)
            return self.c.game.preload(conn, game_id, actor["id"], payload, now)

        return self._execute(room_id, token, game_id, operation)

    def end(self, room_id, token, game_id, payload):
        return self._execute(
            room_id,
            token,
            game_id,
            lambda conn, actor, now: self.c.game.end(
                conn, game_id, actor["id"], payload, now
            ),
        )

    def prepare_upcoming(self, room_id, token, game_id, preparation_id, payload):
        def operation(conn, actor, now):
            if actor["is_host"]:
                self.c.require_audio(room_id, actor, payload["lease_id"], now)
            return self.c.game.prepare_upcoming(
                conn, game_id, preparation_id, actor["id"], payload, now
            )

        return self._execute(room_id, token, game_id, operation)

    def ready(self, room_id, token, game_id, round_id, payload):
        def operation(conn, actor, now):
            if actor["is_host"]:
                self.c.require_audio(room_id, actor, payload["lease_id"], now)
            connected = self.c.rooms.host_presence(conn, room_id, now)["connected"]
            return self.c.game.ready(
                conn,
                game_id,
                round_id,
                actor["id"],
                payload["readiness_generation"],
                now,
                connected,
            )

        return self._execute(room_id, token, game_id, operation)

    def answer(self, room_id, token, game_id, round_id, payload):
        def operation(conn, actor, now):
            values = {"song_guess": None, "who_player_ids": payload["who_player_ids"]}
            if payload["song_guess_token"] is not None:
                values["song_guess"], values["_token_expires_ms"] = self.tokens.decode(
                    payload["song_guess_token"], room_id
                )
                if values["song_guess"].get("_catalog_reference"):
                    raise DomainError(
                        "song_selection_unresolved",
                        "Select the song again before submitting.",
                        409,
                    )
            return self.c.game.answer(conn, game_id, round_id, actor["id"], values, now)

        return self._execute(room_id, token, game_id, operation)

    def recover(self, room_id, token, game_id, round_id, payload, kind):
        return self._execute(
            room_id,
            token,
            game_id,
            lambda conn, actor, now: self.c.game.readiness_command(
                conn, game_id, round_id, actor["id"], kind, payload, now
            ),
        )

    def audio_failure(self, room_id, token, game_id, round_id, payload):
        def operation(conn, actor, now):
            self.c.require_audio(room_id, actor, payload["lease_id"], now)
            return self.c.game.audio_failure(
                conn, game_id, round_id, actor["id"], payload, now
            )

        return self._execute(room_id, token, game_id, operation)
