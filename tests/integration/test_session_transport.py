"""Secure deployments admit only where browsers can retain the room cookie."""

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from tests.support.demo import demo_config


@pytest.fixture(params=["demo", "normal"])
def secure_app(tmp_path, request):
    return create_app(
        demo_config(
            tmp_path,
            cookie_secure=True,
            public_url="https://game.example",
            game_mode=request.param,
        ),
        background=False,
    )


def test_http_entry_redirects_to_https_and_preserves_invitation(secure_app):
    with TestClient(secure_app, base_url="http://192.168.1.80:8000") as client:
        response = client.get("/?join=ABC123&page=play", follow_redirects=False)
        assert response.status_code == 307
        assert (
            response.headers["location"]
            == "https://game.example/?join=ABC123&page=play"
        )
        assert client.get("/health/ready").status_code == 200
        assert client.get("https://game.example/").status_code == 200


def test_http_creation_is_rejected_before_committing_an_unusable_room(secure_app):
    with TestClient(secure_app, base_url="http://192.168.1.80:8000") as client:
        response = client.post(
            "/api/rooms",
            json={"nickname": "Host", "mode": "demo"},
            headers={"X-Forwarded-Proto": "https"},
        )
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "session_https_required"
        assert error["details"] == {"application_url": "https://game.example/"}
        assert "set-cookie" not in response.headers
        with secure_app.state.coordinator.db.read() as connection:
            assert connection.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 0


def test_https_demo_create_join_heartbeat_and_renewal_use_browser_cookie_jars(
    secure_app,
):
    with TestClient(secure_app, base_url="https://game.example") as host:
        with TestClient(secure_app, base_url="https://game.example") as guest:
            created = host.post("/api/rooms", json={"nickname": "Host", "mode": "demo"})
            assert created.status_code == 201
            path = "/api/rooms/" + created.json()["room_id"]
            assert "Secure" in created.headers["set-cookie"]
            assert guest.get(path + "/state").status_code == 401
            # A direct HTTP admission must not leave an extra player behind.
            rejected = guest.post(
                "http://game.example" + path + "/join", json={"nickname": "Lost"}
            )
            assert rejected.status_code == 409
            assert len(host.get(path + "/state").json()["players"]) == 1
            joined = guest.post(path + "/join", json={"nickname": "Friend"})
            assert joined.status_code == 201
            assert "Secure" in joined.headers["set-cookie"]
            for client, nickname in ((host, "Host"), (guest, "Friend")):
                assert client.post(path + "/heartbeat", json={}).status_code == 200
                state = client.get(path + "/state")
                assert state.status_code == 200
                assert state.json()["me"]["nickname"] == nickname
                assert "Secure" in state.headers["set-cookie"]
                assert client.get(path + "/state").status_code == 200


def test_secure_configuration_without_shared_https_has_actionable_error(tmp_path):
    app = create_app(demo_config(tmp_path, cookie_secure=True), background=False)
    with TestClient(app) as client:
        response = client.post("/api/rooms", json={"nickname": "Host", "mode": "demo"})
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "session_https_required"
        assert "host must configure" in error["message"]
        assert error["details"] == {}
