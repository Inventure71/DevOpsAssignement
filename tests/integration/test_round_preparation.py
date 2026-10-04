"""Upcoming readiness through real SQLite while the scored round stays current."""

import json
import sqlite3

import pytest

from backend.application.coordinator import Coordinator
from tests.support.demo import demo_config
from backend.core.errors import DomainError
from backend.core.paths import MIGRATIONS_DIR
from backend.game.views import game_view
from backend.storage.database import MIGRATIONS, Database
from tests.integration.test_game import Match

LEASE = "current-audio-lease"


@pytest.fixture
def revealed(tmp_path):
    match = Match(tmp_path, rounds=5)
    match.preload()
    match.answering()
    match.close()
    return match


def pending(match):
    with match.db.read() as conn:
        return match.game.repo.pending_preparation(conn, match.game_id)


def acknowledge(match, player_ids=None, *, at=None, lease=LEASE, browser="browser"):
    preparation = pending(match)
    with match.db.transaction() as conn:
        for player_id in match.ids if player_ids is None else player_ids:
            match.game.prepare_upcoming(
                conn,
                match.game_id,
                preparation["id"],
                player_id,
                {
                    "readiness_generation": preparation["readiness_generation"],
                    "browser_id": browser + "-" + player_id,
                    "lease_id": lease if player_id == match.host else None,
                },
                match.now if at is None else at,
            )


def promote(match, *, lease=LEASE, connected=None):
    game, _ = match.fetch()
    # May already be in leaderboard after a separate advance.
    when = game["phase_ends_at_ms"] + (5000 if game["phase"] == "reveal" else 0)
    match.now = when
    with match.db.transaction() as conn:
        match.game.advance(
            conn,
            match.game_id,
            when,
            host_lease_id=lease,
            connected_player_ids=set(match.ids) if connected is None else connected,
        )
    return match.fetch()


def test_preparation_preserves_current_reveal_and_guest_privacy(revealed):
    match = revealed
    old_game, old_round = match.fetch()
    preparation = pending(match)
    assert preparation["round_number"] == 2
    assert preparation["id"] != old_round["id"]
    acknowledge(match)
    with match.db.read() as conn:
        game = match.game.repo.game(conn, match.game_id)
        current = match.game.repo.current(conn, match.game_id)
        assert current == old_round
        assert game["phase"] == old_game["phase"] == "reveal"
        assert len(match.game.repo.attempts(conn, match.game_id)) == 1
        guest = game_view(match.game.repo, conn, game, match.ids[1])
        host = game_view(match.game.repo, conn, game, match.host, host=True)
        assert guest["round"]["id"] == old_round["id"]
        assert guest["round"]["reveal"] is not None
        assert set(guest["upcoming_round"]) == {
            "id",
            "round_number",
            "readiness_generation",
        }
        assert host["upcoming_round"] == {
            **guest["upcoming_round"],
            "audio_candidate_id": preparation["song_key"],
        }
        assert guest["leaderboard"] == host["leaderboard"]


def test_fresh_preparation_promotes_to_full_countdown_after_results(revealed):
    match = revealed
    preparation = pending(match)
    closed_at = match.now
    acknowledge(match, at=closed_at + 9999)
    match.advance(closed_at + 9999)
    assert match.fetch()[0]["phase"] == "leaderboard"
    assert match.fetch()[1]["round_number"] == 1
    game, current = promote(match)
    assert current["id"] == preparation["id"]
    assert current["round_number"] == 2
    assert game["phase"] == "countdown"
    assert current["starts_at_ms"] == closed_at + 13_000
    assert current["deadline_at_ms"] == current["starts_at_ms"] + 10_000
    assert set(json.loads(current["ready_player_ids_json"])) == set(match.ids)
    assert current["readiness_deadline_at_ms"] == closed_at + 20_000
    assert pending(match) is None
    with match.db.read() as conn:
        view = game_view(match.game.repo, conn, game, match.ids[1])
        assert view["upcoming_round"] is None


@pytest.mark.parametrize("age,carried", [(5000, True), (5001, False), (-1, False)])
def test_acknowledgement_freshness_boundary(revealed, age, carried):
    match = revealed
    acknowledge(match, at=match.now + 10_000 - age)
    game, current = promote(match)
    assert game["phase"] == ("countdown" if carried else "ready")
    assert bool(json.loads(current["ready_player_ids_json"])) is carried


def test_repeated_acknowledgement_renews_freshness(revealed):
    match = revealed
    acknowledge(match)
    acknowledge(match, at=match.now + 9000, browser="renewed-browser")
    preparation = pending(match)
    host_ack = preparation["acknowledgements"][match.host]
    assert host_ack["prepared_at_ms"] == match.now + 9000
    assert host_ack["browser_id"].startswith("renewed-browser")
    assert promote(match)[0]["phase"] == "countdown"


def test_missing_preparation_falls_back_and_can_complete_normal_readiness(revealed):
    match = revealed
    acknowledge(match, match.ids[:2], at=match.now + 9000)
    game, current = promote(match)
    assert game["phase"] == "ready"
    assert set(json.loads(current["ready_player_ids_json"])) == set(match.ids[:2])
    assert current["readiness_deadline_at_ms"] == match.now + 10_000
    match.ready([match.ids[2]])
    game, current = match.fetch()
    assert game["phase"] == "countdown"
    assert current["starts_at_ms"] == match.now + 3000


@pytest.mark.parametrize("lease", [None, "replacement-audio-lease"])
def test_old_host_lease_is_not_carried(revealed, lease):
    match = revealed
    acknowledge(match, at=match.now + 9000)
    game, current = promote(match, lease=lease)
    assert game["phase"] == "ready"
    assert set(json.loads(current["ready_player_ids_json"])) == set(match.ids[1:])


def test_disconnected_prepared_player_is_not_carried(revealed):
    match = revealed
    acknowledge(match, at=match.now + 9000)
    game, current = promote(match, connected=set(match.ids[:2]))
    assert game["phase"] == "ready"
    assert set(json.loads(current["ready_player_ids_json"])) == set(match.ids[:2])


def test_takeover_clears_only_upcoming_host_acknowledgement(revealed):
    match = revealed
    acknowledge(match, at=match.now + 9000)
    with match.db.transaction() as conn:
        match.game.invalidate_upcoming_host(conn, match.game_id, match.host)
    assert set(pending(match)["acknowledgements"]) == set(match.ids[1:])
    assert promote(match)[0]["phase"] == "ready"


@pytest.mark.parametrize("wrong", ["id", "generation", "actor"])
def test_unissued_preparation_and_nonmember_are_rejected(revealed, wrong):
    match = revealed
    preparation = pending(match)
    payload = {
        "readiness_generation": preparation["readiness_generation"]
        + (wrong == "generation"),
        "browser_id": "browser",
        "lease_id": LEASE,
    }
    with match.db.transaction() as conn, pytest.raises(DomainError) as error:
        match.game.prepare_upcoming(
            conn,
            match.game_id,
            "unissued" if wrong == "id" else preparation["id"],
            "outsider" if wrong == "actor" else match.host,
            payload,
            match.now,
        )
    assert (
        error.value.code
        == {
            "id": "stale_preparation",
            "generation": "stale_generation",
            "actor": "game_not_found",
        }[wrong]
    )
    assert pending(match)["acknowledgements"] == {}


def test_late_acknowledgement_cannot_modify_promoted_round(revealed):
    match = revealed
    preparation = pending(match)
    promote(match)
    before = match.fetch()[1]
    with match.db.transaction() as conn, pytest.raises(DomainError) as error:
        match.game.prepare_upcoming(
            conn,
            match.game_id,
            preparation["id"],
            match.host,
            {"readiness_generation": 1, "browser_id": "browser", "lease_id": LEASE},
            match.now,
        )
    assert error.value.code == "stale_preparation"
    assert match.fetch()[1] == before


def test_skipped_slot_is_not_exposed_as_upcoming(tmp_path):
    match = Match(tmp_path, rounds=5)
    match.preload(failed_slots={2})
    match.answering()
    match.close()
    assert pending(match)["round_number"] == 3
    acknowledge(match, at=match.now + 9000)
    assert promote(match)[1]["round_number"] == 3


def test_candidate_replacement_does_not_inherit_old_acknowledgements(revealed):
    match = revealed
    preparation = pending(match)
    acknowledge(match, at=match.now + 9000)
    with match.db.transaction() as conn:
        game = match.game.repo.game(conn, match.game_id)
        plan = json.loads(game["round_plan_json"])
        plan[1]["chosen_index"] = 1
        match.game.repo.update_game(
            conn, match.game_id, round_plan_json=json.dumps(plan)
        )
    game, current = promote(match)
    assert game["phase"] == "ready"
    assert current["id"] != preparation["id"]
    assert json.loads(current["ready_player_ids_json"]) == []


def test_promotion_failure_rolls_back_preparation_and_round(revealed, monkeypatch):
    match = revealed
    match.advance(match.now + 5000)
    acknowledge(match, at=match.now + 4999)
    preparation = pending(match)
    before = match.fetch()
    original = match.game.repo.insert

    def fail_round(conn, table, values):
        if table == "rounds":
            raise sqlite3.IntegrityError("simulated round insert failure")
        return original(conn, table, values)

    monkeypatch.setattr(match.game.repo, "insert", fail_round)
    with pytest.raises(sqlite3.IntegrityError):
        promote(match)
    assert match.fetch() == before
    assert pending(match) == preparation


@pytest.mark.parametrize("reason", ["host_ended", "server_restart"])
def test_finish_and_startup_remove_pending_preparation(revealed, tmp_path, reason):
    match = revealed
    acknowledge(match)
    if reason == "server_restart":
        coordinator = Coordinator(
            demo_config(tmp_path), clock=lambda: match.now, game=match.game
        )
        coordinator.initialize()
    else:
        with match.db.transaction() as conn:
            match.game.finish(conn, match.game_id, match.now, reason)
    assert pending(match) is None
    assert match.fetch()[0]["end_reason"] == reason


def test_game_deletion_cascades_pending_preparation(revealed):
    match = revealed
    with match.db.transaction() as conn:
        match.game.repo.delete_room_games(conn, match.room_id)
    assert pending(match) is None


def test_final_round_has_no_pending_preparation_and_keeps_results_timers(tmp_path):
    match = Match(tmp_path, rounds=5)
    match.preload()
    for number in range(1, 6):
        match.answering()
        match.close()
        if number < 5:
            match.next()
    assert pending(match) is None
    closed_at = match.now
    match.advance(closed_at + 9999)
    assert match.fetch()[0]["phase"] == "leaderboard"
    match.advance(closed_at + 10_000)
    assert match.fetch()[0]["status"] == "completed"


def test_version_five_database_upgrades_without_losing_rooms(tmp_path):
    path = tmp_path / "historical.sqlite3"
    with sqlite3.connect(path) as conn:
        for filename in MIGRATIONS[:5]:
            conn.executescript((MIGRATIONS_DIR / filename).read_text())
        conn.execute("PRAGMA user_version=5")
        conn.execute(
            "INSERT INTO rooms (id,code,mode,created_at_ms) "
            "VALUES ('retained','ABCDEF','demo',1000)"
        )
    database = Database(path)
    database.initialize()
    database.initialize()
    with database.read() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
        assert conn.execute("SELECT id FROM rooms").fetchone()[0] == "retained"
        assert (
            conn.execute("SELECT COUNT(*) FROM game_round_preparations").fetchone()[0]
            == 0
        )
