"""Both listening adapters prepare the same import consumed by real Rooms SQL."""

import hashlib
from contextlib import contextmanager

import pytest

from backend.application.commands import RoomCommands
from backend.application.coordinator import Coordinator
from backend.application.music_admission import MusicAdmissionHandler
from backend.catalog.search import SongSearch
from backend.core.errors import DomainError
from backend.music.importer import MusicImporter
from backend.music.previews import PreviewResolver
from backend.music.sources import DemoListeningAdapter, SpotifyListeningAdapter
from backend.music.spotify import SpotifyClient
from tests.support.demo import demo_config, make_demo_pack


class ListeningTransport:
    def request(self, method, url, headers=None, data=None):
        if url.endswith("/me"):
            return {"id": "listener-account"}
        if "recently-played" in url:
            return {"items": []}
        return {
            "items": [
                {
                    "id": str(index),
                    "name": "Recording " + str(index),
                    "artists": [{"id": "artist", "name": "Artist"}],
                    "external_ids": {"isrc": "USAA1" + str(index).zfill(7)},
                }
                for index in range(36)
            ]
        }


class PreviewCatalog:
    def resolve_verified(self, song, on_verified=None):
        return song | {"preview_url": "https://audio-ssl.itunes.apple.com/clip.m4a"}


def personal_import():
    source = SpotifyListeningAdapter(
        SpotifyClient(
            "client", "http://127.0.0.1:8000/callback", transport=ListeningTransport()
        )
    )
    return MusicImporter(
        source, PreviewResolver(PreviewCatalog()), list
    ).import_account("credential")


@pytest.fixture
def coordinator(tmp_path):
    c = Coordinator(demo_config(tmp_path, game_mode="normal"), clock=lambda: 1000)
    c.initialize()
    return c


@pytest.mark.parametrize("mode", ["demo", "normal"])
def test_both_sources_persist_song_facts_through_identical_rooms_path(
    coordinator, mode
):
    c = coordinator
    imported = c.prepare_demo_import() if mode == "demo" else personal_import()
    result = MusicAdmissionHandler(c)(
        {"nickname": "Host", "character_id": "coral", "mode": mode},
        imported,
        lambda: True,
    )
    room_id, player_id = result["room"]["id"], result["player"]["id"]
    with c.db.read() as conn:
        player = c.rooms.repo.player(conn, room_id, player_id)
        snapshot = c.rooms.snapshot(conn, room_id)
        assert c.rooms.lobby(conn, room_id, 1000)["players"][0]["song_count"] == len(
            imported["songs"]
        )
        assert conn.execute(
            "SELECT COUNT(*) FROM player_songs WHERE player_id=?", (player_id,)
        ).fetchone()[0] == len(imported["observed_songs"])
        assert len(
            [song for song in snapshot["songs"] if not song["listeners"]]
        ) == len(imported["decoys"])
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        if mode == "demo":
            assert len(imported["songs"]) == 36 and len(imported["decoys"]) == 20
            assert player["music_status"] == "demo"
            assert (
                player["music_provider"] is None
                and player["music_account_hash"] is None
            )
        else:
            assert (
                len(imported["songs"]) == 24 and len(imported["observed_songs"]) == 36
            )
            assert (
                player["music_status"] == "ready"
                and player["music_provider"] == "spotify"
            )
            expected = hashlib.sha256(
                (room_id + ":spotify:listener-account").encode()
            ).hexdigest()
            assert player["music_account_hash"] == expected


@pytest.mark.parametrize("mode", ["demo", "normal"])
def test_rooms_reject_cross_mode_evidence_before_creating_any_rows(coordinator, mode):
    c = coordinator
    imported = personal_import() if mode == "demo" else c.prepare_demo_import()
    with pytest.raises(DomainError) as error:
        c.admission(
            lambda conn, now: c.rooms.create(
                conn, "Host", "coral", mode, now, imported=imported
            )
        )
    assert error.value.code == "music_source_mismatch"

    with c.db.read() as conn:
        for table in ("rooms", "players", "songs", "player_songs"):
            assert conn.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0


def test_completed_receipt_validity_tracks_current_membership(coordinator):
    commands = RoomCommands(coordinator, SongSearch(lambda query: []))
    host = commands.create(
        {"nickname": "Host", "character_id": "coral", "mode": "demo"}
    )
    _, guest = commands.join(
        host["room"]["id"], None, {"nickname": "Guest", "character_id": "sage"}
    )
    assert commands.music_session_valid(guest)
    with coordinator.db.transaction() as conn:
        coordinator.rooms.remove_player(
            conn, host["room"]["id"], guest["player"]["id"], 1001
        )
    assert commands.music_session_valid(guest) is False
    assert commands.music_session_valid(host)


def test_rooms_requires_prepared_demo_data_without_database_writes(coordinator):
    c = coordinator
    with pytest.raises(DomainError) as error:
        c.admission(
            lambda conn, now: c.rooms.create(conn, "Host", "coral", "demo", now)
        )
    assert error.value.code == "music_import_required"
    with c.db.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 0


def test_demo_preparation_closes_catalog_read_before_source_and_preview_work(
    coordinator, monkeypatch
):
    c, active_reads = coordinator, []
    original_read, original_source = c.db.read, DemoListeningAdapter.read

    @contextmanager
    def read():
        with original_read() as conn:
            active_reads.append(conn)
            try:
                yield conn
            finally:
                active_reads.pop()

    def source_read(self, credential=None):
        assert active_reads == []
        return original_source(self, credential)

    monkeypatch.setattr(c.db, "read", read)
    monkeypatch.setattr(DemoListeningAdapter, "read", source_read)
    imported = c.prepare_demo_import()
    assert len(imported["songs"]) == 36


def test_demo_snapshot_decoys_survive_catalog_reseed(coordinator):
    c = coordinator
    result = MusicAdmissionHandler(c)(
        {"nickname": "Host", "character_id": "coral", "mode": "demo"},
        c.prepare_demo_import(),
        lambda: True,
    )
    with c.db.transaction() as conn:
        before = c.rooms.snapshot(conn, result["room"]["id"])
        conn.execute("DELETE FROM demo_catalog WHERE pool_kind='decoy'")
        assert c.rooms.snapshot(conn, result["room"]["id"]) == before


def test_rejected_local_audio_remains_listener_evidence_but_never_playable(
    tmp_path,
    monkeypatch,
):
    c = Coordinator(
        demo_config(
            tmp_path / "data",
            game_mode="normal",
            demo_pack_dir=make_demo_pack(tmp_path / "media"),
        ),
        clock=lambda: 1000,
    )
    c.initialize()
    # Use a stable assignment containing the missing clip after startup checks.
    from backend.rooms.demo import catalog_snapshot

    with c.db.read() as conn:
        missing = catalog_snapshot(conn)["personal"][0]
    (
        c.config.demo_pack_dir
        / "assets"
        / missing["preview_url"].removeprefix("/static/demo/local/")
    ).unlink()

    def read(self, credential=None):
        from backend.music.sources import ListeningData

        return ListeningData(
            "demo",
            "simulated",
            [song | {"familiarity": "easy"} for song in self.songs[:36]],
        )

    monkeypatch.setattr(DemoListeningAdapter, "read", read)
    imported = c.prepare_demo_import()
    assert len(imported["songs"]) == 35
    result = MusicAdmissionHandler(c)(
        {"nickname": "Host", "character_id": "coral", "mode": "demo"},
        imported,
        lambda: True,
    )
    with c.db.read() as conn:
        room_id = result["room"]["id"]
        assert c.rooms.lobby(conn, room_id, 1000)["players"][0]["song_count"] == 35
        snapshot = c.rooms.snapshot(conn, room_id)
        assert all(song["isrc"] != missing["isrc"] for song in snapshot["songs"])
        evidence = conn.execute(
            "SELECT s.preview_url FROM songs s JOIN player_songs ps ON ps.song_id=s.id WHERE s.room_id=? AND s.isrc=?",
            (room_id, missing["isrc"]),
        ).fetchone()
        assert evidence is not None and evidence["preview_url"] is None


def test_normal_domain_accepts_trusted_provider_ids_and_preserves_shared_owners(
    coordinator,
):
    c = coordinator
    first_import = personal_import()
    second_import = first_import | {"provider": "contract-test"}
    handler = MusicAdmissionHandler(c)
    host = handler(
        {"nickname": "Host", "character_id": "coral"}, first_import, lambda: True
    )
    room_id = host["room"]["id"]
    guest = handler(
        {"room_id": room_id, "nickname": "Guest", "character_id": "sage"},
        second_import,
        lambda: True,
    )
    with c.db.read() as conn:
        players = c.rooms.repo.players(conn, room_id)
        assert {player["music_provider"] for player in players} == {
            "spotify",
            "contract-test",
        }
        assert len({player["music_account_hash"] for player in players}) == 2
        for player in players:
            expected = hashlib.sha256(
                (
                    room_id + ":" + player["music_provider"] + ":listener-account"
                ).encode()
            ).hexdigest()
            assert player["music_account_hash"] == expected
        songs = c.rooms.snapshot(conn, room_id)["songs"]
        assert len(songs) == 24
        assert all(
            {listener["player_id"] for listener in song["listeners"]}
            == {host["player"]["id"], guest["player"]["id"]}
            for song in songs
        )


@pytest.mark.parametrize("provider", [None, "", "DEMO", "demo", "contract test"])
def test_normal_domain_rejects_missing_or_noncanonical_source_ids(
    coordinator, provider
):
    c = coordinator
    with pytest.raises(DomainError) as error:
        c.admission(
            lambda conn, now: c.rooms.create(
                conn,
                "Host",
                "coral",
                "normal",
                now,
                imported=personal_import() | {"provider": provider},
            )
        )
    assert error.value.code == "music_source_mismatch"
