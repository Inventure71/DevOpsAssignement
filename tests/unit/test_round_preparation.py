"""Preparation policy: freshness, membership, ownership and promotion."""

import json
from copy import deepcopy

import pytest

from backend.core.errors import DomainError
from backend.game.repository import encode
from tests.support.game_policy import answering
from tests.support.game_policy import (
    match as match,  # noqa: PLC0414 -- fixture registration
)


@pytest.fixture
def upcoming(match):
    service, repo, game, _, _, _ = match
    attempt = answering(match)
    service.advance(None, game["id"], attempt["deadline_at_ms"])
    return match, repo.pending_preparation(None, game["id"]), attempt["deadline_at_ms"]


def prepare_player(match, pending, actor, now, lease="speaker"):
    service, _, game, _, _, _ = match
    return service.prepare_upcoming(
        None,
        game["id"],
        pending["id"],
        actor,
        {"readiness_generation": 1, "browser_id": actor, "lease_id": lease},
        now,
    )


PLAYERS = frozenset({"p0", "p1", "p2"})


@pytest.mark.parametrize(
    "conditions,ready",
    [
        pytest.param({"age": 5000}, PLAYERS, id="exact-freshness-boundary"),
        pytest.param({"age": 5001}, set(), id="expired"),
        pytest.param({"age": -1}, set(), id="clock-moved-backwards"),
        pytest.param({"lease": None}, {"p1", "p2"}, id="host-lease-expired"),
        pytest.param({"lease": "replacement"}, {"p1", "p2"}, id="host-lease-replaced"),
        pytest.param(
            {"connected": {"p0", "p1"}}, {"p0", "p1"}, id="guest-disconnected"
        ),
        pytest.param({"actors": {"p0", "p1"}}, {"p0", "p1"}, id="guest-not-prepared"),
    ],
)
def test_upcoming_promotion_requires_fresh_connected_players_and_current_host_lease(
    upcoming, conditions, ready
):
    match, pending, closed_at = upcoming
    service, repo, game, rounds, _, _ = match
    now = closed_at + 10_000
    for actor in conditions.get("actors", PLAYERS):
        prepare_player(match, pending, actor, now - conditions.get("age", 0))
    service.advance(
        None,
        game["id"],
        now,
        host_lease_id=conditions.get("lease", "speaker"),
        connected_player_ids=conditions.get("connected", PLAYERS),
    )
    current = rounds[-1]
    assert current["id"] == pending["id"]
    assert set(json.loads(current["ready_player_ids_json"])) == ready
    assert repo.pending_preparation(None, game["id"]) is None
    if ready == PLAYERS:
        assert game["phase"] == "countdown" and current["starts_at_ms"] == now + 3000
    else:
        assert game["phase"] == "ready" and current["starts_at_ms"] is None
        service.ready(None, game["id"], current["id"], "p0", 1, now)
        service.ready(None, game["id"], current["id"], "p1", 1, now)
        service.ready(None, game["id"], current["id"], "p2", 1, now)
        assert game["phase"] == "countdown"


@pytest.mark.parametrize(
    "invalid,code",
    [
        ("id", "stale_preparation"),
        ("generation", "stale_generation"),
        ("player", "game_not_found"),
        ("promoted", "stale_preparation"),
    ],
)
def test_unissued_or_consumed_preparation_cannot_acknowledge_a_round(
    upcoming, invalid, code
):
    match, pending, closed_at = upcoming
    service, repo, game, rounds, _, _ = match
    if invalid == "promoted":
        service.advance(None, game["id"], closed_at + 10_000)
    before = deepcopy(rounds)
    with pytest.raises(DomainError) as caught:
        service.prepare_upcoming(
            None,
            game["id"],
            "unissued" if invalid == "id" else pending["id"],
            "outsider" if invalid == "player" else "p0",
            {
                "readiness_generation": 2 if invalid == "generation" else 1,
                "browser_id": "tab",
            },
            closed_at,
        )
    assert caught.value.code == code
    assert rounds == before
    assert not (repo.pending_preparation(None, game["id"]) or {}).get(
        "acknowledgements"
    )


def test_upcoming_renewal_and_host_takeover_preserve_guest_checkins(upcoming):
    match, pending, closed_at = upcoming
    service, repo, game, _, _, _ = match
    for actor in ("p0", "p1", "p2"):
        prepare_player(match, pending, actor, closed_at)
    prepare_player(match, pending, "p0", closed_at + 9000)
    assert (
        repo.pending_preparation(None, game["id"])["acknowledgements"]["p0"][
            "prepared_at_ms"
        ]
        == closed_at + 9000
    )
    service.invalidate_upcoming_host(None, game["id"], "p0")
    assert set(repo.pending_preparation(None, game["id"])["acknowledgements"]) == {
        "p1",
        "p2",
    }
    service.invalidate_upcoming_host(None, game["id"], "p0")
    assert set(repo.pending_preparation(None, game["id"])["acknowledgements"]) == {
        "p1",
        "p2",
    }


def test_changed_candidate_never_inherits_previous_preparation(upcoming):
    match, pending, closed_at = upcoming
    service, _, game, rounds, _, _ = match
    prepare_player(match, pending, "p0", closed_at + 9000)
    plan = json.loads(game["round_plan_json"])
    plan[1]["chosen_index"] = 1
    game["round_plan_json"] = encode(plan)
    service.advance(None, game["id"], closed_at + 10_000)
    assert rounds[-1]["id"] != pending["id"]
    assert rounds[-1]["song_key"] == plan[1]["candidates"][1]["song_key"]
    assert json.loads(rounds[-1]["ready_player_ids_json"]) == []
