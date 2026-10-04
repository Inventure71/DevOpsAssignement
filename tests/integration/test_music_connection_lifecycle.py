"""Connection cancellation and session delivery over actual HTTP and SQLite."""

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from backend.music.admissions import LIFETIME_SECONDS
from tests.integration.test_music_admission import (
    MUSIC,
    await_status,
    begin,
    finish,
)
from tests.integration.test_music_admission import (
    normal_session as normal_session,  # noqa: PLC0414 - register shared pytest fixture
)


def callback(client, state, account):
    response = client.get(
        MUSIC + "/spotify/callback",
        params={"state": state, "code": account},
        follow_redirects=False,
    )
    assert response.status_code == 303


def count_players(session):
    with session["app"].state.coordinator.db.read() as conn:
        return conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]


def test_provider_configuration_and_selection_do_not_create_membership(normal_session):
    session, host = normal_session, normal_session["host"]
    providers = host.get(MUSIC + "/config").json()["providers"]
    assert providers["spotify"]["enabled"] is True
    assert providers["apple"] == {
        "id": "apple",
        "label": "Apple Music",
        "enabled": False,
        "reason": "Coming later",
    }
    for provider in ("apple", "unknown"):
        response = host.post(
            MUSIC + "/admissions", json={"nickname": "Host", "provider": provider}
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "music_provider_unavailable"
    state = begin(host, "Host")
    assert state and count_players(session) == 0
    status = host.get(MUSIC + "/status").json()
    assert status["admission_id"] != host.cookies.get("repeat_music_admission")
    assert status["connection"]["nickname"] == "Host"
    assert status["provider"] == "spotify"
    assert not any(key in status for key in ("state", "verifier", "context", "token"))


def test_back_during_import_prevents_late_membership(normal_session):
    session, host = normal_session, normal_session["host"]
    session["importer"].block_accounts = {"blocked"}
    state = begin(host, "Host")
    callback(host, state, "blocked")
    assert session["importer"].blocked.wait(2)
    assert host.post(MUSIC + "/acknowledge", json={}).status_code == 422
    receipt = host.get(MUSIC + "/status").json()
    assert host.post(
        MUSIC + "/acknowledge", json={"admission_id": receipt["admission_id"]}
    ).status_code == 409
    assert host.post(MUSIC + "/cancel", json={}).json() == {"status": "cancelled"}
    session["importer"].release.set()
    # Join queued worker completion: the absence assertion follows the attempted
    # import, so a late write cannot slip past this test's final observation.
    admissions = session["app"].state.music_admissions
    admissions._workers.shutdown(wait=True)
    admissions.close()
    assert host.get(MUSIC + "/status").status_code == 401
    assert count_players(session) == 0


def test_registered_provider_configuration_supersedes_deferred_placeholder(
    normal_session,
):
    admissions = normal_session["app"].state.music_admissions
    admissions.providers["apple"] = replace(
        admissions.providers["spotify"], label="Registered contract source"
    )
    providers = normal_session["host"].get(MUSIC + "/config").json()["providers"]
    assert providers["apple"]["id"] == "apple"
    assert providers["apple"]["enabled"] is True
    assert providers["apple"]["label"] == "Registered contract source"
    assert providers["apple"]["reason"] is None


def test_callback_at_exact_receipt_expiry_creates_no_membership(normal_session):
    admissions = normal_session["app"].state.music_admissions
    elapsed = [0]
    admissions.clock = lambda: elapsed[0]
    host = normal_session["host"]
    state = begin(host, "Host")
    elapsed[0] = LIFETIME_SECONDS
    response = host.get(
        MUSIC + "/spotify/callback",
        params={"state": state, "code": "expired"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/?music=error"
    assert host.get(MUSIC + "/status").status_code == 401
    assert count_players(normal_session) == 0


def test_receipt_expiry_during_persistence_rolls_back_all_admission_rows(
    normal_session, monkeypatch
):
    coordinator = normal_session["app"].state.coordinator
    admissions = normal_session["app"].state.music_admissions
    elapsed = [0]
    admissions.clock = lambda: elapsed[0]
    create = coordinator.rooms.create

    def expire_after_writes(*args, **kwargs):
        result = create(*args, **kwargs)
        elapsed[0] = LIFETIME_SECONDS
        return result

    monkeypatch.setattr(coordinator.rooms, "create", expire_after_writes)
    host = normal_session["host"]
    callback(host, begin(host, "Host"), "expiring-account")
    admissions._workers.shutdown(wait=True)
    assert host.get(MUSIC + "/status").status_code == 401
    with coordinator.db.read() as conn:
        for table in ("rooms", "players", "songs", "player_songs"):
            assert conn.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0


def test_completion_cancel_recovers_cookie_then_ack_allows_another_connection(
    normal_session,
):
    session, host = normal_session, normal_session["host"]
    result = finish(host, begin(host, "Host"), "host-account")
    recovering = session["new_client"]()
    cookie = next(c for c in host.cookies.jar if c.name == "repeat_music_admission")
    recovering.cookies.set(
        cookie.name, cookie.value, domain=cookie.domain, path=cookie.path
    )
    recovered = recovering.post(MUSIC + "/cancel", json={}).json()
    assert recovered["status"] == "complete"
    assert recovered["admission"] == result["admission"]
    assert recovered["admission_id"] == result["admission_id"]
    prefix = "/api/rooms/" + result["admission"]["room_id"]
    assert recovering.get(prefix + "/state").json()["me"]["nickname"] == "Host"
    payload = {"admission_id": recovered["admission_id"]}
    acknowledged = recovering.post(MUSIC + "/acknowledge", json=payload)
    assert "set-cookie" not in acknowledged.headers
    assert acknowledged.json() == {
        "acknowledged": True
    }
    assert recovering.post(MUSIC + "/acknowledge", json=payload).status_code == 200
    assert begin(recovering, "Other Host")
    assert count_players(session) == 1


@pytest.mark.parametrize("new_status", ["processing", "complete"])
def test_old_tab_acknowledgement_preserves_new_tabs_receipt_and_session(
    normal_session, new_status
):
    session, old_tab = normal_session, normal_session["host"]
    old_result = finish(old_tab, begin(old_tab, "Old Host"), "old-account")
    old_ack = {"admission_id": old_result["admission_id"]}
    # One tab retires A; another tab still holds its completed result and has
    # paused before acknowledging it. Both tabs use the browser's shared cookie.
    assert old_tab.post(MUSIC + "/acknowledge", json=old_ack).json() == {
        "acknowledged": True
    }
    new_tab = session["new_client"]()
    new_tab.cookies.update(old_tab.cookies)
    session["importer"].block_accounts = {"new-account"}
    callback(new_tab, begin(new_tab, "New Host"), "new-account")
    assert session["importer"].blocked.wait(2)
    admissions = session["app"].state.music_admissions
    if new_status == "complete":
        session["importer"].release.set()
        admissions._workers.shutdown(wait=True)
    cookie = new_tab.cookies.get("repeat_music_admission")
    assert admissions.status(cookie)[0]["status"] == new_status
    old_tab.cookies.update(new_tab.cookies)
    delayed = old_tab.post(MUSIC + "/acknowledge", json=old_ack)
    assert delayed.status_code == 200
    assert delayed.json() == {"acknowledged": False}
    assert "set-cookie" not in delayed.headers
    assert old_tab.cookies.get("repeat_music_admission") == cookie
    assert admissions.status(cookie)[0]["status"] == new_status
    # B has not polled for its completed result or received its room cookie yet.
    assert sum(
        c.name.startswith("repeat_") and c.path.startswith("/api/rooms/")
        for c in new_tab.cookies.jar
    ) == 1  # Only A's existing session.
    session["importer"].release.set()
    admissions._workers.shutdown(wait=True)
    new_result = await_status(new_tab)
    assert new_result["admission_id"] != old_result["admission_id"]
    room_id = new_result["admission"]["room_id"]
    state = new_tab.get("/api/rooms/" + room_id + "/state")
    assert state.status_code == 200
    assert state.json()["me"]["id"] == new_result["admission"]["player_id"]
    assert state.json()["me"]["nickname"] == "New Host"
    assert count_players(session) == 2
    current_ack = {"admission_id": new_result["admission_id"]}
    assert new_tab.post(MUSIC + "/acknowledge", json=current_ack).json() == {
        "acknowledged": True
    }
    assert new_tab.get("/api/rooms/" + room_id + "/state").status_code == 200
    assert new_tab.get(MUSIC + "/status").status_code == 401


def test_cancel_during_atomic_completion_returns_the_committed_session(normal_session):
    session, host = normal_session, normal_session["host"]
    admissions = session["app"].state.music_admissions
    admit = admissions.admit
    committed, release, cancel_started = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )

    def paused_delivery(payload, imported, valid):
        result = admit(payload, imported, valid)
        committed.set()
        assert release.wait(3)
        return result

    admissions.admit = paused_delivery
    state = begin(host, "Host")
    callback(host, state, "host-account")
    assert committed.wait(2)
    other = session["new_client"]()
    other.cookies.update(host.cookies)

    def cancel():
        cancel_started.set()
        return other.post(MUSIC + "/cancel", json={})

    with ThreadPoolExecutor(max_workers=1) as worker:
        cancellation = worker.submit(cancel)
        assert cancel_started.wait(2)
        try:
            assert not cancellation.done()
        finally:
            release.set()
        response = cancellation.result(timeout=3)
    assert response.json()["status"] == "complete"
    receipt = response.json()["admission"]
    assert other.get("/api/rooms/" + receipt["room_id"] + "/state").status_code == 200
    assert count_players(session) == 1


def test_unacknowledged_completed_receipt_does_not_restore_a_departed_player(
    normal_session,
):
    host = normal_session["host"]
    result = finish(host, begin(host, "Host"), "host-account")
    prefix = "/api/rooms/" + result["admission"]["room_id"]
    assert (
        host.post(
            prefix + "/leave", json={"request_id": "leave-before-ack"}
        ).status_code
        == 200
    )
    assert host.post(MUSIC + "/cancel", json={}).json() == {"status": "cancelled"}
    assert host.get(MUSIC + "/status").status_code == 401
    assert begin(host, "New Host")


def test_failed_authorization_retains_only_connection_draft(normal_session):
    session, host = normal_session, normal_session["host"]
    state = begin(host, "Host")
    response = host.get(
        MUSIC + "/spotify/callback",
        params={"state": state, "error": "access_denied"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    result = await_status(host)
    assert result["status"] == "failed"
    assert result["connection"]["nickname"] == "Host"
    receipt = next(iter(session["app"].state.music_admissions._receipts.values()))
    assert receipt.context is None
    assert count_players(session) == 0
