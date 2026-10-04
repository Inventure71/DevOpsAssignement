"""Named room use cases; HTTP receives values rather than database handles."""

from backend.catalog.selection import CatalogSelections
from backend.core.errors import DomainError


class RoomCommands:
    def __init__(self, coordinator, search):
        self.c, self.search = coordinator, search
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
        return self.c.admission(
            lambda conn, now: self.c.rooms.create(
                conn, payload["nickname"], payload["character_id"], payload["mode"], now
            )
        )

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
        with self.c.room_lock(room_id):

            def admit(conn, now):
                room = self.c.rooms.room(conn, room_id, now)
                self.c.launch_mode.require(room["mode"])
                return self.c.rooms.join(
                    conn, room_id, payload["nickname"], payload["character_id"], now
                )

            admission = self.c.admission(admit)
        return self.admission_result(admission), admission

    @staticmethod
    def admission_result(admission):
        return {
            "room_id": admission["room"]["id"],
            "code": admission["room"]["code"],
            "player_id": admission["player"]["id"],
        }

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
        return self.c.execute(
            room_id,
            token,
            lambda conn, actor, now: self.c.leave(conn, room_id, actor, payload, now),
        )

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
                    "Demo rooms do not require Spotify sign-in.",
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
