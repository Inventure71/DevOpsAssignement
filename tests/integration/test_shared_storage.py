"""Rooms, game and public catalog persist in one application SQLite file."""

from fastapi.testclient import TestClient

from backend.app import create_app
from tests.support.demo import demo_config
from tests.unit.test_song_catalog import SONG


def test_startup_preserves_rooms_and_colocated_catalog_link_directions(tmp_path):
    config = demo_config(tmp_path)
    app = create_app(config, background=False)
    source = SONG | {"song_key": "musicbrainz:recording:verified"}
    with TestClient(app) as client:
        room = client.post(
            "/api/rooms", json={"nickname": "Host", "mode": "demo"}
        ).json()
        store = app.state.catalog_store
        assert store.path == config.database_path
        store.save_songs([source], "fixture", 10)
        store.links.save("apple:es", "guess", source, SONG, 20)
        store.save_preview(
            "recording", {"preview_url": "https://example.test/preview"}, 10, 100
        )
        assert store.search("billie jean")[0]["song_key"] == source["song_key"]
        assert store.links.find("apple:es", "guess", source) == [SONG]
        assert store.links.find("apple:es", "guess", SONG) == [source]
        assert store.preview("recording", 11)[0]
        with app.state.coordinator.db.read() as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
            assert (
                conn.execute(
                    "SELECT version FROM component_schema_versions WHERE component='catalog'"
                ).fetchone()[0]
                == 3
            )
    with TestClient(create_app(config, background=False)) as client:
        assert client.get("/api/room-codes/" + room["code"]).status_code == 200
        store = client.app.state.catalog_store
        assert store.links.find("apple:es", "guess", source) == [SONG]
        assert store.links.find("apple:es", "guess", SONG) == [source]
        store.links.reject("apple:es", "guess", source, SONG["song_key"])
    with TestClient(create_app(config, background=False)) as client:
        assert (
            client.app.state.catalog_store.links.find("apple:es", "guess", source) == []
        )
        assert client.get("/api/room-codes/" + room["code"]).status_code == 200
    assert {p.name for p in tmp_path.glob("*.sqlite3")} == {"whos_on_repeat.sqlite3"}


def test_fresh_install_creates_exactly_one_sqlite_file(tmp_path):
    app = create_app(demo_config(tmp_path), background=False)
    with TestClient(app) as client:
        assert client.get("/health/ready").status_code == 200
        assert app.state.catalog_store.search("Fleetwood Dreams")
    assert [p.name for p in tmp_path.glob("*.sqlite3")] == ["whos_on_repeat.sqlite3"]
