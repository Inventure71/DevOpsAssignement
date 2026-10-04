"""Server readiness and admission are independent of optional Demo media."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core.config import Config
from tests.integration.test_music_admission import admit, create_normal_app
from tests.support.demo import make_demo_pack


@pytest.mark.parametrize("mode", ["demo", "normal"])
def test_missing_pack_starts_sqlite_http_and_disables_demo_before_mutation(
    tmp_path, mode
):
    missing = tmp_path / "missing-music"
    config = Config(tmp_path / "data", demo_pack_dir=missing, game_mode=mode)
    app = create_app(config, background=False)
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").json() == {"status": "ready"}
        capability = client.get("/api/config").json()["modes"]["demo"]
        assert capability["enabled"] is False
        assert "not installed" in capability["reason"]
        assert client.get("/api/config").json()["modes"]["normal"]["enabled"] is False
        response = client.post("/api/rooms", json={"nickname": "Host", "mode": "demo"})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "mode_unavailable"
        for path in (
            "/api/demo/preview",
            "/music-credits",
            "/static/demo/local/clips/missing.m4a",
        ):
            assert client.get(path).status_code == 409
        with app.state.coordinator.db.read() as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
            assert conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM demo_catalog").fetchone()[0] == 0
        assert not missing.exists(), "Starting HTTP must not create or download media"


def test_configured_normal_admission_does_not_require_demo_media(tmp_path):
    config = Config(tmp_path / "data", demo_pack_dir=tmp_path / "missing")
    app = create_normal_app(config, background=False)
    with TestClient(app) as client:
        modes = client.get("/api/config").json()["modes"]
        assert modes["normal"]["enabled"] is True
        assert modes["demo"]["enabled"] is False
        room = admit(client, "Host", "host-account")
        state = client.get("/api/rooms/" + room["room_id"] + "/state")
        assert state.status_code == 200
        assert state.json()["room"]["mode"] == "normal"


def test_missing_pack_after_restart_does_not_reuse_stale_demo_availability(tmp_path):
    pack = make_demo_pack(tmp_path / "music")
    config = Config(tmp_path / "data", demo_pack_dir=pack)
    with TestClient(create_app(config, background=False)) as host:
        room = host.post("/api/rooms", json={"nickname": "Host", "mode": "demo"}).json()
        code = host.get("/api/rooms/" + room["room_id"] + "/state").json()["room"][
            "code"
        ]
    app = create_app(
        replace(config, demo_pack_dir=tmp_path / "absent"), background=False
    )
    with TestClient(app) as client:
        assert client.get("/health/ready").status_code == 200
        assert client.get("/api/room-codes/" + code).json()["join_available"] is False
        response = client.post(
            "/api/rooms/" + room["room_id"] + "/join", json={"nickname": "Guest"}
        )
        assert response.status_code == 409
        with app.state.coordinator.db.read() as conn:
            assert conn.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 1
            assert (
                conn.execute("SELECT COUNT(*) FROM demo_catalog").fetchone()[0] == 100
            )


def test_existing_invalid_pack_is_rejected_before_database_initialization(tmp_path):
    pack = tmp_path / "bad-music"
    pack.mkdir()
    config = Config(tmp_path / "data", demo_pack_dir=pack)
    with (
        pytest.raises(ValueError, match="missing or incomplete"),
        TestClient(create_app(config, background=False)),
    ):
        pass
    assert not config.database_path.exists()


def test_installing_valid_pack_then_restarting_enables_actual_demo_flow(tmp_path):
    pack = tmp_path / "music"
    config = Config(tmp_path / "data", demo_pack_dir=pack)
    with TestClient(create_app(config, background=False)) as client:
        assert client.get("/api/config").json()["modes"]["demo"]["enabled"] is False
    make_demo_pack(pack)
    with TestClient(create_app(config, background=False)) as client:
        assert client.get("/api/config").json()["modes"]["demo"]["enabled"] is True
        sample = client.get("/api/demo/preview").json()["song"]
        assert client.get(sample["preview_url"]).status_code == 200
        response = client.post("/api/rooms", json={"nickname": "Host", "mode": "demo"})
        assert response.status_code == 201
