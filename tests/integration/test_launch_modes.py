"""Deployment mode is enforced through real admission, cookies and SQLite."""

from dataclasses import replace

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.catalog.search import SongSearch
from tests.support.demo import demo_config
from tests.integration.test_music_admission import (
    MUSIC,
    admit,
    create_normal_app,
)


def test_demo_capabilities_and_admission_ignore_configured_music_providers(tmp_path):
    app = create_normal_app(demo_config(tmp_path), background=False)
    # Reuse deterministic configured adapters, but launch the production Demo.
    app = create_app(
        replace(app.state.coordinator.config, game_mode="demo"),
        background=False,
        spotify_client=app.state.music_admissions.spotify,
        apple_catalog=app.state.music_admissions.importer.apple,
        music_importer=app.state.music_admissions.importer,
    )
    with TestClient(app) as client:
        config = client.get("/api/config").json()
        assert config["launch_mode"] == "demo"
        assert config["modes"]["demo"]["enabled"] is True
        assert config["modes"]["normal"]["enabled"] is False
        assert client.get(MUSIC + "/config").json()["enabled"] is False
        for url, body in (
            ("/api/rooms", {"nickname": "Host", "mode": "normal"}),
            (MUSIC + "/admissions", {"nickname": "Host"}),
        ):
            response = client.post(url, json=body)
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "mode_unavailable"
        with app.state.coordinator.db.read() as conn:
            assert conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 0
        assert (
            client.post(
                "/api/rooms", json={"nickname": "Host", "mode": "demo"}
            ).status_code
            == 201
        )


def test_demo_search_hits_and_repeated_misses_never_call_external_provider(tmp_path):
    def forbidden(query):
        raise AssertionError("Demo must not call an external search provider")

    app = create_app(
        demo_config(tmp_path), background=False, song_search=SongSearch(forbidden)
    )
    with TestClient(app) as client:
        room = client.post(
            "/api/rooms", json={"nickname": "Host", "mode": "demo"}
        ).json()
        path = "/api/rooms/" + room["room_id"] + "/song-search"
        with app.state.coordinator.db.read() as conn:
            title = conn.execute("SELECT title FROM demo_catalog LIMIT 1").fetchone()[0]
        result = client.get(path, params={"q": title}).json()
        assert result["source"] == "catalog" and result["songs"]
        # More than the external provider's per-minute budget, including local=true.
        for number in range(25):
            response = client.get(
                path, params={"q": f"missing-recording-{number}", "local": True}
            )
            assert response.status_code == 200
            assert response.json()["songs"] == []
        assert not app.state.song_search.calls


def test_real_capabilities_allow_demo_and_actual_music_admission_together(
    tmp_path,
):
    app = create_normal_app(demo_config(tmp_path), background=False)
    with TestClient(app) as client:
        config = client.get("/api/config").json()
        assert config["launch_mode"] == "normal"
        assert config["modes"]["normal"]["enabled"] is True
        assert config["modes"]["demo"]["enabled"] is True
        created = client.post("/api/rooms", json={"nickname": "Demo", "mode": "demo"})
        assert created.status_code == 201
        demo_path = "/api/rooms/" + created.json()["room_id"]
        guest = TestClient(app)
        try:
            assert (
                guest.post(demo_path + "/join", json={"nickname": "Friend"}).status_code
                == 201
            )
            assert guest.get(demo_path + "/state").json()["room"]["mode"] == "demo"
        finally:
            guest.close()
        room = admit(client, "Host", "host-account")
        path = "/api/rooms/" + room["room_id"]
        assert client.get(path + "/state").json()["room"]["mode"] == "normal"
        assert client.get(demo_path + "/state").json()["me"]["nickname"] == "Demo"
        assert client.post(demo_path + "/heartbeat", json={}).status_code == 200


def test_demo_launch_rejects_old_spotify_room_and_new_members(tmp_path):
    config = demo_config(tmp_path)
    with TestClient(create_normal_app(config, background=False)) as real:
        room = admit(real, "Host", "host-account")
        cookies = real.cookies
    app = create_app(config, background=False)
    with TestClient(app) as client:
        client.cookies.update(cookies)
        path = "/api/rooms/" + room["room_id"]
        assert (
            client.get("/api/room-codes/" + room["code"]).json()["join_available"]
            is False
        )
        for response in (
            client.get(path + "/state"),
            client.post(path + "/join", json={"nickname": "Friend"}),
        ):
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "mode_unavailable"
        with app.state.coordinator.db.read() as conn:
            assert conn.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 1


def test_real_without_keys_exposes_configuration_reason_and_cannot_admit(tmp_path):
    app = create_app(demo_config(tmp_path, game_mode="normal"), background=False)
    with TestClient(app) as client:
        config = client.get("/api/config").json()
        assert config["modes"]["demo"]["enabled"] is True
        assert config["modes"]["normal"]["enabled"] is False
        assert "not configured" in config["modes"]["normal"]["reason"]
        assert (
            client.post(MUSIC + "/admissions", json={"nickname": "Host"}).status_code
            == 503
        )
        assert (
            client.post(
                "/api/rooms", json={"nickname": "Host", "mode": "demo"}
            ).status_code
            == 201
        )
