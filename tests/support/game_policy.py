"""Game policy fixture with a constrained repository double and explicit time."""

import json
from copy import deepcopy
from random import Random
from unittest.mock import create_autospec

import pytest

from backend.core.errors import DomainError
from backend.game.repository import GameRepository, encode
from backend.game.service import GameService


@pytest.fixture
def match():
    repo = create_autospec(GameRepository, instance=True)
    games, roster, rounds, answers, receipts = {}, [], [], [], {}
    preparations = {}
    repo.pending_preparation.side_effect = lambda conn, gid: deepcopy(
        preparations.get(gid)
    )

    def save_preparation(conn, gid, record):
        preparations[gid] = deepcopy(record)

    repo.save_pending_preparation.side_effect = save_preparation
    repo.delete_pending_preparation.side_effect = lambda conn, gid: preparations.pop(
        gid, None
    )
    repo.game.side_effect = lambda conn, gid: dict(games[gid]) if gid in games else None
    repo.active.side_effect = lambda conn: [
        dict(g) for g in games.values() if g["status"] in ("preparing", "playing")
    ]
    repo.start_receipt.return_value = None
    repo.receipt.side_effect = lambda conn, gid, rid: receipts.get((gid, rid))
    repo.roster.side_effect = lambda conn, gid: [
        dict(row) for row in roster if row["game_id"] == gid
    ]
    repo.current.side_effect = lambda conn, gid: next(
        (dict(row) for row in reversed(rounds) if row["game_id"] == gid), None
    )
    repo.attempts.side_effect = lambda conn, gid: [
        dict(row) for row in rounds if row["game_id"] == gid
    ]
    repo.answers.side_effect = lambda conn, rid: [
        dict(a) for a in answers if a["round_id"] == rid
    ]

    def insert(conn, table, values):
        row = dict(values)
        if table == "games":
            games[row["id"]] = row
        elif table == "game_players":
            roster.append(row)
        elif table == "rounds":
            row = {
                "starts_at_ms": None,
                "deadline_at_ms": None,
                "readiness_generation": 1,
                "ready_player_ids_json": "[]",
                "excluded_player_ids_json": "[]",
                **row,
            }
            rounds.append(row)
        elif table == "answers":
            answers.append(row)

    repo.insert.side_effect = insert
    repo.update_game.side_effect = lambda conn, gid, **fields: games[gid].update(fields)
    repo.update_round.side_effect = lambda conn, rid, **fields: next(
        r for r in rounds if r["id"] == rid
    ).update(fields)

    def score_answer(conn, rid, actor, points):
        next(
            row
            for row in answers
            if row["round_id"] == rid and row["player_id"] == actor
        )["points"] = points

    repo.score_answer.side_effect = score_answer

    def remember(conn, gid, actor, kind, payload, result, now):
        receipts[gid, payload["request_id"]] = {
            "actor_player_id": actor,
            "command_type": kind,
            "payload_json": encode(payload),
            "result_json": encode(result),
        }

    repo.remember.side_effect = remember
    game = GameService(Random(17), repository=repo)
    players = [
        {
            "id": f"p{i}",
            "nickname": f"Player {i}",
            "character_id": "coral",
            "is_host": i == 0,
        }
        for i in range(3)
    ]
    songs = [
        {
            "song_key": f"song{i}",
            "title": f"Title {i}",
            "artist": "Composer",
            "artists": [{"artist_key": "demo:composer", "name": "Composer"}],
            "listeners": [{"player_id": f"p{i % 3}", "familiarity": "easy"}],
            "preview_url": "/clip",
        }
        for i in range(96)
    ]
    songs += [
        {
            "song_key": f"decoy{i}",
            "title": f"Decoy {i}",
            "artist": "Composer",
            "artists": [{"artist_key": "demo:composer", "name": "Composer"}],
            "listeners": [],
            "preview_url": "/clip",
        }
        for i in range(24)
    ]
    snapshot = {
        "room_id": "room",
        "revision": 3,
        "mode": "demo",
        "host_id": "p0",
        "players": players,
        "songs": songs,
    }
    settings = {
        "round_count": 10,
        "answer_seconds": 20,
        "difficulty": "mixed",
        "decoys_enabled": True,
    }
    payload = {"request_id": "start", "room_revision": 3}
    gid = game.start(None, snapshot, settings, "p0", payload, 1000)["game_id"]
    return game, repo, games[gid], rounds, answers, snapshot


def error(code, operation):
    with pytest.raises(DomainError) as caught:
        operation()
    assert caught.value.code == code


def prepared(match):
    service, _, game, rounds, _, _ = match
    for slot in json.loads(game["round_plan_json"]):
        for candidate in slot["candidates"]:
            service.preload(
                None,
                game["id"],
                "p0",
                {
                    "request_id": candidate["song_key"],
                    "candidate_id": candidate["song_key"],
                    "ok": True,
                },
                1000,
            )
    service.advance(None, game["id"], 6000)
    return rounds[-1]


def answering(match):
    service, _, game, _, _, _ = match
    attempt = prepared(match)
    for actor in ("p0", "p1", "p2"):
        service.ready(None, game["id"], attempt["id"], actor, 1, 6000)
    service.advance(None, game["id"], 9000)
    return attempt
