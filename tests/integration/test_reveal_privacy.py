"""Private answers stay owner-only across live phases and public history."""

import json
from uuid import uuid4

from fastapi.testclient import TestClient

from tests.integration.test_api import session, start


def _state(client, prefix):
    response = client.get(prefix + "/state")
    assert response.status_code == 200, response.text
    return response.json()


def _begin_answering(coordinator, clock, game_id):
    with coordinator.db.read() as conn:
        clock.value = coordinator.game.repo.current(conn, game_id)["starts_at_ms"]
    coordinator.tick()


def _submit_distinct_answers(session, game_id, attempt):
    coordinator, clock, host, guests, room, prefix, _ = session
    clients = [host, *guests]
    with coordinator.db.read() as conn:
        game = coordinator.game.repo.game(conn, game_id)
        current = coordinator.game.repo.current(conn, game_id)
        actual = next(
            song for song in json.loads(game["songs_snapshot_json"])
            if song["song_key"] == current["song_key"]
        )
        private_titles = [
            row["title"] for row in conn.execute("SELECT title FROM demo_catalog ORDER BY id")
            if row["title"] != actual["title"]
        ][:len(clients)]
    expected = []
    path = prefix + f'/games/{game_id}/rounds/{attempt["id"]}/answers'
    for client, title in zip(clients, private_titles):
        player_id = _state(client, prefix)["me"]["id"]
        selection = client.get(prefix + "/song-search", params={"q": title}).json()["songs"][0]
        assert selection["title"] == title
        response = client.post(path, json={
            "song_guess_token": selection["token"],
            "who_player_ids": [player_id],
        })
        assert response.status_code == 200, response.text
        expected.append({"player_id": player_id, "title": title})
        if len(expected) < len(clients):
            for other_client in clients:
                if other_client is client:
                    continue
                other_response = other_client.get(prefix + "/state")
                assert other_response.json()["game"]["round"]["reveal"] is None
                assert title not in other_response.text
    return expected


def _assert_owner_only(session, phase, expected):
    _, _, host, guests, _, prefix, _ = session
    for client, owner in zip([host, *guests], expected):
        response = client.get(prefix + "/state")
        state = response.json()
        assert state["game"]["phase"] == phase
        reveal = state["game"]["round"]["reveal"]
        assert set(reveal) == {"song", "listener_ids", "my_answer"}
        answer = reveal["my_answer"]
        assert set(answer) == {
            "player_id", "status", "points", "song_guess", "song_match", "who_player_ids",
        }
        assert answer["player_id"] == owner["player_id"]
        assert answer["status"] == "submitted"
        assert answer["song_guess"]["title"] == owner["title"]
        assert answer["who_player_ids"] == [owner["player_id"]]
        for other in expected:
            if other != owner:
                assert other["title"] not in response.text
        assert "song_guess_json" not in response.text
        assert "received_at_ms" not in response.text


def _advance_phase(session):
    coordinator, clock, host, _, _, prefix, _ = session
    clock.value = _state(host, prefix)["game"]["phase_ends_at_ms"]
    assert host.post(prefix + "/heartbeat", json={}).status_code == 200
    assert host.post(prefix + "/audio-controller", json={"tab_id": "host"}).status_code == 200
    coordinator.tick()


def test_owner_only_reveal_leaderboard_completed_and_anonymous_history(session):
    coordinator, clock, host, guests, room, prefix, lease = session
    assert host.patch(prefix + "/settings", json={"round_count": 5}).status_code == 200
    game_id, attempt, _ = start(session)
    first_expected = None
    for round_number in range(1, 6):
        _begin_answering(coordinator, clock, game_id)
        expected = _submit_distinct_answers(session, game_id, attempt)
        _assert_owner_only(session, "reveal", expected)
        if first_expected is None:
            first_expected = expected
            first_attempt = attempt["id"]
        _advance_phase(session)
        _assert_owner_only(session, "leaderboard", expected)
        _advance_phase(session)
        if round_number < 5:
            next_state = _state(host, prefix)
            assert next_state["game"]["phase"] == "ready"
            attempt = next_state["game"]["round"]
            for client in [host, *guests]:
                response = client.post(
                    prefix + f'/games/{game_id}/rounds/{attempt["id"]}/ready',
                    json={
                        "readiness_generation": attempt["readiness_generation"],
                        "lease_id": lease if client is host else None,
                    },
                )
                assert response.status_code == 200, response.text
    _assert_owner_only(session, "finished", expected)
    assert _state(host, prefix)["game"]["status"] == "completed"

    with TestClient(host.app) as anonymous:
        response = anonymous.get("/api/room-codes/" + room["code"] + "/history")
    assert response.status_code == 200
    game = response.json()["games"][0]
    assert set(game) == {"id", "status", "end_reason", "ended_at_ms", "leaderboard"}
    for owner in expected:
        assert owner["title"] not in response.text
    assert "song_guess" not in response.text
    assert "who_player_ids" not in response.text

    with coordinator.db.read() as conn:
        stored = coordinator.game.repo.answers(conn, first_attempt)
    assert len(stored) == 3
    assert {
        (answer["player_id"], json.loads(answer["song_guess_json"])["title"])
        for answer in stored
    } == {(owner["player_id"], owner["title"]) for owner in first_expected}


def test_missing_submission_is_distinct_from_submitted_nobody(session):
    coordinator, clock, host, guests, room, prefix, _ = session
    game_id, attempt, _ = start(session)
    _begin_answering(coordinator, clock, game_id)
    response = host.post(
        prefix + f'/games/{game_id}/rounds/{attempt["id"]}/answers',
        json={"song_guess_token": None, "who_player_ids": []},
    )
    assert response.status_code == 200
    clock.value = _state(host, prefix)["game"]["round"]["deadline_at_ms"]
    coordinator.tick()
    host_answer = _state(host, prefix)["game"]["round"]["reveal"]["my_answer"]
    assert host_answer["status"] == "submitted"
    assert host_answer["who_player_ids"] == []
    for guest in guests:
        state = _state(guest, prefix)
        assert state["game"]["round"]["my_answer"] is None
        assert state["game"]["round"]["reveal"]["my_answer"] == {
            "player_id": state["me"]["id"],
            "status": "missing",
            "points": 0,
            "song_guess": None,
            "song_match": "unanswered",
            "who_player_ids": None,
        }


def test_void_attempt_retains_private_answers_for_diagnosis(session):
    coordinator, clock, host, guests, room, prefix, lease = session
    game_id, attempt, _ = start(session)
    _begin_answering(coordinator, clock, game_id)
    selected = guests[0].get(prefix + "/song-search", params={"q": "Test Song 001"}).json()["songs"][0]
    guest_id = _state(guests[0], prefix)["me"]["id"]
    response = guests[0].post(
        prefix + f'/games/{game_id}/rounds/{attempt["id"]}/answers',
        json={"song_guess_token": selected["token"], "who_player_ids": [room["player_id"]]},
    )
    assert response.status_code == 200
    failed = host.post(
        prefix + f'/games/{game_id}/rounds/{attempt["id"]}/audio-failure',
        json={
            "request_id": str(uuid4()),
            "readiness_generation": attempt["readiness_generation"],
            "lease_id": lease,
        },
    )
    assert failed.status_code == 200, failed.text
    for client in [host, *guests]:
        state = _state(client, prefix)
        assert state["game"]["round"]["id"] != attempt["id"]
        assert state["game"]["round"]["reveal"] is None
        assert state["game"]["round"]["my_answer"] is None
        assert all(row["score"] == 0 for row in state["game"]["leaderboard"])
    with coordinator.db.read() as conn:
        stored = coordinator.game.repo.answers(conn, attempt["id"])
        old = next(row for row in coordinator.game.repo.attempts(conn, game_id) if row["id"] == attempt["id"])
    assert old["status"] == "void"
    assert len(stored) == 1
    assert stored[0]["player_id"] == guest_id
    assert json.loads(stored[0]["song_guess_json"])["title"] == selected["title"]
    assert json.loads(stored[0]["who_player_ids_json"]) == [room["player_id"]]
