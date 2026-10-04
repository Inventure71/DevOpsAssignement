"""Canonical 100-song metadata and explicit local-pack startup boundaries."""

import json

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core.paths import CATALOG_PATH, FRONTEND_DIR
from backend.rooms.demo import seed_demo
from backend.rooms.service import RoomsService
from backend.storage.database import Database
from tests.support.catalog import write_large_catalog
from tests.support.demo import demo_config, make_demo_pack


def test_canonical_demo_boots_serves_assets_and_starts_default_game(tmp_path):
    app = create_app(demo_config(tmp_path), clock=lambda: 1000, background=False)
    with TestClient(app) as host, TestClient(app) as ada, TestClient(app) as grace:
        assert host.get("/health/ready").status_code == 200
        response = host.post("/api/rooms", json={"nickname": "Host", "mode": "demo"})
        assert response.status_code == 201
        prefix = "/api/rooms/" + response.json()["room_id"]
        for client, nickname in ((ada, "Ada"), (grace, "Grace")):
            assert (
                client.post(prefix + "/join", json={"nickname": nickname}).status_code
                == 201
            )
        state = host.get(prefix + "/state").json()
        assert [p["song_count"] for p in state["players"]] == [36, 36, 36]
        assert state["game"] is None
        with app.state.coordinator.db.read() as conn:
            entries = list(conn.execute("SELECT * FROM demo_catalog ORDER BY id"))
            assert len(entries) == len({entry["id"] for entry in entries}) == 100
            assert sum(entry["pool_kind"] == "personal" for entry in entries) == 80
            assert sum(entry["pool_kind"] == "decoy" for entry in entries) == 20
            for entry in entries:
                assert entry["preview_url"].startswith("/static/demo/local/clips/")
                assert not entry["title"].startswith("Demo ")
                clip = host.get(entry["preview_url"])
                assert clip.status_code == 200 and len(clip.content) > 1000
                assert clip.headers["content-type"].startswith("audio/")
        assert host.get("/music-credits").status_code == 200
        assert host.get("/static/demo/clips/song-001.mp3").status_code == 404
        assert host.get("/static/demo/local/demo_catalog.json").status_code == 404
        lease = host.post(prefix + "/audio-controller", json={"tab_id": "host"}).json()[
            "lease_id"
        ]
        started = host.post(
            prefix + "/start",
            json={
                "request_id": "canonical-catalog",
                "room_revision": state["room"]["revision"],
                "lease_id": lease,
            },
        )
        assert started.status_code == 200, started.text
        assert host.get(prefix + "/state").json()["room"]["state"] == "playing"
        with app.state.coordinator.db.read() as conn:
            assert conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1


def test_reseed_preserves_current_room_copies_and_frozen_snapshot(tmp_path):
    db = Database(tmp_path / "state.sqlite3")
    db.initialize()
    rooms = RoomsService()
    with db.transaction() as conn:
        seed_demo(conn, write_large_catalog(tmp_path / "large.json"))
        old = rooms.create(conn, "Old Host", "coral", "demo", 1000)
        frozen = rooms.snapshot(conn, old["room"]["id"])
        old_ids = {s["song_key"] for s in frozen["songs"] if s["listeners"]}
        seed_demo(conn, CATALOG_PATH)
        seed_demo(conn, CATALOG_PATH)
        assert conn.execute("SELECT COUNT(*) FROM demo_catalog").fetchone()[0] == 100
        assert {
            row[0]
            for row in conn.execute(
                "SELECT id FROM songs WHERE room_id=?", (old["room"]["id"],)
            )
        } == old_ids
        assert [
            song
            for song in rooms.snapshot(conn, old["room"]["id"])["songs"]
            if song["listeners"]
        ] == [song for song in frozen["songs"] if song["listeners"]]
        assert len(frozen["songs"]) == 60
        new = rooms.create(conn, "New Host", "coral", "demo", 1000)
        assert (
            rooms.lobby(conn, new["room"]["id"], 1000)["players"][0]["song_count"] == 36
        )
        assert len(rooms.snapshot(conn, new["room"]["id"])["songs"]) == 56
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("entries", [[], [{"id": "invalid"}]])
def test_invalid_catalog_keeps_previously_seeded_entries(tmp_path, entries):
    db = Database(tmp_path / "state.sqlite3")
    db.initialize()
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(entries))
    with db.transaction() as conn:
        seed_demo(conn, CATALOG_PATH)
        with pytest.raises(ValueError):
            seed_demo(conn, invalid)
        assert conn.execute("SELECT COUNT(*) FROM demo_catalog").fetchone()[0] == 100


@pytest.mark.parametrize("missing", ["catalog", "clip", "credits"])
def test_incomplete_pack_rejects_startup_before_database_creation(tmp_path, missing):
    pack = tmp_path / "media"
    make_demo_pack(pack)
    if missing == "catalog":
        (pack / "demo_catalog.json").unlink()
    elif missing == "clip":
        next((pack / "assets/clips").iterdir()).unlink()
    elif missing == "credits":
        (pack / "assets/credits.html").unlink()
    config = demo_config(tmp_path / "data", demo_pack_dir=pack)
    with (
        pytest.raises(ValueError, match="missing or incomplete"),
        TestClient(create_app(config, background=False)),
    ):
        pass
    assert not config.database_path.exists()
    assert not config.data_dir.exists()


def test_demo_preview_exposes_catalog_metadata_without_personal_facts(tmp_path):
    app = create_app(demo_config(tmp_path), background=False)
    with TestClient(app) as client:
        response = client.get("/api/demo/preview")
        assert response.status_code == 200
        song = response.json()["song"]
        assert set(song) == {"title", "artist", "preview_url", "artwork_url"}
        assert song["preview_url"].startswith("/static/demo/local/")
        assert client.get(song["preview_url"]).status_code == 200
        assert client.get("/music-credits").status_code == 200
        with app.state.coordinator.db.read() as conn:
            assert conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM player_songs").fetchone()[0] == 0


def test_app_resources_work_when_started_outside_checkout(tmp_path, monkeypatch):
    data_dir = (tmp_path / "runtime").resolve()
    config = demo_config(data_dir)
    monkeypatch.chdir(tmp_path)
    app = create_app(config, clock=lambda: 1000, background=False)
    with TestClient(app) as client:
        assert client.get("/health/ready").status_code == 200
        assert client.get("/").status_code == 200
        assert client.get("/docs").status_code == 200
        schema = client.get("/openapi.json")
        assert schema.status_code == 200
        assert "/api/rooms" in schema.json()["paths"]
        assert client.get("/static/js/app.js").status_code == 404
        assert (
            client.get("/static/demo/local/%2e%2e/demo_catalog.json").status_code == 404
        )
        # Static routing is independent of module count; verify the real entry module.
        module = FRONTEND_DIR / "app.mjs"
        response = client.get("/ui/" + module.relative_to(FRONTEND_DIR).as_posix())
        assert response.status_code == 200
        assert response.headers["content-type"].split(";")[0] in {
            "text/javascript",
            "application/javascript",
        }
        assert response.content == module.read_bytes()
        with app.state.coordinator.db.read() as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
            song = conn.execute("SELECT preview_url FROM demo_catalog LIMIT 1").fetchone()
        assert client.get(song["preview_url"]).status_code == 200
    assert config.database_path.is_file()
