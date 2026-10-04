"""Room state exposes a usable invitation without requiring guest credentials."""

from urllib.parse import urlsplit, parse_qs

from fastapi.testclient import TestClient

from backend.app import create_app
from tests.support.demo import demo_config


def test_localhost_host_invites_a_separate_lan_client(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.api.invitations.discover_lan_host", lambda: "192.168.1.80"
    )
    app = create_app(demo_config(tmp_path), background=False)
    with TestClient(app, base_url="http://127.0.0.1:8000") as host:
        room = host.post("/api/rooms", json={"nickname": "Host", "mode": "demo"}).json()
        path = "/api/rooms/" + room["room_id"]
        url = host.get(path + "/state").json()["room"]["invite_url"]
        parsed = urlsplit(url)
        assert parsed.netloc == "192.168.1.80:8000"
        assert parse_qs(parsed.query) == {"join": [room["code"]]}
        guest = TestClient(app, base_url=f"{parsed.scheme}://{parsed.netloc}")
        try:
            assert guest.get(parsed.path + "?" + parsed.query).status_code == 200
            assert guest.get(path + "/state").status_code == 401
            resolved = guest.get("/api/room-codes/" + room["code"]).json()
            assert resolved["room_id"] == room["room_id"]
            assert (
                guest.post(path + "/join", json={"nickname": "Friend"}).status_code
                == 201
            )
            assert guest.get(path + "/state").json()["room"]["invite_url"] == url
            assert host.get(path + "/state").json()["me"]["nickname"] == "Host"
        finally:
            guest.close()
