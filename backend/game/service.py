"""Game commands over frozen values, independent of live room membership."""

import json
import random
import uuid

from backend.core.errors import DomainError
from backend.game.preparation import RoundPreparations, next_slot, round_identity
from backend.game.repository import GameRepository, encode
from backend.game.scoring import score_answer
from backend.game.selection import prepare_plan, skip_limit_exceeded


class GameService:
    def __init__(self, rng=None, setup_timeout_ms=60_000, repository=None):
        self.repo = repository if repository is not None else GameRepository()
        self.rng = rng or random.Random()
        self.setup_timeout_ms = setup_timeout_ms
        self.preparations = RoundPreparations(self.repo)

    def advance(
        self,
        conn,
        game_id,
        now,
        host_connected=True,
        *,
        host_lease_id=None,
        connected_player_ids=None,
    ):
        for _ in range(64):
            game = self.repo.game(conn, game_id)
            if game["status"] in ("completed", "aborted"):
                return
            phase = game["phase"]
            if phase == "setup":
                if now < game["phase_ends_at_ms"]:
                    return
                plan = json.loads(game["round_plan_json"])
                candidates = [c["song_key"] for s in plan for c in s["candidates"]]
                checked = sum(len(s["checks"]) for s in plan)
                if (
                    checked < len(candidates)
                    and now < game["started_at_ms"] + self.setup_timeout_ms
                ):
                    return
                if checked < len(candidates):
                    self.finish(conn, game_id, now, "host_preparation_timeout")
                    return
                if not host_connected:
                    return
                for slot in plan:
                    for c in slot["candidates"]:
                        slot["checks"].setdefault(c["song_key"], False)
                    slot["chosen_index"] = next(
                        (
                            i
                            for i, c in enumerate(slot["candidates"])
                            if slot["checks"][c["song_key"]]
                        ),
                        None,
                    )
                    slot["skipped"] = slot["chosen_index"] is None
                self.repo.update_game(
                    conn, game_id, prepared_at_ms=now, round_plan_json=encode(plan)
                )
                if skip_limit_exceeded(
                    sum(s["skipped"] for s in plan),
                    json.loads(game["settings_json"])["round_count"],
                ):
                    self.finish(conn, game_id, now, "too_many_skipped")
                    return
                self._next(conn, self.repo.game(conn, game_id), 0, now)
            elif phase == "ready":
                attempt = self.repo.current(conn, game_id)
                if now >= attempt["readiness_deadline_at_ms"]:
                    if game["status"] == "preparing":
                        self.finish(conn, game_id, now, "initial_readiness_timeout")
                    return
                if host_connected:
                    self._schedule(conn, game_id, now)
                if self.repo.game(conn, game_id)["phase"] == "ready":
                    return
            elif phase == "countdown":
                attempt = self.repo.current(conn, game_id)
                if now < attempt["starts_at_ms"]:
                    return
                self.repo.update_round(conn, attempt["id"], status="playing")
                self.repo.update_game(
                    conn,
                    game_id,
                    phase="answering",
                    phase_ends_at_ms=attempt["deadline_at_ms"],
                )
            elif phase == "answering":
                attempt = self.repo.current(conn, game_id)
                if now < attempt["deadline_at_ms"]:
                    return
                self._close(conn, game, attempt, attempt["deadline_at_ms"])
            elif phase == "reveal":
                if now < game["phase_ends_at_ms"]:
                    return
                self.repo.update_game(
                    conn,
                    game_id,
                    phase="leaderboard",
                    phase_ends_at_ms=game["phase_ends_at_ms"] + 5000,
                )
            elif phase == "leaderboard":
                if now < game["phase_ends_at_ms"]:
                    return
                attempt = self.repo.current(conn, game_id)
                has_next = any(
                    s["round_number"] > attempt["round_number"] and not s.get("skipped")
                    for s in json.loads(game["round_plan_json"])
                )
                if has_next and not host_connected:
                    return
                self._next(
                    conn,
                    game,
                    attempt["round_number"],
                    now,
                    host_lease_id=host_lease_id,
                    connected_player_ids=connected_player_ids,
                )
            else:
                return
        raise RuntimeError("Game transition bound exceeded")

    def start(self, conn, snapshot, settings, actor, payload, now):
        old = self.repo.start_receipt(conn, snapshot["room_id"], payload["request_id"])
        if old:
            return self.retry_receipt(conn, old["id"], actor, "start", payload)
        if actor != snapshot["host_id"]:
            raise DomainError("host_required", "Only the host can start.", 403)
        if snapshot["revision"] != payload["room_revision"]:
            raise DomainError(
                "stale_revision", "The lobby changed. Refresh and try again.", 409
            )
        minimum, maximum = (
            snapshot.get("minimum_players", 3),
            snapshot.get("maximum_players", 10),
        )
        if not minimum <= len(snapshot["players"]) <= maximum:
            raise DomainError(
                "player_count", f"A game needs {minimum}–{maximum} players."
            )
        if any(
            sum(
                any(l["player_id"] == p["id"] for l in s["listeners"])
                for s in snapshot["songs"]
            )
            < 10
            for p in snapshot["players"]
        ):
            raise DomainError(
                "insufficient_songs", "Every player needs at least ten songs."
            )
        if any(g["room_id"] == snapshot["room_id"] for g in self.repo.active(conn)):
            raise DomainError("game_active", "A game is already running.", 409)
        plan = prepare_plan(
            snapshot["songs"],
            snapshot["players"],
            settings["round_count"],
            self.rng,
            difficulty=settings.get("difficulty", "mixed"),
            decoys=settings.get("decoys_enabled", True),
        )
        for slot in plan:
            slot["checks"] = {}
        game_id = uuid.uuid4().hex
        self.repo.insert(
            conn,
            "games",
            {
                "id": game_id,
                "room_id": snapshot["room_id"],
                "room_revision": snapshot["revision"],
                "start_request_id": payload["request_id"],
                "status": "preparing",
                "phase": "setup",
                "settings_json": encode(
                    {
                        **settings,
                        "mode": snapshot["mode"],
                        "playtest": snapshot.get("playtest", False),
                    }
                ),
                "songs_snapshot_json": encode(snapshot["songs"]),
                "round_plan_json": encode(plan),
                "started_at_ms": now,
                "phase_ends_at_ms": now + 5000,
            },
        )
        for p in snapshot["players"]:
            self.repo.insert(
                conn,
                "game_players",
                {
                    "game_id": game_id,
                    "player_id": p["id"],
                    "nickname": p["nickname"],
                    "character_id": p["character_id"],
                    "is_host": p["is_host"],
                },
            )
        result = {"game_id": game_id}
        self.repo.remember(conn, game_id, actor, "start", payload, result, now)
        return result

    def retry_receipt(self, conn, game_id, actor, kind, payload):
        old = self.repo.receipt(conn, game_id, payload["request_id"])
        if old is None:
            return None
        if (
            old["actor_player_id"] != actor
            or old["command_type"] != kind
            or old["payload_json"] != encode(payload)
        ):
            raise DomainError(
                "request_conflict", "This request ID was already used differently.", 409
            )
        return json.loads(old["result_json"])

    def require_game(self, conn, game_id, actor, host=False):
        game = self.repo.game(conn, game_id)
        roster = self.repo.roster(conn, game_id)
        player = next((p for p in roster if p["player_id"] == actor), None)
        if not game or not player:
            raise DomainError("game_not_found", "Game not found for this player.", 404)
        if host and not player["is_host"]:
            raise DomainError("host_required", "Only the host can do this.", 403)
        return game

    def require_round(self, conn, game_id, round_id, generation=None):
        current = self.repo.current(conn, game_id)
        if not current or current["id"] != round_id:
            raise DomainError(
                "stale_attempt", "This round attempt is no longer current.", 409
            )
        if generation is not None and current["readiness_generation"] != generation:
            raise DomainError(
                "stale_generation", "The readiness check has been retried.", 409
            )
        return current

    def preload(self, conn, game_id, actor, payload, now):
        game = self.require_game(conn, game_id, actor, host=True)
        result = self.retry_receipt(conn, game_id, actor, "preload_check", payload)
        if result is not None:
            return result
        if game["phase"] != "setup":
            raise DomainError("setup_closed", "Preparation has already finished.", 409)
        plan = json.loads(game["round_plan_json"])
        slot = next(
            (
                s
                for s in plan
                if any(
                    c["song_key"] == payload["candidate_id"] for c in s["candidates"]
                )
            ),
            None,
        )
        if slot is None:
            raise DomainError(
                "unknown_candidate", "Candidate was not issued for this game."
            )
        old = slot["checks"].get(payload["candidate_id"])
        if old is not None and old != payload["ok"]:
            raise DomainError(
                "check_final", "A preparation outcome is already recorded.", 409
            )
        slot["checks"][payload["candidate_id"]] = payload["ok"]
        if payload["ok"] and payload.get("waveform") is not None:
            slot.setdefault("waveforms", {})[payload["candidate_id"]] = payload[
                "waveform"
            ]
        self.repo.update_game(conn, game_id, round_plan_json=encode(plan))
        result = {"accepted": True}
        self.repo.remember(conn, game_id, actor, "preload_check", payload, result, now)
        return result

    def ready(
        self, conn, game_id, round_id, actor, generation, now, host_connected=True
    ):
        game = self.require_game(conn, game_id, actor)
        attempt = self.require_round(conn, game_id, round_id, generation)
        if actor in json.loads(attempt["ready_player_ids_json"]):
            return {"accepted": True}
        if game["phase"] != "ready" or now >= attempt["readiness_deadline_at_ms"]:
            raise DomainError(
                "readiness_closed", "The readiness window is closed.", 409
            )
        ids = set(json.loads(attempt["ready_player_ids_json"]))
        ids.add(actor)
        self.repo.update_round(
            conn, round_id, ready_player_ids_json=encode(sorted(ids))
        )
        self.repo.update_game(conn, game_id, phase="ready")
        if host_connected:
            self._schedule(conn, game_id, now)
        return {"accepted": True}

    def prepare_upcoming(self, conn, game_id, preparation_id, actor, payload, now):
        game = self.require_game(conn, game_id, actor)
        return self.preparations.acknowledge(
            conn, game, preparation_id, actor, payload, now
        )

    def invalidate_upcoming_host(self, conn, game_id, actor):
        self.require_game(conn, game_id, actor, host=True)
        self.preparations.invalidate_host(conn, game_id, actor)

    def _schedule(self, conn, game_id, now):
        game = self.repo.game(conn, game_id)
        attempt = self.repo.current(conn, game_id)
        required = {p["player_id"] for p in self.repo.roster(conn, game_id)} - set(
            json.loads(attempt["excluded_player_ids_json"])
        )
        if not required.issubset(set(json.loads(attempt["ready_player_ids_json"]))):
            return
        starts = now + 3000
        settings = json.loads(game["settings_json"])
        self.repo.update_round(
            conn,
            attempt["id"],
            starts_at_ms=starts,
            deadline_at_ms=starts + settings["answer_seconds"] * 1000,
        )
        self.repo.update_game(
            conn, game_id, status="playing", phase="countdown", phase_ends_at_ms=starts
        )

    def readiness_command(self, conn, game_id, round_id, actor, kind, payload, now):
        game = self.require_game(conn, game_id, actor, host=True)
        result = self.retry_receipt(conn, game_id, actor, kind, payload)
        if result is not None:
            return result
        attempt = self.require_round(
            conn, game_id, round_id, payload["readiness_generation"]
        )
        if (
            game["status"] != "playing"
            or game["phase"] != "ready"
            or now < attempt["readiness_deadline_at_ms"]
        ):
            raise DomainError(
                "recovery_unavailable",
                "Recovery is available after a later readiness timeout.",
                409,
            )
        if kind == "retry":
            self.repo.update_round(
                conn,
                round_id,
                readiness_generation=attempt["readiness_generation"] + 1,
                readiness_deadline_at_ms=now + 10_000,
                ready_player_ids_json="[]",
                excluded_player_ids_json="[]",
            )
        else:
            ready = set(json.loads(attempt["ready_player_ids_json"]))
            roster = self.repo.roster(conn, game_id)
            excluded = set(payload["exclude_player_ids"])
            permitted = {p["player_id"] for p in roster if not p["is_host"]} - ready
            if (
                not excluded
                or excluded != permitted
                or len(payload["exclude_player_ids"]) != len(excluded)
            ):
                raise DomainError(
                    "invalid_exclusion",
                    "Continue must name every currently unready non-host player.",
                )
            if actor not in ready:
                raise DomainError(
                    "host_not_ready", "The host audio must be ready.", 409
                )
            self.repo.update_round(
                conn, round_id, excluded_player_ids_json=encode(sorted(excluded))
            )
            self._schedule(conn, game_id, now)
        self.repo.update_game(
            conn, game_id, phase=self.repo.game(conn, game_id)["phase"]
        )
        result = {"accepted": True}
        self.repo.remember(conn, game_id, actor, kind, payload, result, now)
        return result

    def answer(self, conn, game_id, round_id, actor, payload, now):
        game = self.require_game(conn, game_id, actor)
        old = next(
            (a for a in self.repo.answers(conn, round_id) if a["player_id"] == actor),
            None,
        )
        who = sorted(payload["who_player_ids"])
        if old:
            if (
                old["status"] == "submitted"
                and json.loads(old["song_guess_json"]) == payload["song_guess"]
                and json.loads(old["who_player_ids_json"]) == who
            ):
                return {"accepted": True, "received_at_ms": old["received_at_ms"]}
            raise DomainError("answer_final", "Your answer is already final.", 409)
        attempt = self.require_round(conn, game_id, round_id)
        if (
            game["phase"] != "answering"
            or not attempt["starts_at_ms"] <= now < attempt["deadline_at_ms"]
        ):
            raise DomainError(
                "answer_window_closed", "The answer window is closed.", 409
            )
        if payload.get("_token_expires_ms", now + 1) <= now:
            raise DomainError(
                "song_selection_expired", "Search for the song again before submitting."
            )
        roster_ids = {p["player_id"] for p in self.repo.roster(conn, game_id)}
        if len(who) != len(set(who)) or not set(who).issubset(roster_ids):
            raise DomainError(
                "invalid_listeners", "Select each starting player at most once."
            )
        self.repo.insert(
            conn,
            "answers",
            {
                "game_id": game_id,
                "round_id": round_id,
                "player_id": actor,
                "status": "submitted",
                "song_guess_json": encode(payload["song_guess"]),
                "who_mode": "players" if who else "nobody",
                "who_player_ids_json": encode(who),
                "received_at_ms": now,
            },
        )
        self.repo.update_game(conn, game_id, phase="answering")
        if len(self.repo.answers(conn, round_id)) == len(roster_ids):
            self._close(conn, game, attempt, now)
        return {"accepted": True, "received_at_ms": now}

    def _close(self, conn, game, attempt, now):
        songs = {s["song_key"]: s for s in json.loads(game["songs_snapshot_json"])}
        song = songs[attempt["song_key"]]
        answers = {a["player_id"]: a for a in self.repo.answers(conn, attempt["id"])}
        for player in self.repo.roster(conn, game["id"]):
            answer = answers.get(player["player_id"])
            if answer is None:
                self.repo.insert(
                    conn,
                    "answers",
                    {
                        "game_id": game["id"],
                        "round_id": attempt["id"],
                        "player_id": player["player_id"],
                        "status": "missing",
                        "song_guess_json": "null",
                        "who_mode": "blank",
                        "who_player_ids_json": "[]",
                        "points": 0,
                    },
                )
            else:
                points = score_answer(
                    song,
                    json.loads(answer["song_guess_json"]),
                    json.loads(answer["who_player_ids_json"]),
                    answer["received_at_ms"] - attempt["starts_at_ms"],
                    attempt["deadline_at_ms"] - attempt["starts_at_ms"],
                    attempt["difficulty"],
                )
                self.repo.score_answer(conn, attempt["id"], player["player_id"], points)
        self.repo.update_round(
            conn, attempt["id"], status="revealed", revealed_at_ms=now
        )
        self.repo.update_game(
            conn, game["id"], phase="reveal", phase_ends_at_ms=now + 5000
        )
        self.preparations.stage(conn, game, attempt["round_number"])

    def activate(self, conn, game_id, slot, candidate_index, now, *, preparation=None):
        self.repo.insert(
            conn,
            "rounds",
            {
                "id": preparation["id"] if preparation else uuid.uuid4().hex,
                "game_id": game_id,
                **round_identity(slot, candidate_index),
                "status": "ready",
                "readiness_deadline_at_ms": now + 10_000,
                "ready_player_ids_json": encode(
                    preparation["ready_player_ids"] if preparation else []
                ),
            },
        )
        self.repo.update_game(conn, game_id, phase="ready", phase_ends_at_ms=None)

    def audio_failure(self, conn, game_id, round_id, actor, payload, now):
        game = self.require_game(conn, game_id, actor, host=True)
        result = self.retry_receipt(conn, game_id, actor, "audio_failure", payload)
        if result is not None:
            return result
        attempt = self.require_round(
            conn, game_id, round_id, payload["readiness_generation"]
        )
        if attempt["status"] not in ("ready", "playing") or game["status"] not in (
            "preparing",
            "playing",
        ):
            raise DomainError(
                "reveal_final", "A revealed or ended attempt cannot be changed.", 409
            )
        self.repo.update_round(
            conn,
            round_id,
            status="void",
            void_reason=payload.get("reason", "audio_failed"),
        )
        plan = json.loads(game["round_plan_json"])
        slot = next(s for s in plan if s["round_number"] == attempt["round_number"])
        following = next(
            (
                i
                for i, c in enumerate(slot["candidates"])
                if i >= attempt["attempt"] and slot["checks"].get(c["song_key"]) is True
            ),
            None,
        )
        if following is not None:
            self.activate(conn, game_id, slot, following, now)
        else:
            skipped = self.skipped(conn, game_id)
            if skip_limit_exceeded(
                skipped, json.loads(game["settings_json"])["round_count"]
            ):
                self.finish(conn, game_id, now, "too_many_skipped", completed=False)
            else:
                self._next(conn, game, attempt["round_number"], now)
        result = {"accepted": True, "void_round_id": round_id}
        self.repo.remember(conn, game_id, actor, "audio_failure", payload, result, now)
        return result

    def skipped(self, conn, game_id):
        game = self.repo.game(conn, game_id)
        plan = json.loads(game["round_plan_json"])
        skipped = {s["round_number"] for s in plan if s.get("skipped")}
        latest = {}
        for r in self.repo.attempts(conn, game_id):
            latest[r["round_number"]] = r
        skipped.update(n for n, r in latest.items() if r["status"] == "void")
        return len(skipped)

    def _next(
        self,
        conn,
        game,
        after_number,
        now,
        *,
        host_lease_id=None,
        connected_player_ids=None,
    ):
        slot = next_slot(game, after_number)
        if slot is None:
            self.finish(conn, game["id"], now, "completed", completed=True)
        else:
            preparation = self.preparations.consume(
                conn,
                game["id"],
                slot,
                slot["chosen_index"],
                now,
                host_lease_id,
                connected_player_ids,
            )
            self.activate(
                conn,
                game["id"],
                slot,
                slot["chosen_index"],
                now,
                preparation=preparation,
            )

    def finish(self, conn, game_id, now, reason, completed=False):
        game = self.repo.game(conn, game_id)
        self.repo.delete_pending_preparation(conn, game_id)
        if game["status"] in ("completed", "aborted"):
            return
        for attempt in self.repo.attempts(conn, game_id):
            if attempt["status"] in ("ready", "playing"):
                self.repo.update_round(
                    conn, attempt["id"], status="void", void_reason=reason
                )
        self.repo.save_ranks(conn, game_id)
        self.repo.update_game(
            conn,
            game_id,
            status="completed" if completed else "aborted",
            phase="finished",
            phase_ends_at_ms=None,
            ended_at_ms=now,
            end_reason=reason,
        )

    def end(self, conn, game_id, actor, payload, now, kind="end"):
        self.require_game(conn, game_id, actor, host=True)
        result = self.retry_receipt(conn, game_id, actor, kind, payload)
        if result is not None:
            return result
        self.finish(
            conn, game_id, now, "host_left" if kind == "leave" else "host_ended"
        )
        result = {"accepted": True}
        self.repo.remember(conn, game_id, actor, kind, payload, result, now)
        return result
