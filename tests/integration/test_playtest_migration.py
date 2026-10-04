"""Playtest account exemptions preserve identities and ordinary account guards."""

import sqlite3

import pytest

from backend.core.errors import DomainError
from backend.rooms import repository
from backend.rooms.service import RoomsService
from backend.storage.database import Database
from tests.integration.test_music_admission import song
from tests.support.migrations import legacy_copy


def imported(account="same-account"):
    return {
        "provider": "spotify",
        "evidence": "personal",
        "account_id": account,
        "songs": [song(f"shared-{index}") for index in range(12)],
    }


def records(conn):
    tables = [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    return {
        table: [
            dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")
        ]
        for table in tables
    }


def test_populated_v4_upgrade_preserves_sessions_account_hashes_and_song_memberships(
    tmp_path,
):
    source = Database(tmp_path / "source.sqlite3")
    source.initialize()
    ordinary = RoomsService()
    with source.transaction() as conn:
        host = ordinary.create(
            conn, "Host", "coral", "normal", 1000, imported=imported()
        )
        guest = ordinary.join(
            conn,
            host["room"]["id"],
            "Guest",
            "sky",
            1100,
            imported=imported("other-account"),
        )

    path = tmp_path / "v4.sqlite3"
    with source.read() as conn, sqlite3.connect(path) as legacy:
        legacy_copy(conn, legacy, 4)
    upgraded = Database(path)
    with upgraded.read() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
        before = records(conn)
        assert "shared_music_account" not in before["players"][0]
        assert len(before["player_songs"]) == 24
        assert all(player["music_account_hash"] for player in before["players"])

    upgraded.initialize()
    upgraded.initialize()
    with upgraded.read() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        after = records(conn)
        assert after.pop("game_round_preparations") == []
        for player in after["players"]:
            assert player.pop("shared_music_account") == 0
        assert after == before
        for admission in (host, guest):
            restored = ordinary.authenticate(
                conn, host["room"]["id"], admission["token"], 1200
            )
            assert restored["id"] == admission["player"]["id"]
        assert all(
            player["song_count"] == 12
            for player in ordinary.lobby(conn, host["room"]["id"], 1200)["players"]
        )


@pytest.mark.parametrize("host_playtest", [False, True])
def test_playtest_shared_accounts_retain_hashes_and_are_rejected_after_disabling(
    tmp_path, host_playtest
):
    database = Database(tmp_path / "state.sqlite3")
    database.initialize()
    playtest = RoomsService(playtest=True)
    host_service = playtest if host_playtest else RoomsService()
    with database.transaction() as conn:
        host = host_service.create(
            conn, "Host", "coral", "normal", 1000, imported=imported()
        )
        room_id = host["room"]["id"]
        guest = playtest.join(conn, room_id, "Guest", "sky", 1100, imported=imported())
    assert host["player"]["id"] != guest["player"]["id"]
    assert host["token"] != guest["token"]
    with database.read() as conn:
        players = repository.players(conn, room_id)
        assert len(players) == 2
        assert len({player["music_account_hash"] for player in players}) == 1
        assert all(player["music_account_hash"] for player in players)
        assert {
            player["nickname"]: player["shared_music_account"] for player in players
        } == {"Host": int(host_playtest), "Guest": 1}
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM songs WHERE room_id=?", (room_id,)
            ).fetchone()[0]
            == 12
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM player_songs WHERE room_id=?", (room_id,)
            ).fetchone()[0]
            == 24
        )
        snapshot = playtest.snapshot(conn, room_id)
        assert all(
            {listener["player_id"] for listener in song["listeners"]}
            == {host["player"]["id"], guest["player"]["id"]}
            for song in snapshot["songs"]
        )

    # Reopen storage and disable playtest: prior exemptions still retain the
    # account identity needed to reject another ordinary admission.
    reopened = Database(database.path)
    reopened.initialize()
    ordinary = RoomsService()
    with pytest.raises(DomainError) as error:
        with reopened.transaction() as conn:
            ordinary.join(
                conn, room_id, "Another Guest", "sage", 1200, imported=imported()
            )
    assert error.value.code == "music_account_taken"
    with reopened.read() as conn:
        assert len(repository.players(conn, room_id)) == 2
        for admission in (host, guest):
            assert (
                ordinary.authenticate(conn, room_id, admission["token"], 1200)["id"]
                == admission["player"]["id"]
            )


def test_ordinary_duplicate_account_constraint_survives_playtest_migration(tmp_path):
    database = Database(tmp_path / "state.sqlite3")
    database.initialize()
    with database.transaction() as conn:
        host = RoomsService().create(
            conn, "Host", "coral", "normal", 1000, imported=imported()
        )
        room_id = host["room"]["id"]
        account_hash = repository.player(conn, room_id, host["player"]["id"])[
            "music_account_hash"
        ]

    # Exercise SQLite directly: an accidental omission of the service guard
    # must still fail for an ordinary admission using the repository default.
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as conn:
            repository.add_player(
                conn,
                room_id=room_id,
                player_id="duplicate",
                nickname="Duplicate",
                nickname_key="duplicate",
                character_id="sky",
                music_status="ready",
                token_hash="another-session",
                is_host=False,
                now_ms=1100,
                music_provider="spotify",
                music_account_hash=account_hash,
            )
    with database.read() as conn:
        assert len(repository.players(conn, room_id)) == 1
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
