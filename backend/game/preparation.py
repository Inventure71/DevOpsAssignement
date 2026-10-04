"""Upcoming technical readiness, separate from the active scored round."""

import json
import uuid

from backend.core.errors import DomainError

ACKNOWLEDGEMENT_MAX_AGE_MS = 5000


def next_slot(game, after_number):
    return next(
        (
            slot
            for slot in json.loads(game["round_plan_json"])
            if slot["round_number"] > after_number and not slot.get("skipped")
        ),
        None,
    )


def round_identity(slot, candidate_index):
    candidate = slot["candidates"][candidate_index]
    return {
        "round_number": slot["round_number"],
        "attempt": candidate_index + 1,
        "song_key": candidate["song_key"],
        "difficulty": candidate["difficulty"],
        "picked_player_id": candidate["picked_player_id"],
    }


class RoundPreparations:
    def __init__(self, repository):
        self.repo = repository

    def stage(self, conn, game, after_number):
        slot = next_slot(game, after_number)
        if slot is None:
            self.repo.delete_pending_preparation(conn, game["id"])
            return
        self.repo.save_pending_preparation(
            conn,
            game["id"],
            {
                "id": uuid.uuid4().hex,
                **round_identity(slot, slot["chosen_index"]),
                "readiness_generation": 1,
                "acknowledgements": {},
            },
        )

    def acknowledge(self, conn, game, preparation_id, actor, payload, now):
        pending = self.repo.pending_preparation(conn, game["id"])
        if (
            game["phase"] not in ("reveal", "leaderboard")
            or game["status"] != "playing"
            or pending is None
            or pending["id"] != preparation_id
        ):
            raise DomainError(
                "stale_preparation", "This upcoming preparation is no longer open.", 409
            )
        if payload["readiness_generation"] != pending["readiness_generation"]:
            raise DomainError(
                "stale_generation", "This upcoming preparation has changed.", 409
            )
        pending["acknowledgements"][actor] = {
            "browser_id": payload["browser_id"],
            "lease_id": payload.get("lease_id"),
            "prepared_at_ms": now,
        }
        self.repo.save_pending_preparation(conn, game["id"], pending)
        return {"accepted": True}

    def consume(
        self, conn, game_id, slot, candidate_index, now, host_lease_id, connected_ids
    ):
        pending = self.repo.pending_preparation(conn, game_id)
        self.repo.delete_pending_preparation(conn, game_id)
        expected = round_identity(slot, candidate_index)
        if pending is None or any(
            pending[key] != value for key, value in expected.items()
        ):
            return None
        ready = []
        for player in self.repo.roster(conn, game_id):
            player_id = player["player_id"]
            ack = pending["acknowledgements"].get(player_id)
            if ack is None or not (
                0 <= now - ack["prepared_at_ms"] <= ACKNOWLEDGEMENT_MAX_AGE_MS
            ):
                continue
            if connected_ids is not None and player_id not in connected_ids:
                continue
            if player["is_host"] and (
                not host_lease_id or ack["lease_id"] != host_lease_id
            ):
                continue
            ready.append(player_id)
        return {"id": pending["id"], "ready_player_ids": sorted(ready)}

    def invalidate_host(self, conn, game_id, actor):
        pending = self.repo.pending_preparation(conn, game_id)
        if pending is not None and actor in pending["acknowledgements"]:
            pending["acknowledgements"].pop(actor)
            self.repo.save_pending_preparation(conn, game_id, pending)
