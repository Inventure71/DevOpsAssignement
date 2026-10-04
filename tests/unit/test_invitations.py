"""Invitation origins for local development and hosted games."""

import pytest

from backend.api import invitations
from backend.api.invitations import InviteLinks, discover_lan_host
from backend.core.config import Config


@pytest.fixture
def lan(monkeypatch):
    monkeypatch.setattr(invitations, "discover_lan_host", lambda: "192.168.1.80")


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:8000/",
        "http://127.0.0.1:8000/",
        "http://[::1]:8000/",
        "http://0.0.0.0:8000/",
    ],
)
def test_loopback_invites_use_the_server_lan_address(lan, origin):
    assert (
        InviteLinks(port=8123).for_room(origin, "ABC123")
        == "http://192.168.1.80:8123/?join=ABC123"
    )


@pytest.mark.parametrize(
    "origin", ["http://192.168.1.80:8000/", "https://game.example/"]
)
def test_reachable_request_origin_is_preserved(lan, origin):
    assert InviteLinks().for_room(origin, "ABC123") == origin + "?join=ABC123"


def test_configured_public_origin_wins(lan, monkeypatch):
    monkeypatch.setenv("APP_PUBLIC_URL", "https://game.example/")
    config = Config.from_env()
    assert (
        InviteLinks(config.public_url).for_room("http://localhost:8000/", "ABC123")
        == "https://game.example/?join=ABC123"
    )


@pytest.mark.parametrize(
    "value",
    [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://[::1]:8000",
        "http://0.0.0.0:8000",
        "ftp://game.example",
        "https://user:secret@game.example",
        "https://game.example/path",
        "https://game.example?join=old",
        "https://game.example#fragment",
        "http://game.example:bad",
    ],
)
def test_invalid_public_origin_fails_startup(value):
    with pytest.raises(ValueError):
        InviteLinks(value)


def test_no_lan_address_does_not_advertise_loopback(monkeypatch):
    monkeypatch.setattr(invitations, "discover_lan_host", lambda: None)
    assert InviteLinks().for_room("http://127.0.0.1:8000/", "ABC123") is None


def test_network_discovery_failure_is_optional(monkeypatch):
    def unavailable(*args):
        raise OSError("No route")

    monkeypatch.setattr(invitations.socket, "socket", unavailable)
    assert discover_lan_host() is None
