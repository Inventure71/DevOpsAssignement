"""Game policy against repository doubles; clocks/randomness are explicit."""

import json

import pytest

from backend.core.errors import DomainError
from tests.support.game_policy import answering, error, prepared
from tests.support.game_policy import (
    match as match,  # noqa: PLC0414 -- fixture registration
)


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
        "game_not_found",
        lambda: service.answer(
            None, game["id"], attempt["id"], "outsider", payload, 9000
        ),
    )
    assert answers == []
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
            lambda selected=selected: service.answer(
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
            29000,
        ),
    )
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


@pytest.mark.parametrize(
    "failed_slots,aborted", [(range(1, 4), False), (range(1, 5), True)]
)
def test_checked_plan_skips_failed_original_slots_or_aborts_at_limit(
    match, failed_slots, aborted
):
    service, _, game, rounds, _, _ = match
    plan = json.loads(game["round_plan_json"])
    for slot in plan:
        for candidate in slot["candidates"]:
            service.preload(
                None,
                game["id"],
                "p0",
                {
                    "request_id": candidate["song_key"],
                    "candidate_id": candidate["song_key"],
                    "ok": slot["round_number"] not in failed_slots,
                },
                1000,
            )
    service.advance(None, game["id"], 6000, host_connected=False)
    assert game["phase"] == "setup" and rounds == []
    service.advance(None, game["id"], 9000)
    assert (game["status"] == "aborted") is aborted
    if aborted:
        assert game["end_reason"] == "too_many_skipped" and rounds == []
    else:
        assert rounds[-1]["round_number"] == 4
        assert game["prepared_at_ms"] == 9000
        assert rounds[-1]["readiness_deadline_at_ms"] == 19_000


@pytest.mark.parametrize(
    "excluded,code",
    [
        (["p0"], "invalid_exclusion"),
        (["p1", "p2"], "host_not_ready"),
        (["p1"], "invalid_exclusion"),
        (["p1", "p1", "p2"], "invalid_exclusion"),
    ],
)
def test_continue_cannot_exclude_host_or_omit_duplicate_missing_players(
    match, excluded, code
):
    service, _, game, rounds, _, _ = match
    first = answering(match)
    service.advance(None, game["id"], first["deadline_at_ms"] + 10_000)
    current = rounds[-1]
    with pytest.raises(DomainError) as caught:
        service.readiness_command(
            None,
            game["id"],
            current["id"],
            "p0",
            "continue",
            {
                "request_id": "continue",
                "readiness_generation": 1,
                "exclude_player_ids": excluded,
            },
            current["readiness_deadline_at_ms"],
        )
    assert caught.value.code == code
    assert game["phase"] == "ready"


def test_continue_excludes_only_barrier_and_reconnecting_player_can_still_answer(match):
    service, _, game, rounds, _, _ = match
    first = answering(match)
    service.advance(None, game["id"], first["deadline_at_ms"] + 10_000)
    current = rounds[-1]
    now = current["readiness_deadline_at_ms"]
    service.ready(None, game["id"], current["id"], "p0", 1, now - 1)
    payload = {
        "request_id": "continue",
        "readiness_generation": 1,
        "exclude_player_ids": ["p1", "p2"],
    }
    accepted = service.readiness_command(
        None, game["id"], current["id"], "p0", "continue", payload, now
    )
    assert (
        service.readiness_command(
            None, game["id"], current["id"], "p0", "continue", payload, now + 1
        )
        == accepted
    )
    assert game["phase"] == "countdown"
    service.advance(None, game["id"], current["starts_at_ms"])
    assert service.answer(
        None,
        game["id"],
        current["id"],
        "p1",
        {"song_guess": None, "who_player_ids": []},
        current["starts_at_ms"],
    )["accepted"]
