"""Complete offline matches through real HTTP, SQLite and explicit local media assets.

The frozen database snapshot supplies only the answer oracle. Commands, signed
song selection, readiness, timing, scoring and history all use production paths.
This verifies transport and playable media availability, not physical speakers.
"""

import json
from contextlib import ExitStack

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.storage.database import Database
from tests.support.demo import demo_config, make_demo_pack


class Clock:
    def __init__(self):
        self.now = 1_000_000

    def __call__(self):
        return self.now


def accepted(response):
    assert response.status_code == 200, response.text
    return response.json()


def test_100_song_pack_completes_match_without_provider_credentials(tmp_path):
    pack = make_demo_pack(tmp_path / "music")
    exercise_demo_match(tmp_path, 15, pack)


def exercise_demo_match(tmp_path, round_count, pack, *, expected_song_count=36):
    """Run the same HTTP scenario against fixtures or a prepared local pack."""
    clock = Clock()
    app = create_app(
        demo_config(tmp_path / "data", demo_pack_dir=pack),
        clock=clock,
        background=False,
    )
    with ExitStack() as stack:
        host = stack.enter_context(TestClient(app))
        # One server lifecycle, three independent browser cookie jars.
        guests = [TestClient(app) for _ in range(2)]
        for guest in guests:
            stack.callback(guest.close)
        clients = [host, *guests]
        created = host.post("/api/rooms", json={"nickname": "Host", "mode": "demo"})
        assert created.status_code == 201, created.text
        room = created.json()
        prefix = "/api/rooms/" + room["room_id"]
        player_ids = [room["player_id"]]
        for client, name in zip(guests, ("Ada", "Grace")):
            joined = client.post(prefix + "/join", json={"nickname": name})
            assert joined.status_code == 201, joined.text
            player_ids.append(joined.json()["player_id"])
        if round_count != 10:
            accepted(
                host.patch(prefix + "/settings", json={"round_count": round_count})
            )
        state = accepted(host.get(prefix + "/state"))
        assert state["settings"]["round_count"] == round_count
        assert all(
            player["song_count"] == expected_song_count for player in state["players"]
        )
        assert host.get("/music-credits").status_code == 200
        assert host.get("/static/demo/clips/song-001.mp3").status_code == 404
        assert host.get("/static/demo/local/demo_catalog.json").status_code == 404
        lease = accepted(
            host.post(prefix + "/audio-controller", json={"tab_id": "demo-host"})
        )["lease_id"]
        game_id = accepted(
            host.post(
                prefix + "/start",
                json={
                    "request_id": "start-offline",
                    "room_revision": state["room"]["revision"],
                    "lease_id": lease,
                },
            )
        )["game_id"]
        game_path = prefix + "/games/" + game_id
        candidates = accepted(
            host.get(game_path + "/audio", headers={"X-Audio-Lease": lease})
        )["candidates"]
        assert len({item["candidate_id"] for item in candidates}) == len(candidates)
        assert len(candidates) >= round_count
        if round_count == 10:
            assert (
                len(candidates) == 40
            )  # original and three distinct reserves per slot.
        for candidate in candidates:
            clip = host.get(candidate["preview_url"])
            assert clip.status_code == 200 and len(clip.content) > 1_000
            assert clip.headers["content-type"].startswith("audio/")
            accepted(
                host.post(
                    game_path + "/preload-check",
                    json={
                        "request_id": "preload-" + candidate["candidate_id"],
                        "lease_id": lease,
                        "candidate_id": candidate["candidate_id"],
                        "ok": True,
                    },
                )
            )
        clock.now += 5_000
        state = accepted(host.get(prefix + "/state"))
        points = {player_id: 0 for player_id in player_ids}
        played = set()
        nobody_rounds = 0
        coordinator = app.state.coordinator
        for number in range(1, round_count + 1):
            assert state["game"]["phase"] == "ready"
            current = state["game"]["round"]
            assert current["round_number"] == number
            for client in clients:
                accepted(client.post(prefix + "/heartbeat", json={}))
            lease = accepted(
                host.post(prefix + "/audio-controller", json={"tab_id": "demo-host"})
            )["lease_id"]
            round_path = game_path + "/rounds/" + current["id"]
            for client in clients:
                accepted(
                    client.post(
                        round_path + "/ready",
                        json={
                            "readiness_generation": current["readiness_generation"],
                            "lease_id": lease if client is host else None,
                        },
                    )
                )
            scheduled = accepted(host.get(prefix + "/state"))["game"]
            assert scheduled["phase"] == "countdown"
            clock.now = scheduled["round"]["starts_at_ms"] + 1_000
            assert accepted(host.get(prefix + "/state"))["game"]["phase"] == "answering"
            with coordinator.db.read() as conn:
                game = conn.execute(
                    "SELECT songs_snapshot_json FROM games WHERE id=?", (game_id,)
                ).fetchone()
                key = conn.execute(
                    "SELECT song_key FROM rounds WHERE id=?", (current["id"],)
                ).fetchone()[0]
                song = next(
                    song for song in json.loads(game[0]) if song["song_key"] == key
                )
            assert key not in played
            played.add(key)
            listeners = [listener["player_id"] for listener in song["listeners"]]
            nobody_rounds += not listeners
            for client in clients:
                result = accepted(
                    client.get(prefix + "/song-search", params={"q": song["title"]})
                )
                assert result["source"] == "catalog"  # no provider or Internet needed.
                selection = next(
                    choice
                    for choice in result["songs"]
                    if choice["title"] == song["title"]
                )
                accepted(
                    client.post(
                        round_path + "/answers",
                        json={
                            "song_guess_token": selection["token"],
                            "who_player_ids": listeners,
                        },
                    )
                )
            for client, player_id in zip(clients, player_ids):
                state = accepted(client.get(prefix + "/state"))
                assert state["game"]["phase"] == "reveal"
                reveal = state["game"]["round"]["reveal"]
                assert reveal["song"]["title"] == song["title"]
                assert set(reveal["listener_ids"]) == set(listeners)
                assert reveal["my_answer"]["song_match"] == "correct"
                assert reveal["my_answer"]["points"] > 0
                points[player_id] += reveal["my_answer"]["points"]
            clock.now = state["game"]["phase_ends_at_ms"]
            state = accepted(host.get(prefix + "/state"))
            assert state["game"]["phase"] == "leaderboard"
            clock.now = state["game"]["phase_ends_at_ms"]
            state = accepted(host.get(prefix + "/state"))
        assert nobody_rounds == round_count // 5
        assert state["game"]["status"] == "completed"
        assert state["game"]["playable_rounds"] == round_count
        assert {
            item["player_id"]: item["score"] for item in state["game"]["leaderboard"]
        } == points
        history = accepted(host.get("/api/room-codes/" + room["code"] + "/history"))[
            "games"
        ]
        assert len(history) == 1 and history[0]["id"] == game_id
        with coordinator.db.read() as conn:
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM rounds WHERE game_id=? AND status='revealed'",
                    (game_id,),
                ).fetchone()[0]
                == round_count
            )
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM answers WHERE game_id=? AND status='submitted'",
                    (game_id,),
                ).fetchone()[0]
                == 3 * round_count
            )
            assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

    # Scores, immutable answers and ranks must survive independent reopening.
    reopened = Database(coordinator.db.path)
    reopened.initialize()
    with reopened.read() as conn:
        roster = coordinator.game.repo.roster(conn, game_id)
        assert len(roster) == len(player_ids)
        assert all(
            p["final_score"] == points[p["player_id"]] and p["final_rank"] is not None
            for p in roster
        )
        saved = coordinator.game.repo.history(conn, room["room_id"])
        assert saved[0]["id"] == game_id
        assert saved[0]["leaderboard"] == state["game"]["leaderboard"]
