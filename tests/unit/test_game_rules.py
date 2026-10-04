"""Game policy against repository doubles; clocks/randomness are explicit."""

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


def test_start_freezes_values_and_rejects_invalid_host_revision_count_and_pool(match):
    service, repo, game, _, _, snapshot = match
    frozen = json.loads(game["songs_snapshot_json"])
    snapshot["songs"][0]["title"] = "Changed after Start"
    assert frozen[0]["title"] == "Title 0"
    payload = {"request_id": "again", "room_revision": 3}
    settings = {"round_count": 10, "answer_seconds": 20}
    error(
        "host_required",
        lambda: service.start(None, snapshot, settings, "p1", payload, 1000),
    )
    error(
        "stale_revision",
        lambda: service.start(
            None, snapshot, settings, "p0", payload | {"room_revision": 2}, 1000
        ),
    )
    error(
        "player_count",
        lambda: service.start(
            None,
            snapshot | {"players": snapshot["players"][:2]},
            settings,
            "p0",
            payload,
            1000,
        ),
    )
    error(
        "insufficient_songs",
        lambda: service.start(
            None, snapshot | {"songs": []}, settings, "p0", payload, 1000
        ),
    )
    error(
        "game_active",
        lambda: service.start(None, snapshot, settings, "p0", payload, 1000),
    )
    repo.start_receipt.return_value = {"id": game["id"]}
    assert service.start(
        None,
        snapshot,
        settings,
        "p0",
        {"request_id": "start", "room_revision": 3},
        5000,
    ) == {"game_id": game["id"]}
    error(
        "request_conflict",
        lambda: service.retry_receipt(
            None, game["id"], "p1", "start", {"request_id": "start", "room_revision": 3}
        ),
    )


def test_setup_checks_are_final_idempotent_and_require_issued_candidate(match):
    service, _, game, _, _, _ = match
    candidate = json.loads(game["round_plan_json"])[0]["candidates"][0]["song_key"]
    payload = {
        "request_id": "check",
        "candidate_id": candidate,
        "ok": True,
        "waveform": [0.2],
    }
    assert service.preload(None, game["id"], "p0", payload, 1000) == {"accepted": True}
    assert service.preload(None, game["id"], "p0", payload, 1001) == {"accepted": True}
    error(
        "check_final",
        lambda: service.preload(
            None, game["id"], "p0", payload | {"request_id": "other", "ok": False}, 1001
        ),
    )
    error(
        "unknown_candidate",
        lambda: service.preload(
            None,
            game["id"],
            "p0",
            payload | {"request_id": "unknown", "candidate_id": "unknown"},
            1001,
        ),
    )
    error(
        "host_required", lambda: service.preload(None, game["id"], "p1", payload, 1000)
    )
    error("game_not_found", lambda: service.require_game(None, game["id"], "unknown"))
    service.advance(None, game["id"], 5999)
    assert game["phase"] == "setup"
    service.advance(None, game["id"], 61000)
    assert game["end_reason"] == "host_preparation_timeout"
    service.advance(None, game["id"], 62000)


def test_readiness_requires_every_player_and_exact_generation_and_deadline(match):
    service, _, game, _, _, _ = match
    attempt = prepared(match)
    error(
        "setup_closed",
        lambda: service.preload(
            None,
            game["id"],
            "p0",
            {"request_id": "late", "candidate_id": "x", "ok": True},
            6001,
        ),
    )
    error(
        "stale_attempt", lambda: service.ready(None, game["id"], "old", "p0", 1, 6000)
    )
    error(
        "stale_generation",
        lambda: service.ready(None, game["id"], attempt["id"], "p0", 2, 6000),
    )
    service.ready(None, game["id"], attempt["id"], "p0", 1, 6000)
    assert game["phase"] == "ready"
    assert service.ready(None, game["id"], attempt["id"], "p0", 1, 6000) == {
        "accepted": True
    }
    error(
        "readiness_closed",
        lambda: service.ready(
            None,
            game["id"],
            attempt["id"],
            "p1",
            1,
            attempt["readiness_deadline_at_ms"],
        ),
    )
    service.advance(None, game["id"], attempt["readiness_deadline_at_ms"])
    assert game["end_reason"] == "initial_readiness_timeout"


def test_answers_enforce_window_listener_identity_expiry_finality_and_close_once(match):
    service, repo, game, _, answers, _ = match
    attempt = answering(match)
    song = next(
        s
        for s in json.loads(game["songs_snapshot_json"])
        if s["song_key"] == attempt["song_key"]
    )
    payload = {
        "song_guess": song,
        "who_player_ids": [x["player_id"] for x in song["listeners"]],
    }
    error(
        "answer_window_closed",
        lambda: service.answer(None, game["id"], attempt["id"], "p0", payload, 8999),
    )
    error(
        "answer_window_closed",
        lambda: service.answer(None, game["id"], attempt["id"], "p0", payload, 29000),
    )
    error(
        "song_selection_expired",
        lambda: service.answer(
            None,
            game["id"],
            attempt["id"],
            "p0",
            payload | {"_token_expires_ms": 9000},
            9000,
        ),
    )
    for selected in (["unknown"], ["p0", "p0"]):
        error(
            "invalid_listeners",
            lambda: service.answer(
                None,
                game["id"],
                attempt["id"],
                "p0",
                payload | {"who_player_ids": selected},
                9000,
            ),
        )
    result = service.answer(None, game["id"], attempt["id"], "p0", payload, 9000)
    assert (
        service.answer(None, game["id"], attempt["id"], "p0", payload, 29000) == result
    )
    error(
        "answer_final",
        lambda: service.answer(
            None,
            game["id"],
            attempt["id"],
            "p0",
            payload | {"who_player_ids": ["p2"]},
            9001,
        ),
    )
    for actor in ("p1", "p2"):
        service.answer(None, game["id"], attempt["id"], actor, payload, 9001)
    assert game["phase"] == "reveal" and len(answers) == 3
    assert repo.score_answer.call_count == 3
    assert all(call.args[-1] > 0 for call in repo.score_answer.call_args_list)
    assert all(answer["points"] > 0 for answer in answers)


def test_deadline_creates_missing_answers_and_automatic_next_round(match):
    service, repo, game, rounds, answers, _ = match
    attempt = answering(match)
    service.advance(None, game["id"], attempt["deadline_at_ms"])
    assert len(answers) == 3 and all(
        a["status"] == "missing" and a["points"] == 0 for a in answers
    )
    service.advance(None, game["id"], attempt["deadline_at_ms"] + 5000)
    assert game["phase"] == "leaderboard"
    service.advance(None, game["id"], attempt["deadline_at_ms"] + 10000, False)
    assert len(rounds) == 1
    service.advance(None, game["id"], attempt["deadline_at_ms"] + 10000)
    assert len(rounds) == 2 and game["phase"] == "ready"
    service.end(None, game["id"], "p0", {"request_id": "end"}, 40000)
    assert game["end_reason"] == "host_ended" and rounds[-1]["status"] == "void"
    assert service.end(None, game["id"], "p0", {"request_id": "end"}, 40001) == {
        "accepted": True
    }
    repo.save_ranks.assert_called_once()


def test_audio_failure_uses_checked_reserve_and_preserves_voided_attempt(match):
    service, _, game, rounds, _, _ = match
    attempt = answering(match)
    payload = {
        "request_id": "failure",
        "readiness_generation": 1,
        "reason": "decode_failed",
    }
    response = service.audio_failure(
        None, game["id"], attempt["id"], "p0", payload, 9001
    )
    assert response["void_round_id"] == attempt["id"]
    assert (
        attempt["status"] == "void"
        and rounds[-1]["attempt"] == 2
        and game["phase"] == "ready"
    )
    assert (
        service.audio_failure(None, game["id"], attempt["id"], "p0", payload, 9002)
        == response
    )
    error(
        "recovery_unavailable",
        lambda: service.readiness_command(
            None,
            game["id"],
            rounds[-1]["id"],
            "p0",
            "retry",
            {"request_id": "early", "readiness_generation": 1},
            9002,
        ),
    )
    game["status"] = "playing"
    now = rounds[-1]["readiness_deadline_at_ms"]
    service.readiness_command(
        None,
        game["id"],
        rounds[-1]["id"],
        "p0",
        "retry",
        {"request_id": "retry", "readiness_generation": 1},
        now,
    )
    assert rounds[-1]["readiness_generation"] == 2
