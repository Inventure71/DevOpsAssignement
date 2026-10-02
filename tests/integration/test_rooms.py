"""Exercise Rooms through real transactions, constraints and persistent sessions."""

import json
import sqlite3

import pytest

from backend.core.config import Config
from tests.support.catalog import write_large_catalog
from backend.storage.database import Database
from backend.core.errors import DomainError
from backend.rooms.demo import seed_demo
from backend.rooms.service import RETENTION_MS, RoomsService


@pytest.fixture
def database(tmp_path):
    database = Database(tmp_path / "state/whos_on_repeat.sqlite3")
    database.initialize()
    catalog_path = write_large_catalog(tmp_path / "catalog.json")
    with database.transaction() as conn:
        seed_demo(conn, catalog_path)
    return database


@pytest.fixture
def service():
    return RoomsService()


def create(database, service, nickname="Host", now=1000):
    with database.transaction() as conn:
        return service.create(conn, nickname, "coral", "demo", now)


def test_schema_initialization_is_versioned_and_idempotent(database):
    database.initialize()
    with database.read() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM demo_catalog").fetchone()[0] == 120
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_transaction_rolls_back_all_room_admission_data(database, service):
    with pytest.raises(RuntimeError):
        with database.transaction() as conn:
            service.create(conn, "Host", "coral", "demo", 1000)
            raise RuntimeError("simulated subsequent operation failure")
    with database.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM songs").fetchone()[0] == 0


def test_credential_survives_restart_is_only_a_digest_and_is_room_scoped(database, service):
    first, second = create(database, service), create(database, service)
    database.initialize()
    with database.read() as conn:
        player = service.authenticate(conn, first["room"]["id"], first["token"], 1100)
        assert player["id"] == first["player"]["id"]
        assert player["session_token_hash"] != first["token"]
        assert len(player["session_token_hash"]) == 64
        with pytest.raises(DomainError) as error:
            service.authenticate(conn, second["room"]["id"], first["token"], 1100)
        assert error.value.code == "unauthorized"


def test_normal_mode_cannot_fake_authorization_or_assign_demo(database, service):
    with pytest.raises(DomainError) as error:
        with database.transaction() as conn:
            service.create(conn, "Host", "coral", "normal", 1000)
    assert error.value.code == "provider_unavailable"
    assert error.value.status == 503
    with database.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 0


def test_hidden_assignment_counts_shared_dedup_and_independent_rooms(database, service):
    first, second = create(database, service), create(database, service)
    room_id = first["room"]["id"]
    with database.transaction() as conn:
        join = service.join(conn, room_id, "Guest", "lavender", 1100)
        assert not join["player"]["is_host"]
        lobby = service.lobby(conn, room_id, 1200)
        assert len(lobby["players"]) == 2
        assert all(p["song_count"] == 36 for p in lobby["players"])
        assert "songs" not in lobby
        assert "session_token_hash" not in json.dumps(lobby)
        assert "Artist" not in json.dumps(lobby)
        # The assignment is a union of each player's songs, with no duplicate identities.
        identities = [row[0] for row in conn.execute("SELECT identity_key FROM songs WHERE room_id=?", (room_id,))]
        assert 36 <= len(identities) <= 72
        assert len(set(identities)) == len(identities)
        ids_first = {row[0] for row in conn.execute("SELECT id FROM songs WHERE room_id=?", (room_id,))}
        ids_second = {row[0] for row in conn.execute("SELECT id FROM songs WHERE room_id=?", (second["room"]["id"],))}
        assert ids_first.isdisjoint(ids_second)


def test_snapshot_copies_artwork_credits_characters_and_decoys(database, service):
    joined = create(database, service)
    room_id = joined["room"]["id"]
    with database.transaction() as conn:
        conn.execute("UPDATE songs SET artwork_url='/static/demo/covers/test.svg' WHERE room_id=?", (room_id,))
        snapshot = service.snapshot(conn, room_id)
        assert snapshot["host_id"] == joined["player"]["id"]
        assert snapshot["players"][0]["character_id"] == "coral"
        assert len([s for s in snapshot["songs"] if not s["listeners"]]) == 24
        assert len([s for s in snapshot["songs"] if s["listeners"]]) == 36
        for song in snapshot["songs"]:
            assert song["artists"][0]["artist_key"].startswith("demo:")
            if song["listeners"]:
                assert song["artwork_url"] == "/static/demo/covers/test.svg"
                assert song["listeners"][0]["player_id"] == joined["player"]["id"]
        conn.execute("UPDATE songs SET title='Changed' WHERE room_id=?", (room_id,))
        service.update_player(conn, room_id, joined["player"]["id"], "Changed", "lavender", 1100)
        assert snapshot["players"][0]["nickname"] == "Host"
        assert all(song["title"] != "Changed" for song in snapshot["songs"])


def test_casefold_uniqueness_and_invalid_character(database, service):
    joined = create(database, service, nickname="Straße")
    room_id = joined["room"]["id"]
    with database.transaction() as conn:
        with pytest.raises(DomainError) as error:
            service.join(conn, room_id, " STRASSE ", "lavender", 1100)
        assert error.value.code == "nickname_taken"
        with pytest.raises(DomainError) as error:
            service.join(conn, room_id, "Guest", "arbitrary", 1100)
        assert error.value.code == "invalid_character"
        assert len(service.lobby(conn, room_id, 1100)["players"]) == 1


def test_roster_limit_and_lobby_lock_allow_existing_identity(database, service):
    joined = create(database, service)
    room_id = joined["room"]["id"]
    with database.transaction() as conn:
        for i in range(9):
            service.join(conn, room_id, f"Guest {i}", "lavender", 1100)
        with pytest.raises(DomainError) as error:
            service.join(conn, room_id, "Eleventh", "lavender", 1100)
        assert error.value.code == "room_full"
        service.set_state(conn, room_id, "playing")
        with pytest.raises(DomainError) as error:
            service.join(conn, room_id, "New browser", "lavender", 1100)
        assert error.value.code == "room_locked"
        with pytest.raises(DomainError):
            service.update_player(conn, room_id, joined["player"]["id"], "New Host", "lemon", 1200)
        assert service.authenticate(conn, room_id, joined["token"], 1200)["id"] == joined["player"]["id"]


def test_host_heartbeat_at_exact_grace_cannot_revive_playing_game(database, service):
    joined = create(database, service)
    room_id, host = joined["room"]["id"], joined["player"]["id"]
    with database.transaction() as conn:
        service.set_state(conn, room_id, "playing")
        assert service.heartbeat(conn, room_id, host, 60_999)["last_seen_at_ms"] == 60_999
        with pytest.raises(DomainError) as error:
            service.heartbeat(conn, room_id, host, 120_999)
        assert error.value.code == "host_expired"
        assert service.snapshot(conn, room_id)["players"][0]["last_seen_at_ms"] == 60_999


def test_host_presence_uses_heartbeat_only_and_revision_changes_are_explicit(database, service):
    joined = create(database, service)
    room_id = joined["room"]["id"]
    with database.transaction() as conn:
        initial_revision = service.room(conn, room_id, 1000)["revision"]
        presence = service.host_presence(conn, room_id, 1000)
        assert presence == {"player_id": joined["player"]["id"], "connected": True, "expires_at_ms": 61_000}
        assert service.host_presence(conn, room_id, 16_000)["connected"] is False
        # Reads, authentication and revision updates never renew host presence.
        service.authenticate(conn, room_id, joined["token"], 20_000)
        service.bump_revision(conn, room_id)
        assert service.room(conn, room_id, 20_000)["revision"] == initial_revision + 1
        assert service.host_presence(conn, room_id, 61_000)["expires_at_ms"] == 61_000
        service.heartbeat(conn, room_id, joined["player"]["id"], 61_000)
        assert service.host_presence(conn, room_id, 61_000)["expires_at_ms"] == 121_000


def test_presence_and_polling_do_not_renew_retention_and_exact_expiry_is_rejected(database, service):
    joined = create(database, service)
    room_id, host = joined["room"]["id"], joined["player"]["id"]
    with database.transaction() as conn:
        service.heartbeat(conn, room_id, host, RETENTION_MS)
        assert service.room(conn, room_id, RETENTION_MS + 999)["last_completed_at_ms"] is None
        with pytest.raises(DomainError) as error:
            service.authenticate(conn, room_id, joined["token"], RETENTION_MS + 1000)
        assert error.value.code == "room_expired"
        assert service.expired_ids(conn, RETENTION_MS + 1000) == [room_id]


def test_completion_renews_room_and_cleanup_preserves_other_room_and_catalog(database, service):
    joined, other = create(database, service), create(database, service)
    room_id = joined["room"]["id"]
    with database.transaction() as conn:
        service.complete(conn, room_id, 2000)
        assert service.room(conn, room_id, RETENTION_MS + 1000)["last_completed_at_ms"] == 2000
        assert service.expired_ids(conn, RETENTION_MS + 1000) == [other["room"]["id"]]
        service.delete(conn, room_id)
        assert conn.execute("SELECT COUNT(*) FROM players WHERE room_id=?", (room_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM songs WHERE room_id=?", (room_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM demo_catalog").fetchone()[0] == 120
        assert service.room(conn, other["room"]["id"], 2000)["id"] == other["room"]["id"]
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_cross_room_relationship_is_rejected_by_database(database, service):
    first, second = create(database, service), create(database, service)
    with database.transaction() as conn:
        second_song = conn.execute("SELECT id FROM songs WHERE room_id=? LIMIT 1", (second["room"]["id"],)).fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO player_songs (room_id,player_id,song_id,familiarity) VALUES (?,?,?,'easy')",
                         (first["room"]["id"], first["player"]["id"], second_song))


def test_member_leave_removes_only_own_links_and_unreferenced_songs(database, service):
    joined = create(database, service)
    room_id = joined["room"]["id"]
    with database.transaction() as conn:
        guest = service.join(conn, room_id, "Guest", "lavender", 1100)
        service.remove_player(conn, room_id, guest["player"]["id"], 1200)
        assert len(service.lobby(conn, room_id, 1200)["players"]) == 1
        assert conn.execute("SELECT COUNT(*) FROM songs WHERE room_id=?", (room_id,)).fetchone()[0] == 36
        assert service.lobby(conn, room_id, 1200)["players"][0]["song_count"] == 36
        with pytest.raises(DomainError):
            service.authenticate(conn, room_id, guest["token"], 1200)


def test_invalid_seed_does_not_create_partial_catalog(database, tmp_path):
    path = tmp_path / "invalid_catalog.json"
    path.write_text(json.dumps([{"id": "incomplete"}]))
    with database.transaction() as conn:
        with pytest.raises(ValueError):
            seed_demo(conn, path)
        assert conn.execute("SELECT COUNT(*) FROM demo_catalog").fetchone()[0] == 120


def test_environment_config_validates_deployment_values(monkeypatch):
    monkeypatch.setenv("DATA_DIR", "/tmp/custom")
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("COOKIE_SECURE", "true")
    config = Config.from_env()
    assert config.database_path.name == "whos_on_repeat.sqlite3"
    assert config.port == 9000 and config.cookie_secure
    monkeypatch.setenv("PORT", "70000")
    with pytest.raises(ValueError):
        Config.from_env()
