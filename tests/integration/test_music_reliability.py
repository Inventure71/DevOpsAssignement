"""Cancellation, expiry rollback and ownership across real Rooms persistence."""

import pytest

from backend.application.music_admission import MusicAdmissionHandler
from backend.core.errors import DomainError
from tests.integration.test_music_admission import (
    MUSIC,
    begin,
    finish,
    normal_session as normal_session,
    song,
)


def test_unexpected_import_error_logs_source_frames_without_credentials(
    normal_session, monkeypatch, caplog
):
    def crash(token, include_decoys=False):
        raise RuntimeError("private-token private-authorization-code")

    monkeypatch.setattr(normal_session["importer"], "import_account", crash)
    host = normal_session["host"]
    with caplog.at_level("WARNING", logger="backend.music.admissions"):
        result = finish(host, begin(host, "Host"), "private-authorization-code")
    assert result["error"]["code"] == "music_import_failed"
    assert "RuntimeError" in caplog.text and "crash" in caplog.text
    assert (
        "private-token" not in caplog.text
        and "private-authorization-code" not in caplog.text
    )
    with normal_session["app"].state.coordinator.db.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 0


def test_cancelled_running_import_cannot_create_a_room(normal_session):
    session, client = normal_session, normal_session["host"]
    importer = session["importer"]
    importer.block_accounts.add("cancelled")
    state = begin(client, "Cancelled")
    assert (
        client.get(
            MUSIC + "/callback",
            params={"state": state, "code": "cancelled"},
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert importer.blocked.wait(2)
    assert client.post(MUSIC + "/cancel", json={}).json() == {"cancelled": True}
    assert client.post(MUSIC + "/cancel", json={}).status_code == 200
    importer.release.set()
    session["app"].state.music_admissions._workers.shutdown(wait=True)
    assert client.get(MUSIC + "/status").status_code == 401
    with session["app"].state.coordinator.db.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 0


def test_expiry_after_room_creation_rolls_back_all_admission_data(normal_session):
    c = normal_session["app"].state.coordinator
    checks = iter([True, False])
    imported = {
        "account_id": "expired",
        "songs": [song("expiry" + str(i)) for i in range(10)],
    }
    with pytest.raises(DomainError, match="expired"):
        MusicAdmissionHandler(c)(
            {"nickname": "Expired", "character_id": "coral"},
            imported,
            lambda: next(checks),
        )
    with c.db.read() as conn:
        for table in ("rooms", "players", "songs", "player_songs"):
            assert conn.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0


def test_unavailable_observed_song_gains_its_original_listener_when_media_arrives(
    normal_session,
):
    c = normal_session["app"].state.coordinator
    known = song("shared-recording")
    unavailable = {key: value for key, value in known.items() if key != "preview_url"}
    first = c.admission(
        lambda conn, now: c.rooms.create(
            conn,
            "Host",
            "coral",
            "normal",
            now,
            imported={
                "account_id": "host",
                "songs": [song("host" + str(i)) for i in range(10)],
                "observed_songs": [unavailable],
            },
        )
    )
    room_id = first["room"]["id"]
    with c.db.read() as conn:
        assert not any(
            s["isrc"] == known["isrc"] for s in c.rooms.snapshot(conn, room_id)["songs"]
        )
    second = c.admission(
        lambda conn, now: c.rooms.join(
            conn,
            room_id,
            "Guest",
            "sky",
            now,
            imported={
                "account_id": "guest",
                "songs": [known, *[song("guest" + str(i)) for i in range(10)]],
            },
        )
    )
    with c.db.read() as conn:
        shared = next(
            s
            for s in c.rooms.snapshot(conn, room_id)["songs"]
            if s["isrc"] == known["isrc"]
        )
        assert {p["player_id"] for p in shared["listeners"]} == {
            first["player"]["id"],
            second["player"]["id"],
        }
        assert shared["preview_url"] == known["preview_url"]


def test_mislabeled_decoy_isrc_does_not_supply_personal_song_media_or_membership(
    normal_session,
):
    c = normal_session["app"].state.coordinator
    original = song("collision")
    decoy = original | {
        "title": original["title"] + " - Instrumental",
        "preview_url": "https://audio.example/instrumental.mp3",
    }
    host = c.admission(
        lambda conn, now: c.rooms.create(
            conn,
            "Host",
            "coral",
            "normal",
            now,
            imported={
                "account_id": "host",
                "songs": [song("host" + str(i)) for i in range(10)],
                "decoys": [decoy],
            },
        )
    )
    room_id = host["room"]["id"]
    guest = c.admission(
        lambda conn, now: c.rooms.join(
            conn,
            room_id,
            "Guest",
            "sky",
            now,
            imported={
                "account_id": "guest",
                "songs": [original, *[song("guest" + str(i)) for i in range(10)]],
            },
        )
    )
    with c.db.read() as conn:
        versions = [
            s
            for s in c.rooms.snapshot(conn, room_id)["songs"]
            if s["isrc"] == original["isrc"]
        ]
        assert len(versions) == 2
        personal = next(s for s in versions if s["title"] == original["title"])
        assert personal["preview_url"] == original["preview_url"]
        assert personal["listeners"] == [
            {"player_id": guest["player"]["id"], "familiarity": "easy"}
        ]
        assert (
            next(s for s in versions if s["title"] == decoy["title"])["listeners"] == []
        )
