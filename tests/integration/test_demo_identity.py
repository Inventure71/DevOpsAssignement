"""Validate custom pack identities through persistent room admission."""

import json

import pytest

from backend.rooms.demo import seed_demo
from backend.rooms.service import RoomsService
from backend.storage.database import Database


def song(number, **changes):
    return {
        "id": f"recording-{number}",
        "pool_kind": "personal",
        "isrc": f"USAA100{number:05d}",
        "title": f"Recording {number}",
        "artist": "Demo Artist",
        "artists": [{"artist_key": "demo:artist", "name": "Demo Artist"}],
        "preview_url": "/static/demo/local/clips/song-001.mp3",
        "artwork_url": None,
    } | changes


def seed(conn, tmp_path, entries):
    path = tmp_path / "pack.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    seed_demo(conn, path)


@pytest.fixture
def database(tmp_path):
    db = Database(tmp_path / "state.sqlite3")
    db.initialize()
    return db


def test_duplicate_recordings_are_normalized_before_assignment_size(database, tmp_path):
    entries = [song(number) for number in range(40)]
    duplicates = [
        entry
        | {
            "id": entry["id"] + "-duplicate",
            "isrc": "  " + entry["isrc"].lower() + "  ",
            "title": entry["title"].upper(),
            "artists": [{"artist_key": "demo:artist", "name": "DEMO ARTIST"}],
            "preview_url": "/static/demo/local/clips/song-002.mp3",
        }
        for entry in entries
    ]
    rooms = RoomsService()
    with database.transaction() as conn:
        seed(conn, tmp_path, entries + duplicates)
        assert conn.execute("SELECT COUNT(*) FROM demo_catalog").fetchone()[0] == 40
        assert {row[0] for row in conn.execute("SELECT isrc FROM demo_catalog")} == {
            entry["isrc"] for entry in entries
        }
        assert {
            row[0] for row in conn.execute("SELECT preview_url FROM demo_catalog")
        } == {entries[0]["preview_url"]}
        host = rooms.create(conn, "Host", "coral", "demo", 1000)
        room_id = host["room"]["id"]
        rooms.join(conn, room_id, "Guest", "sage", 1001)
        assert [
            player["song_count"]
            for player in rooms.lobby(conn, room_id, 1002)["players"]
        ] == [36, 36]
        for player in rooms.lobby(conn, room_id, 1002)["players"]:
            identities = list(
                conn.execute(
                    """SELECT songs.identity_key FROM player_songs
                       JOIN songs ON songs.id = player_songs.song_id
                       WHERE player_songs.player_id = ?""",
                    (player["id"],),
                )
            )
            assert len({row[0] for row in identities}) == 36
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_absent_blank_and_null_isrcs_keep_distinct_demo_identities(database, tmp_path):
    entries = [
        song(number, isrc=value, title="Unidentified recording")
        for number, value in enumerate((None, "", "  "))
    ]
    entries.append(song(3, title="Unidentified recording"))
    del entries[-1]["isrc"]
    rooms = RoomsService()
    with database.transaction() as conn:
        seed(conn, tmp_path, entries)
        assert all(
            row[0] is None for row in conn.execute("SELECT isrc FROM demo_catalog")
        )
        host = rooms.create(conn, "Host", "coral", "demo", 1000)
        room_id = host["room"]["id"]
        rooms.join(conn, room_id, "Guest", "sage", 1001)
        assert [
            player["song_count"]
            for player in rooms.lobby(conn, room_id, 1002)["players"]
        ] == [4, 4]
        assert {row[0] for row in conn.execute("SELECT identity_key FROM songs")} == {
            "demo:" + entry["id"] for entry in entries
        }


def test_duplicate_decoys_only_supply_one_unowned_recording(database, tmp_path):
    decoy = song(2, pool_kind="decoy")
    with database.transaction() as conn:
        seed(conn, tmp_path, [song(1), decoy, decoy | {"id": "duplicate-decoy"}])
        rooms = RoomsService()
        host = rooms.create(conn, "Host", "coral", "demo", 1000)
        snapshot = rooms.snapshot(conn, host["room"]["id"])
        assert len(snapshot["songs"]) == 2
        assert [
            entry["isrc"] for entry in snapshot["songs"] if not entry["listeners"]
        ] == [decoy["isrc"]]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"title": "Recording 1 (Live)"}, "Conflicting demo metadata"),
        ({"artist": "Other Artist"}, "Conflicting demo metadata"),
        (
            {"artists": [{"artist_key": "demo:other", "name": "Other Artist"}]},
            "Conflicting demo metadata",
        ),
        (
            {"artists": [{"artist_key": "demo:other", "name": "Demo Artist"}]},
            "Conflicting demo metadata",
        ),
        ({"pool_kind": "decoy"}, "both personal and decoy"),
        ({"isrc": 123}, "ISRC must be text or null"),
        ({"isrc": False}, "ISRC must be text or null"),
        ({"isrc": []}, "ISRC must be text or null"),
    ],
)
def test_invalid_identity_keeps_old_catalog_and_room_assignments(
    database, tmp_path, changes, message
):
    with database.transaction() as conn:
        seed(conn, tmp_path, [song(0)])
        rooms = RoomsService()
        old = rooms.create(conn, "Old Host", "coral", "demo", 1000)
        old_snapshot = rooms.snapshot(conn, old["room"]["id"])
        old_catalog = [tuple(row) for row in conn.execute("SELECT * FROM demo_catalog")]
        duplicate = song(1, id="duplicate", isrc="  usaa10000001  ") | changes
        with pytest.raises(ValueError, match=message):
            seed(conn, tmp_path, [song(1), duplicate])
        assert [
            tuple(row) for row in conn.execute("SELECT * FROM demo_catalog")
        ] == old_catalog
        assert rooms.snapshot(conn, old["room"]["id"]) == old_snapshot
        new = rooms.create(conn, "New Host", "sage", "demo", 1001)
        assert (
            rooms.lobby(conn, new["room"]["id"], 1002)["players"][0]["song_count"] == 1
        )
