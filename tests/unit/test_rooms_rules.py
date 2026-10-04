"""Rooms business policy with an explicit repository double; no SQLite or HTTP."""

import json
from unittest.mock import create_autospec

import pytest

from backend.core.errors import DomainError
from backend.rooms import repository
from backend.rooms.service import (
    CONNECTED_MS,
    HOST_GRACE_MS,
    RETENTION_MS,
    RoomsService,
)


@pytest.fixture
def scenario():
    repo = create_autospec(repository)
    room = {
        "id": "room",
        "code": "ABC123",
        "mode": "demo",
        "state": "lobby",
        "revision": 2,
        "created_at_ms": 1000,
        "last_completed_at_ms": None,
    }
    player = {
        "id": "host",
        "nickname": "Host",
        "character_id": "coral",
        "is_host": True,
        "music_status": "demo",
        "last_seen_at_ms": 1000,
    }
    repo.room.return_value = room
    repo.room_by_code.return_value = room
    repo.players.return_value = [player]
    repo.player.return_value = player
    repo.player_by_token_hash.return_value = player
    repo.nickname_taken.return_value = False
    repo.music_account_taken.return_value = False
    repo.song_counts.return_value = {"host": 36}
    return RoomsService(repo=repo), repo, room, player


def error(code, operation):
    with pytest.raises(DomainError) as caught:
        operation()
    assert caught.value.code == code


def test_retention_uses_last_completed_game_and_expires_at_exact_boundary(scenario):
    service, repo, room, _ = scenario
    assert service.room(None, "room", 1000 + RETENTION_MS - 1) == room
    error("room_expired", lambda: service.room(None, "room", 1000 + RETENTION_MS))
    room["last_completed_at_ms"] = 2000
    assert service.room(None, "room", 1000 + RETENTION_MS) == room
    repo.room.return_value = None
    error("room_not_found", lambda: service.room(None, "missing", 1000))


def test_code_resolution_normalizes_code_and_respects_membership_state_and_capacity(
    scenario,
):
    service, repo, room, player = scenario
    assert service.resolve_code(None, " abc123 ", 1000)["join_available"]
    repo.room_by_code.assert_called_with(None, "ABC123")
    room["state"] = "playing"
    assert not service.resolve_code(None, "ABC123", 1000)["join_available"]
    room.update(state="lobby", mode="normal")
    repo.players.return_value = [player] * 5
    assert not service.resolve_code(None, "ABC123", 1000)["join_available"]
    error("room_not_found", lambda: service.resolve_code(None, None, 1000))
    repo.room_by_code.return_value = None
    error("room_not_found", lambda: service.resolve_code(None, "UNKNOWN", 1000))


@pytest.mark.parametrize("name", [None, "", " ", "x" * 25, "bad\nname", "bad\x7fname"])
def test_invalid_nickname_rejected_before_writes(scenario, name):
    service, repo, _, _ = scenario
    error(
        "invalid_nickname", lambda: service.check_admission(None, name, "coral", 1000)
    )
    repo.add_player.assert_not_called()


@pytest.mark.parametrize("color", [None, "vinyl", "unknown"])
def test_invalid_character_rejected(scenario, color):
    service, _, _, _ = scenario
    error(
        "invalid_character", lambda: service.check_admission(None, "Name", color, 1000)
    )


def test_admission_requires_lobby_capacity_and_unique_normalized_nickname(scenario):
    service, repo, room, player = scenario
    assert (
        service.check_admission(None, " Guest ", "coral", 1000, room_id="room") == room
    )
    repo.nickname_taken.assert_called_with(None, "room", "guest")
    room["state"] = "playing"
    error(
        "room_locked",
        lambda: service.check_admission(None, "Guest", "coral", 1000, room_id="room"),
    )
    room["state"] = "lobby"
    repo.players.return_value = [player] * 10
    error(
        "room_full",
        lambda: service.check_admission(None, "Guest", "coral", 1000, room_id="room"),
    )
    repo.players.return_value = [player]
    repo.nickname_taken.return_value = True
    error(
        "nickname_taken",
        lambda: service.check_admission(None, "Guest", "coral", 1000, room_id="room"),
    )


def test_create_allocates_identity_after_validation_and_handles_exhausted_codes(
    scenario, monkeypatch
):
    service, repo, _, _ = scenario
    error("invalid_mode", lambda: service.create(None, "Host", "coral", "other", 1000))
    error(
        "provider_unavailable",
        lambda: service.create(None, "Host", "coral", "normal", 1000),
    )
    repo.room_by_code.return_value = None
    assign = create_autospec(
        __import__("backend.rooms.demo", fromlist=["assign"]).assign
    )
    monkeypatch.setattr("backend.rooms.demo.assign", assign)
    result = service.create(None, " Host ", "coral", "demo", 1000)
    assert result["token"] and result["player"]["id"] == "host"
    args = repo.add_player.call_args.kwargs
    assert args["nickname"] == "Host" and args["nickname_key"] == "host"
    assert args["is_host"] and args["token_hash"] != result["token"]
    assign.assert_called_once()
    repo.room_by_code.return_value = {"id": "existing"}
    error("room_capacity", lambda: service.create(None, "Host", "coral", "demo", 1000))


def test_join_requires_music_signin_in_normal_and_assigns_demo_only_in_demo(
    scenario, monkeypatch
):
    service, repo, room, _ = scenario
    room["mode"] = "normal"
    error(
        "music_sign_in_required",
        lambda: service.join(None, "room", "Guest", "sky", 1000),
    )
    repo.add_player.assert_not_called()
    room["mode"] = "demo"
    assign = create_autospec(
        __import__("backend.rooms.demo", fromlist=["assign"]).assign
    )
    monkeypatch.setattr("backend.rooms.demo.assign", assign)
    service.join(None, "room", "Guest", "sky", 1000)
    assert repo.add_player.call_args.kwargs["is_host"] is False
    assign.assert_called_once()


@pytest.mark.parametrize("token", [None, "", "x" * 257])
def test_authentication_rejects_malformed_tokens(scenario, token):
    service, repo, _, _ = scenario
    error("unauthorized", lambda: service.authenticate(None, "room", token, 1000))
    repo.player_by_token_hash.assert_not_called()


def test_authentication_hashes_credential_and_rejects_unknown_session(scenario):
    service, repo, _, player = scenario
    assert service.authenticate(None, "room", "secret", 1000) == player
    credential = repo.player_by_token_hash.call_args.args[2]
    assert len(credential) == 64 and credential != "secret"
    repo.player_by_token_hash.return_value = None
    error("unauthorized", lambda: service.authenticate(None, "room", "secret", 1000))


def test_host_heartbeat_cannot_revive_expired_active_game_but_guest_can_rejoin(
    scenario,
):
    service, repo, room, player = scenario
    room["state"] = "playing"
    error(
        "host_expired",
        lambda: service.heartbeat(None, "room", "host", 1000 + HOST_GRACE_MS),
    )
    repo.record_heartbeat.assert_not_called()
    player["is_host"] = False
    service.heartbeat(None, "room", "host", 1000 + HOST_GRACE_MS)
    repo.record_heartbeat.assert_called_once()
    repo.player.return_value = None
    error("unauthorized", lambda: service.heartbeat(None, "room", "unknown", 1000))


def test_identity_change_excludes_self_but_rejects_other_nickname(scenario):
    service, repo, _, player = scenario
    assert service.update_player(None, "room", "host", " Host ", "sky", 1000) == player
    repo.nickname_taken.assert_called_with(
        None, "room", "host", exclude_player_id="host"
    )
    repo.update_identity.assert_called_with(None, "room", "host", "Host", "host", "sky")
    repo.nickname_taken.return_value = True
    error(
        "nickname_taken",
        lambda: service.update_player(None, "room", "host", "Taken", "sky", 1000),
    )


def test_leave_prunes_orphan_songs_and_lobby_exposes_counts_not_credentials(scenario):
    service, repo, _, _ = scenario
    lobby = service.lobby(None, "room", 1000 + CONNECTED_MS)
    assert lobby["players"][0]["connected"] is False
    assert lobby["players"][0]["song_count"] == 36
    assert "songs" not in lobby and "token" not in json.dumps(lobby)
    service.remove_player(None, "room", "host", 1000)
    repo.remove_player.assert_called_with(None, "room", "host")
    repo.prune_unreferenced_songs.assert_called_with(None, "room")


def test_snapshot_exports_only_playable_values_with_explicit_ownership_and_decoys(
    scenario, monkeypatch
):
    service, repo, room, _ = scenario
    row = {
        "id": "song",
        "identity_key": "isrc:ONE",
        "isrc": "ONE",
        "title": "Title",
        "artist": "Artist",
        "artists_json": '[{"artist_key":"demo:artist","name":"Artist"}]',
        "preview_url": "/clip",
        "artwork_url": None,
        "pool_kind": "personal",
    }
    repo.songs.return_value = [row, row | {"id": "unplayable", "preview_url": None}]
    repo.song_memberships.return_value = [
        {"song_id": "song", "player_id": "host", "familiarity": "easy"}
    ]
    monkeypatch.setattr(
        "backend.rooms.demo.decoys",
        lambda conn: [{"song_key": "decoy", "listeners": []}],
    )
    snapshot = service.snapshot(None, "room")
    assert snapshot["host_id"] == "host" and snapshot["minimum_players"] == 3
    assert len(snapshot["songs"]) == 2
    assert snapshot["songs"][0]["listeners"] == [
        {"player_id": "host", "familiarity": "easy"}
    ]
    row["title"] = "Changed"
    assert snapshot["songs"][0]["title"] == "Title"
    room["mode"] = "normal"
    assert service.snapshot(None, "room")["songs"][0]["song_key"] == "isrc:ONE"
    repo.room.return_value = None
    error("room_not_found", lambda: service.snapshot(None, "missing"))


def test_host_presence_uses_explicit_grace_and_reports_missing_host(scenario):
    service, repo, _, _ = scenario
    repo.host.return_value = {"id": "host", "last_seen_at_ms": 1000}
    presence = service.host_presence(None, "room", 1000 + CONNECTED_MS)
    assert (
        not presence["connected"] and presence["expires_at_ms"] == 1000 + HOST_GRACE_MS
    )
    repo.host.return_value = None
    error("host_missing", lambda: service.host_presence(None, "room", 1000))
    with pytest.raises(ValueError):
        service.set_state(None, "room", "unknown")
