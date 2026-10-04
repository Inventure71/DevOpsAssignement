"""Upcoming preparation through real HTTP identity, leases and phase transitions."""

import pytest

from tests.integration.test_api import (
    session as session,  # noqa: PLC0414 -- fixture registration
)
from tests.integration.test_api import start


@pytest.fixture
def results(session):
    coordinator, clock, host, guests, _, prefix, _ = session
    game_id, current, _ = start(session)
    with coordinator.db.read() as conn:
        clock.value = coordinator.game.repo.current(conn, game_id)["starts_at_ms"]
    for client in [host, *guests]:
        response = client.post(
            prefix + f"/games/{game_id}/rounds/{current['id']}/answers",
            json={"song_guess_token": None, "who_player_ids": []},
        )
        assert response.status_code == 200, response.text
    state = host.get(prefix + "/state").json()
    assert state["game"]["phase"] == "reveal"
    pending = state["game"]["upcoming_round"]
    yield session, game_id, current, pending, clock.value


def acknowledge(session, game_id, pending, lease=None):
    _, _, host, guests, _, prefix, initial_lease = session
    path = prefix + f"/games/{game_id}/preparations/{pending['id']}/ready"
    for index, client in enumerate([host, *guests]):
        response = client.post(
            path,
            json={
                "readiness_generation": pending["readiness_generation"],
                "browser_id": f"browser-{index}",
                "lease_id": (lease or initial_lease) if client is host else None,
            },
        )
        assert response.status_code == 200, response.text
    return path


def heartbeat(session):
    _, _, host, guests, _, prefix, _ = session
    for client in [host, *guests]:
        assert client.post(prefix + "/heartbeat", json={}).status_code == 200
    response = host.post(prefix + "/audio-controller", json={"tab_id": "host"})
    assert response.status_code == 200, response.text


def test_results_prepare_privately_and_promote_directly_to_countdown(results):
    session, game_id, old_round, pending, revealed_at = results
    coordinator, clock, host, guests, _, prefix, _ = session
    guest = guests[0].get(prefix + "/state").json()["game"]
    assert guest["round"]["id"] == old_round["id"]
    assert set(guest["upcoming_round"]) == {
        "id",
        "round_number",
        "readiness_generation",
    }
    assert "audio_candidate_id" in pending
    path = acknowledge(session, game_id, pending)
    assert host.get(prefix + "/state").json()["game"]["round"]["id"] == old_round["id"]
    clock.value = revealed_at + 9000
    heartbeat(session)
    assert host.get(prefix + "/state").json()["game"]["phase"] == "leaderboard"
    acknowledge(session, game_id, pending)
    clock.value = revealed_at + 10_000
    coordinator.tick()
    game = host.get(prefix + "/state").json()["game"]
    assert game["phase"] == "countdown"
    assert game["upcoming_round"] is None
    assert game["round"]["id"] == pending["id"]
    assert game["round"]["starts_at_ms"] == clock.value + 3000
    assert len(game["round"]["ready_player_ids"]) == 3
    assert game["round"]["reveal"] is None
    assert (
        guests[0]
        .post(path, json={"readiness_generation": 1, "browser_id": "late"})
        .status_code
        == 409
    )
    assert (
        guests[0]
        .post(
            prefix + f"/games/{game_id}/rounds/{pending['id']}/answers",
            json={"song_guess_token": None, "who_player_ids": []},
        )
        .status_code
        == 409
    )


def test_old_preparation_acks_expire_and_fall_back_to_ready(results):
    session, game_id, _, pending, revealed_at = results
    coordinator, clock, host, _, _, prefix, _ = session
    acknowledge(session, game_id, pending)
    clock.value = revealed_at + 9000
    heartbeat(session)
    clock.value = revealed_at + 10_000
    coordinator.tick()
    game = host.get(prefix + "/state").json()["game"]
    assert game["phase"] == "ready"
    assert game["round"]["ready_player_ids"] == []
    assert game["round"]["readiness_deadline_at_ms"] == clock.value + 10_000
    assert game["round"]["starts_at_ms"] is None


def test_host_takeover_invalidates_upcoming_ack_and_old_lease(results):
    session, game_id, _, pending, revealed_at = results
    coordinator, clock, host, _, _, prefix, lease = session
    clock.value = revealed_at + 9000
    heartbeat(session)
    path = acknowledge(session, game_id, pending)
    replacement = host.post(
        prefix + "/audio-controller", json={"tab_id": "replacement", "takeover": True}
    )
    assert replacement.status_code == 200
    assert replacement.json()["lease_id"] != lease
    assert (
        host.post(
            path,
            json={"readiness_generation": 1, "browser_id": "old", "lease_id": lease},
        ).status_code
        == 409
    )
    clock.value = revealed_at + 10_000
    coordinator.tick()
    state = host.get(prefix + "/state").json()
    assert state["game"]["phase"] == "ready"
    assert len(state["game"]["round"]["ready_player_ids"]) == 2
    assert state["me"]["id"] not in state["game"]["round"]["ready_player_ids"]
