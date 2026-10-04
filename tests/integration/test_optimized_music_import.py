"""Bounded imports drive actual normal games, preserving all observed ownership."""

import json
from uuid import uuid4

import pytest

from backend.music.importer import MusicImporter
from backend.music.previews import PreviewResolver
from tests.integration.test_music_admission import (
    normal_session as normal_session,
    admit,
    song,
    start_round,
    search_token,
)


@pytest.mark.parametrize("round_count", [5, 10, 15])
@pytest.mark.parametrize("normal_session", [True], indirect=True)
def test_bounded_shared_account_import_complete_game_with_failed_original(
    normal_session, round_count
):
    session = normal_session
    calls = []
    observed = [
        song(
            "same-account" + str(index),
            familiarity=("easy", "medium", "hard")[index % 3],
        )
        for index in range(60)
    ]
    observed = [
        {key: value for key, value in entry.items() if key != "preview_url"}
        for entry in observed
    ]
    spotify, apple = session["spotify"], session["apple"]
    spotify.listening = lambda token: observed
    original_resolver = apple.resolve_verified

    def resolve_verified(entry, on_verified=None):
        calls.append(entry["song_key"])
        return original_resolver(entry, on_verified=on_verified)

    apple.resolve_verified = resolve_verified
    resolver = PreviewResolver(apple, store=session["app"].state.catalog_store)
    importer = MusicImporter(spotify, resolver, decoy_provider=apple.decoys)
    session["app"].state.music_admissions.importer = importer
    apple.register([*observed, *apple.decoys()])
    room = admit(session["host"], "Host", "same-account")
    assert len(calls) == 36  # 24 player candidates + 12 decoys instead of 90
    peer = session["new_client"]()
    joined = admit(peer, "Peer", "same-account", room["room_id"])
    assert len(calls) == 36  # another player reuses media, never ownership evidence
    clients = [session["host"], peer]
    player_ids = {room["player_id"], joined["player_id"]}
    c = session["app"].state.coordinator
    with c.db.read() as conn:
        snapshot = c.rooms.snapshot(conn, room["room_id"])
        personal = [entry for entry in snapshot["songs"] if entry["listeners"]]
        assert len(personal) == 24
        assert {
            owner["familiarity"] for entry in personal for owner in entry["listeners"]
        } == {"easy", "medium", "hard"}
        assert all(
            {owner["player_id"] for owner in entry["listeners"]} == player_ids
            for entry in personal
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM player_songs WHERE room_id=?", (room["room_id"],)
            ).fetchone()[0]
            == 120
        )
    with session["app"].state.catalog_store.connect() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM catalog_songs WHERE song_key NOT LIKE 'musicbrainz:%'"
            ).fetchone()[0]
            == 0
        )
    host, clock = session["host"], session["clock"]
    prefix = "/api/rooms/" + room["room_id"]
    assert (
        host.patch(prefix + "/settings", json={"round_count": round_count}).status_code
        == 200
    )
    lease = host.post(prefix + "/audio-controller", json={"tab_id": "host-tab"}).json()[
        "lease_id"
    ]
    revision = host.get(prefix + "/state").json()["room"]["revision"]
    game_id = host.post(
        prefix + "/start",
        json={"request_id": str(uuid4()), "room_revision": revision, "lease_id": lease},
    ).json()["game_id"]
    manifest = host.get(
        prefix + f"/games/{game_id}/audio", headers={"X-Audio-Lease": lease}
    ).json()
    assert round_count <= len(manifest["candidates"]) <= min(round_count * 4, 36)
    with c.db.read() as conn:
        plan = json.loads(c.game.repo.game(conn, game_id)["round_plan_json"])
    failed = plan[0]["candidates"][0]["song_key"]
    assert len(plan[0]["candidates"]) >= 2
    for candidate in manifest["candidates"]:
        assert (
            host.post(
                prefix + f"/games/{game_id}/preload-check",
                json={
                    "request_id": str(uuid4()),
                    "lease_id": lease,
                    "candidate_id": candidate["candidate_id"],
                    "ok": candidate["candidate_id"] != failed,
                    "waveform": [0.1] * 8
                    if candidate["candidate_id"] != failed
                    else None,
                },
            ).status_code
            == 200
        )
    clock.value += 5000
    c.tick()
    seen = set()
    for number in range(1, round_count + 1):
        current, frozen = start_round(session, clients, prefix, game_id, lease)
        assert current["round_number"] == number
        assert (
            current["audio_candidate_id"] != failed
            and current["audio_candidate_id"] not in seen
        )
        seen.add(current["audio_candidate_id"])
        for client in clients:
            token = search_token(client, prefix, frozen["title"])
            response = client.post(
                prefix + f"/games/{game_id}/rounds/{current['id']}/answers",
                json={
                    "song_guess_token": token,
                    "who_player_ids": [
                        owner["player_id"] for owner in frozen["listeners"]
                    ],
                },
            )
            assert response.status_code == 200, response.text
        state = host.get(prefix + "/state").json()
        assert (
            state["game"]["phase"] == "reveal"
            and state["game"]["round"]["reveal"]["my_answer"]["song_match"] == "correct"
        )
        clock.value = state["game"]["phase_ends_at_ms"]
        c.tick()
        state = host.get(prefix + "/state").json()
        clock.value = state["game"]["phase_ends_at_ms"]
        host.post(prefix + "/heartbeat", json={})
        host.post(prefix + "/audio-controller", json={"tab_id": "host-tab"})
        c.tick()
    final = host.get(prefix + "/state").json()
    assert (
        final["game"]["status"] == "completed"
        and final["game"]["playable_rounds"] == round_count
    )
