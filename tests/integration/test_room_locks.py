"""Rejected room requests and queued commands do not retain or replace locks."""

import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from backend.app import create_app
from tests.support.demo import demo_config


def test_unknown_room_requests_release_registry_entries(tmp_path):
    app = create_app(demo_config(tmp_path), background=False)
    with TestClient(app) as client:
        for index in range(100):
            response = client.get(f"/api/rooms/unknown-{index}/state")
            assert response.status_code == 404
        coordinator = app.state.coordinator
        assert len(coordinator._locks) == 0
        coordinator.cleanup()
        assert len(coordinator._locks) == 0


def test_reentrant_holder_and_queued_commands_remain_serialized(tmp_path):
    app = create_app(demo_config(tmp_path), background=False)
    coordinator = app.state.coordinator
    entered, release, waiter_started = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    order = []

    def holder():
        with coordinator.room_lock("same-room"):
            with coordinator.room_lock("same-room"):
                order.append("holder")
                entered.set()
                assert release.wait(3)
            order.append("holder-exits")

    def waiter():
        waiter_started.set()
        with coordinator.room_lock("same-room"):
            order.append("waiter")

    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(holder)
        assert entered.wait(2)
        second = pool.submit(waiter)
        assert waiter_started.wait(2)

        # A slow room cannot prevent another room's command turn.
        def independent():
            with coordinator.room_lock("other-room"):
                return "independent"

        assert pool.submit(independent).result(timeout=1) == "independent"
        assert not second.done()
        release.set()
        first.result(timeout=2)
        second.result(timeout=2)
    assert order == ["holder", "holder-exits", "waiter"]
    assert len(coordinator._locks) == 0


def test_failed_command_does_not_retain_its_lock(tmp_path):
    coordinator = create_app(demo_config(tmp_path), background=False).state.coordinator
    try:
        with coordinator.room_lock("failed-room"):
            raise ValueError("operation failed")
    except ValueError:
        pass
    assert len(coordinator._locks) == 0
    with coordinator.room_lock("failed-room"):
        assert len(coordinator._locks) == 1
    assert len(coordinator._locks) == 0
