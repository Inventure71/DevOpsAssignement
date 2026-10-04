"""Game behavior through frozen Rooms snapshots and real SQLite transactions."""

import json
import random
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.application.coordinator import Coordinator
from backend.core.errors import DomainError
from backend.game.service import GameService
from backend.game.views import audio_manifest, game_view
from backend.rooms.service import RETENTION_MS, RoomsService
from backend.storage.database import Database
from tests.support.catalog import write_large_catalog
from tests.support.demo import demo_config, make_demo_pack


class Clock:
    def __init__(self, now=1000):
        self.now = now

    def __call__(self):
        return self.now


class Match:
    def __init__(self, directory, rounds=10, shared_artists=False, player_count=3):
        directory.mkdir(parents=True, exist_ok=True)
        self.db = Database(directory / "whos_on_repeat.sqlite3")
        self.rooms = RoomsService()
        self.game = GameService(random.Random(17), setup_timeout_ms=60_000)
        self.now = 1000
        self.catalog_path = write_large_catalog(directory / "test_catalog.json")
        requested = json.loads(self.catalog_path.read_text())
        self.demo_pack = make_demo_pack(directory / "media", entries=requested)
        self.catalog_path = self.demo_pack / "demo_catalog.json"
        # Keep artwork coverage in frozen-snapshot tests with isolated SVG media.
        entries = json.loads(self.catalog_path.read_text())
        for source, entry in zip(requested, entries):
            if source["artwork_url"]:
                entry["artwork_url"] = source["artwork_url"]
                asset = (
                    self.demo_pack
                    / "assets"
                    / source["artwork_url"].removeprefix("/static/demo/local/")
                )
                asset.parent.mkdir(parents=True, exist_ok=True)
                asset.write_text(
                    '<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>'
                )
        self.catalog_path.write_text(json.dumps(entries), encoding="utf-8")
        self.coordinator = Coordinator(
            demo_config(directory, demo_pack_dir=self.demo_pack),
            clock=Clock(self.now),
            game=self.game,
        )
        self.coordinator.initialize()
        self.settings = {
            "round_count": rounds,
            "answer_seconds": 10,
            "difficulty": "mixed",
            "decoys_enabled": True,
        }
        with self.db.transaction() as conn:
            host = self.rooms.create(conn, "Host", "coral", "demo", self.now)
            self.room_id, self.host, self.token = (
                host["room"]["id"],
                host["player"]["id"],
                host["token"],
            )
            guests = [
                self.rooms.join(
                    conn, self.room_id, f"Guest {i}", "lavender", self.now + i
                )
                for i in range(1, player_count)
            ]
            self.ids = [self.host, *(guest["player"]["id"] for guest in guests)]
            self.tokens = {
                host["player"]["id"]: host["token"],
                **{guest["player"]["id"]: guest["token"] for guest in guests},
            }
            if shared_artists:
                conn.execute(
                    "UPDATE songs SET artists_json=? WHERE room_id=?",
                    (
                        json.dumps(
                            [{"artist_key": "demo:shared", "name": "Shared Artist"}]
                        ),
                        self.room_id,
                    ),
                )
            snapshot = self.rooms.snapshot(conn, self.room_id)
            self.start_payload = {
                "request_id": "start-one",
                "room_revision": snapshot["revision"],
            }
            self.game_id = self.game.start(
                conn, snapshot, self.settings, self.host, self.start_payload, self.now
            )["game_id"]
            self.rooms.set_state(conn, self.room_id, "playing")

    def fetch(self):
        with self.db.read() as conn:
            return self.game.repo.game(conn, self.game_id), self.game.repo.current(
                conn, self.game_id
            )

    def advance(self, now, host_connected=True):
        self.now = now
        with self.db.transaction() as conn:
            self.game.advance(conn, self.game_id, self.now, host_connected)

    def preload(self, failed_slots=(), host_connected=True):
        with self.db.transaction() as conn:
            plan = json.loads(
                self.game.repo.game(conn, self.game_id)["round_plan_json"]
            )
            for slot in plan:
                for candidate in slot["candidates"]:
                    self.game.preload(
                        conn,
                        self.game_id,
                        self.host,
                        {
                            "request_id": "check-" + candidate["song_key"],
                            "candidate_id": candidate["song_key"],
                            "ok": slot["round_number"] not in failed_slots,
                        },
                        self.now,
                    )
        self.advance(6000, host_connected=host_connected)

    def ready(self, player_ids=None):
        with self.db.transaction() as conn:
            attempt = self.game.repo.current(conn, self.game_id)
            for player_id in self.ids if player_ids is None else player_ids:
                self.game.ready(
                    conn,
                    self.game_id,
                    attempt["id"],
                    player_id,
                    attempt["readiness_generation"],
                    self.now,
                )

    def answering(self):
        self.ready()
        _, attempt = self.fetch()
        self.advance(attempt["starts_at_ms"])

    def submit(self, actor, song_guess=None, who=(), now=None):
        if now is not None:
            self.now = now
        with self.db.transaction() as conn:
            attempt = self.game.repo.current(conn, self.game_id)
            return self.game.answer(
                conn,
                self.game_id,
                attempt["id"],
                actor,
                {"song_guess": song_guess, "who_player_ids": list(who)},
                self.now,
            )

    def correct(self):
        with self.db.read() as conn:
            game, attempt = (
                self.game.repo.game(conn, self.game_id),
                self.game.repo.current(conn, self.game_id),
            )
            songs = {
                song["song_key"]: song
                for song in json.loads(game["songs_snapshot_json"])
            }
            song = songs[attempt["song_key"]]
            return song, [item["player_id"] for item in song["listeners"]]

    def close(self):
        _, attempt = self.fetch()
        self.advance(attempt["deadline_at_ms"])

    def next(self):
        game, _ = self.fetch()
        assert game["phase"] == "reveal"
        self.advance(game["phase_ends_at_ms"] + 5000)


@pytest.fixture
def match(tmp_path):
    return Match(tmp_path)


def test_submitted_nobody_and_missing_answer_remain_distinct_on_decoy(match):
    match.preload()
    # Reach the planned decoy through the normal automatic round loop.
    while True:
        match.answering()
        _, attempt = match.fetch()
        if attempt["difficulty"] == "decoy":
            break
        match.close()
        match.next()
    match.submit(match.host, None, ())
    match.close()
    with match.db.read() as conn:
        answers = {
            answer["player_id"]: answer
            for answer in match.game.repo.answers(conn, attempt["id"])
        }
        assert answers[match.host]["who_mode"] == "nobody"
        assert (
            answers[match.host]["status"] == "submitted"
            and answers[match.host]["points"] == 100
        )
        missing = answers[match.ids[1]]
        assert missing["status"] == "missing" and missing["who_mode"] == "blank"
        assert missing["received_at_ms"] is None and missing["points"] == 0


def test_artist_partial_credit_is_scored_from_frozen_structured_ids(tmp_path):
    match = Match(tmp_path, shared_artists=True)
    match.preload()
    match.answering()
    correct, listeners = match.correct()
    with match.db.read() as conn:
        game, attempt = (
            match.game.repo.game(conn, match.game_id),
            match.game.repo.current(conn, match.game_id),
        )
        songs = {
            song["song_key"]: song for song in json.loads(game["songs_snapshot_json"])
        }
        wrong = next(
            song
            for song in songs.values()
            if song["song_key"] != correct["song_key"]
            and song["artists"][0]["artist_key"] == "demo:shared"
        )
    match.submit(match.host, wrong, listeners, match.now + 2000)
    match.close()
    with match.db.read() as conn:
        answer = next(
            answer
            for answer in match.game.repo.answers(conn, attempt["id"])
            if answer["player_id"] == match.host
        )
        expected = {"easy": 150, "medium": 225, "hard": 300}[attempt["difficulty"]]
        assert answer["points"] == expected  # No speed or perfect multiplier.


def test_void_attempt_retains_diagnostic_150_but_only_replacement_is_ranked(match):
    match.preload()
    match.answering()
    _, old = match.fetch()
    match.submit(match.host, None, ())
    payload = {
        "request_id": "failed-clip",
        "readiness_generation": old["readiness_generation"],
        "reason": "decode_failed",
    }
    with match.db.transaction() as conn:
        conn.execute(
            "UPDATE answers SET points=150 WHERE round_id=? AND player_id=?",
            (old["id"], match.host),
        )
        receipt = match.game.audio_failure(
            conn, match.game_id, old["id"], match.host, payload, match.now
        )
        assert (
            match.game.audio_failure(
                conn, match.game_id, old["id"], match.host, payload, match.now + 1
            )
            == receipt
        )
        assert (
            next(
                item
                for item in match.game.repo.leaderboard(conn, match.game_id)
                if item["player_id"] == match.host
            )["score"]
            == 0
        )
    _, replacement = match.fetch()
    assert (
        replacement["round_number"] == old["round_number"]
        and replacement["attempt"] == old["attempt"] + 1
    )
    assert replacement["song_key"] != old["song_key"]
    match.answering()
    correct, listeners = match.correct()
    match.submit(match.host, correct, listeners, match.now + 1000)
    match.close()
    with match.db.read() as conn:
        diagnostic = match.game.repo.answers(conn, old["id"])[0]
        actual = next(
            answer
            for answer in match.game.repo.answers(conn, replacement["id"])
            if answer["player_id"] == match.host
        )
        assert diagnostic["points"] == 150
        assert (
            next(
                item
                for item in match.game.repo.leaderboard(conn, match.game_id)
                if item["player_id"] == match.host
            )["score"]
            == actual["points"]
        )
        assert match.game.skipped(conn, match.game_id) == 0


def test_reveal_is_terminal_and_late_audio_failure_cannot_change_scores(match):
    match.preload()
    match.answering()
    match.close()
    _, attempt = match.fetch()
    with match.db.transaction() as conn:
        before = match.game.repo.leaderboard(conn, match.game_id)
        with pytest.raises(DomainError) as error:
            match.game.audio_failure(
                conn,
                match.game_id,
                attempt["id"],
                match.host,
                {"request_id": "late", "readiness_generation": 1},
                match.now,
            )
        assert error.value.code == "reveal_final"
        assert match.game.repo.leaderboard(conn, match.game_id) == before


def test_later_retry_resets_barrier_not_attempt_budget_or_answers(match):
    match.preload()
    match.answering()
    match.close()
    match.next()
    match.ready([match.host])
    _, attempt = match.fetch()
    match.advance(attempt["readiness_deadline_at_ms"])
    payload = {
        "request_id": "retry-round-two",
        "readiness_generation": attempt["readiness_generation"],
    }
    with match.db.transaction() as conn:
        receipt = match.game.readiness_command(
            conn, match.game_id, attempt["id"], match.host, "retry", payload, match.now
        )
        assert (
            match.game.readiness_command(
                conn,
                match.game_id,
                attempt["id"],
                match.host,
                "retry",
                payload,
                match.now + 1,
            )
            == receipt
        )
        current = match.game.repo.current(conn, match.game_id)
        assert (
            current["id"] == attempt["id"] and current["attempt"] == attempt["attempt"]
        )
        assert current["readiness_generation"] == 2
        assert json.loads(current["ready_player_ids_json"]) == []
        assert json.loads(current["excluded_player_ids_json"]) == []
        assert match.game.repo.answers(conn, attempt["id"]) == []
        with pytest.raises(DomainError) as error:
            match.game.ready(
                conn, match.game_id, attempt["id"], match.host, 1, match.now
            )
        assert error.value.code == "stale_generation"
    match.answering()
    assert match.fetch()[0]["phase"] == "answering"


def test_continue_excludes_barrier_only_and_still_accepts_reconnecting_player(match):
    match.preload()
    match.answering()
    match.close()
    match.next()
    match.ready(match.ids[:2])
    _, attempt = match.fetch()
    match.advance(attempt["readiness_deadline_at_ms"])
    with match.db.transaction() as conn:
        match.game.readiness_command(
            conn,
            match.game_id,
            attempt["id"],
            match.host,
            "continue",
            {
                "request_id": "continue-two",
                "readiness_generation": 1,
                "exclude_player_ids": [match.ids[2]],
            },
            match.now,
        )
        assert len(match.game.repo.roster(conn, match.game_id)) == 3
        assert match.game.repo.answers(conn, attempt["id"]) == []
    _, current = match.fetch()
    match.advance(current["starts_at_ms"])
    match.submit(match.host)
    match.submit(match.ids[1])
    assert (
        match.fetch()[0]["phase"] == "answering"
    )  # Excluded player still counts for early closure.
    match.submit(match.ids[2])
    assert match.fetch()[0]["phase"] == "reveal"
    match.next()
    _, next_attempt = match.fetch()
    assert json.loads(next_attempt["excluded_player_ids_json"]) == []


@pytest.mark.parametrize(
    "requested,skips,aborted",
    [
        (5, 2, True),
        (15, 4, False),
    ],
)
def test_setup_skip_policy_uses_original_requested_denominator(
    tmp_path, requested, skips, aborted
):
    match = Match(tmp_path, rounds=requested)
    match.preload(range(1, skips + 1))
    game, attempt = match.fetch()
    assert (game["status"] == "aborted") is aborted
    with match.db.read() as conn:
        assert match.game.skipped(conn, match.game_id) == skips
        if aborted:
            assert game["end_reason"] == "too_many_skipped" and attempt is None
        else:
            assert attempt["round_number"] == skips + 1
            view = game_view(match.game.repo, conn, game, match.host, True)
            assert (
                view["requested_rounds"] == requested
                and view["playable_rounds"] == requested - skips
            )


def test_runtime_three_replacements_per_slot_and_cumulative_strict_30_percent(match):
    match.preload()
    match.answering()
    failed_song_keys = set()
    for round_number in range(1, 5):
        for attempt_number in range(1, 5):
            game, attempt = match.fetch()
            assert (
                attempt["round_number"] == round_number
                and attempt["attempt"] == attempt_number
            )
            assert attempt["song_key"] not in failed_song_keys
            failed_song_keys.add(attempt["song_key"])
            with match.db.transaction() as conn:
                match.game.audio_failure(
                    conn,
                    match.game_id,
                    attempt["id"],
                    match.host,
                    {
                        "request_id": "fail-" + attempt["id"],
                        "readiness_generation": attempt["readiness_generation"],
                    },
                    match.now,
                )
        if round_number <= 3:
            assert match.fetch()[0]["status"] == "playing"  # Exactly 30% is allowed.
    game, _ = match.fetch()
    assert game["status"] == "aborted" and game["end_reason"] == "too_many_skipped"
    with match.db.read() as conn:
        attempts = match.game.repo.attempts(conn, match.game_id)
        assert len(attempts) == 16 and all(
            attempt["status"] == "void" for attempt in attempts
        )
        assert match.game.skipped(conn, match.game_id) == 4


def test_start_and_host_commands_are_durably_idempotent_with_bound_payloads(match):
    with match.db.transaction() as conn:
        snapshot = match.rooms.snapshot(conn, match.room_id)
        receipt = match.game.start(
            conn, snapshot, match.settings, match.host, match.start_payload, match.now
        )
        assert receipt == {"game_id": match.game_id}
        with pytest.raises(DomainError) as error:
            match.game.start(
                conn,
                snapshot,
                match.settings,
                match.host,
                {**match.start_payload, "room_revision": snapshot["revision"]},
                match.now,
            )
        assert error.value.code == "request_conflict"
        payload = {"request_id": "end-one"}
        match.game.end(conn, match.game_id, match.host, payload, match.now)
        assert match.game.end(conn, match.game_id, match.host, payload, match.now) == {
            "accepted": True
        }
        assert (
            match.game.start(
                conn,
                snapshot,
                match.settings,
                match.host,
                match.start_payload,
                match.now,
            )
            == receipt
        )
        with pytest.raises(DomainError):
            match.game.end(
                conn,
                match.game_id,
                match.ids[1],
                {"request_id": "guest-end"},
                match.now,
            )
        assert (
            len(
                list(
                    conn.execute(
                        "SELECT id FROM games WHERE room_id=?", (match.room_id,)
                    )
                )
            )
            == 1
        )


def test_live_metadata_edits_do_not_mutate_frozen_game_roster_or_plan(match):
    match.preload()
    with match.db.transaction() as conn:
        before = match.game.repo.game(conn, match.game_id)
        assert any(
            song["artwork_url"] for song in json.loads(before["songs_snapshot_json"])
        )
        frozen_roster = match.game.repo.roster(conn, match.game_id)
        conn.execute(
            "UPDATE songs SET title='Changed', artwork_url=NULL, artists_json=? WHERE room_id=?",
            (
                json.dumps([{"artist_key": "demo:changed", "name": "Changed"}]),
                match.room_id,
            ),
        )
        conn.execute(
            "UPDATE players SET nickname='Changed', character_id='lilac' WHERE id=?",
            (match.host,),
        )
        after = match.game.repo.game(conn, match.game_id)
        assert after["songs_snapshot_json"] == before["songs_snapshot_json"]
        assert after["round_plan_json"] == before["round_plan_json"]
        assert match.game.repo.roster(conn, match.game_id) == frozen_roster


def test_public_phase_views_hide_correct_markers_listeners_and_other_guesses(match):
    match.preload()
    match.answering()
    match.submit(match.host, match.correct()[0], [match.ids[1]])
    with match.db.read() as conn:
        game = match.game.repo.game(conn, match.game_id)
        public = game_view(match.game.repo, conn, game, match.ids[1])
        assert public["round"]["submitted_player_ids"] == [match.host]
        assert (
            public["round"]["my_answer"] is None and public["round"]["reveal"] is None
        )
        assert "correct_option" not in json.dumps(public)
        assert "song_match" not in json.dumps(public)
        assert "listener_ids" not in json.dumps(public)
        assert "audio_candidate_id" not in public["round"]
        manifest = audio_manifest(game)
        assert all(
            set(candidate) == {"candidate_id", "preview_url"}
            for candidate in manifest["candidates"]
        )
    match.close()
    with match.db.read() as conn:
        game = match.game.repo.game(conn, match.game_id)
        for player_id in match.ids:
            reveal = game_view(match.game.repo, conn, game, player_id)["round"][
                "reveal"
            ]
            assert set(reveal) == {"song", "listener_ids", "my_answer"}
            assert reveal["my_answer"]["player_id"] == player_id
            assert "artwork_url" in reveal["song"]
            if player_id == match.host:
                assert reveal["my_answer"]["status"] == "submitted"
                assert reveal["my_answer"]["who_player_ids"] == [match.ids[1]]
            else:
                assert reveal["my_answer"]["status"] == "missing"
                assert reveal["my_answer"]["who_player_ids"] is None


def test_round_finishes_but_next_round_waits_when_host_temporarily_disconnected(match):
    match.preload()
    match.answering()
    _, attempt = match.fetch()
    match.advance(attempt["deadline_at_ms"] + 10_000, host_connected=False)
    assert match.fetch()[0]["phase"] == "leaderboard"
    assert match.fetch()[1]["round_number"] == 1
    match.advance(match.now + 1, host_connected=True)
    assert (
        match.fetch()[0]["phase"] == "ready" and match.fetch()[1]["round_number"] == 2
    )


def test_final_leaderboard_completes_while_host_disconnected_within_grace(tmp_path):
    match = Match(tmp_path, rounds=5)
    match.preload()
    for round_number in range(1, 6):
        with match.db.transaction() as conn:
            match.rooms.heartbeat(conn, match.room_id, match.host, match.now)
        match.answering()
        match.close()
        if round_number < 5:
            match.next()
    game, _ = match.fetch()
    final_time = game["phase_ends_at_ms"] + 5000
    with match.db.read() as conn:
        presence = match.rooms.host_presence(conn, match.room_id, final_time)
        assert not presence["connected"] and final_time < presence["expires_at_ms"]
    coordinator = match.coordinator
    coordinator.clock = Clock(final_time)
    coordinator.tick()
    with match.db.read() as conn:
        finished = match.game.repo.game(conn, match.game_id)
        assert (
            finished["status"] == "completed" and finished["end_reason"] == "completed"
        )
        assert all(
            player["final_score"] is not None
            for player in match.game.repo.roster(conn, match.game_id)
        )
        room = match.rooms.room(conn, match.room_id, final_time)
        assert room["state"] == "lobby" and room["last_completed_at_ms"] == final_time


def test_restart_aborts_active_attempt_and_preserves_revealed_scores_without_retention_renewal(
    tmp_path, monkeypatch
):
    match = Match(tmp_path)
    match.preload()
    match.answering()
    correct, listeners = match.correct()
    match.submit(match.host, correct, listeners)
    match.close()
    match.next()
    match.answering()
    match.submit(match.host)
    with match.db.read() as conn:
        expected = match.game.repo.leaderboard(conn, match.game_id)
    coordinator = Coordinator(
        demo_config(tmp_path, demo_pack_dir=match.demo_pack), clock=Clock(match.now + 1)
    )
    coordinator.initialize()
    with coordinator.db.read() as conn:
        game = coordinator.game.repo.game(conn, match.game_id)
        assert game["status"] == "aborted" and game["end_reason"] == "server_restart"
        assert coordinator.game.repo.current(conn, match.game_id)["status"] == "void"
        assert coordinator.game.repo.leaderboard(conn, match.game_id) == expected
        room = coordinator.rooms.room(conn, match.room_id, match.now + 1)
        assert room["state"] == "lobby" and room["last_completed_at_ms"] is None
        assert (
            coordinator.rooms.authenticate(
                conn, match.room_id, match.token, match.now + 1
            )["id"]
            == match.host
        )


def test_coordinator_retention_deletes_cross_domain_history_without_deleting_shared_catalog(
    tmp_path, monkeypatch
):
    match = Match(tmp_path)
    clock = Clock(match.now + 1)
    coordinator = Coordinator(
        demo_config(tmp_path, demo_pack_dir=match.demo_pack), clock=clock
    )
    coordinator.initialize()
    other = coordinator.admission(
        lambda conn, now: coordinator.rooms.create(conn, "Other", "lemon", "demo", now)
    )
    clock.now = 1000 + RETENTION_MS
    coordinator.cleanup()
    with coordinator.db.read() as conn:
        assert coordinator.game.repo.game(conn, match.game_id) is None
        assert (
            coordinator.rooms.room(conn, other["room"]["id"], clock.now)["id"]
            == other["room"]["id"]
        )
        assert conn.execute("SELECT COUNT(*) FROM demo_catalog").fetchone()[0] == 120
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_concurrent_last_answers_close_once_through_real_coordinator(
    match, monkeypatch
):
    match.preload()
    match.answering()
    _, attempt = match.fetch()
    match.submit(match.host)
    coordinator = match.coordinator
    coordinator.clock = Clock(match.now)
    barrier = threading.Barrier(2)
    closed = []
    original_close = match.game._close

    def count_close(conn, game, current, now):
        closed.append(current["id"])
        return original_close(conn, game, current, now)

    monkeypatch.setattr(match.game, "_close", count_close)
    guests = [(player_id, match.tokens[player_id]) for player_id in match.ids[1:]]

    def submit(guest):
        _, token = guest
        barrier.wait(timeout=5)
        return coordinator.execute(
            match.room_id,
            token,
            lambda conn, player, now: match.game.answer(
                conn,
                match.game_id,
                attempt["id"],
                player["id"],
                {"song_guess": None, "who_player_ids": []},
                now,
            ),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        receipts = list(executor.map(submit, guests))
    assert all(receipt["accepted"] for receipt in receipts)
    assert closed == [attempt["id"]]
    with match.db.read() as conn:
        assert match.game.repo.game(conn, match.game_id)["phase"] == "reveal"
        assert len(match.game.repo.answers(conn, attempt["id"])) == 3
        assert all(
            answer["status"] == "submitted" and answer["points"] is not None
            for answer in match.game.repo.answers(conn, attempt["id"])
        )


def test_exact_host_expiry_is_committed_before_returning_heartbeat(match):
    match.preload()
    match.answering()
    clock = Clock(61_000)  # Last accepted heartbeat was the host's admission at 1,000.
    coordinator = match.coordinator
    coordinator.clock = clock
    coordinator.execute(
        match.room_id,
        match.token,
        lambda conn, player, now: coordinator.rooms.heartbeat(
            conn, match.room_id, player["id"], now
        ),
    )
    with match.db.read() as conn:
        game = match.game.repo.game(conn, match.game_id)
        assert game["status"] == "aborted" and game["end_reason"] == "host_timeout"
        assert match.game.repo.current(conn, match.game_id)["status"] == "void"
        assert match.rooms.room(conn, match.room_id, clock.now)["state"] == "lobby"
        assert (
            match.rooms.host_presence(conn, match.room_id, clock.now)["expires_at_ms"]
            == 121_000
        )
        assert all(
            player["final_score"] == 0
            for player in match.game.repo.roster(conn, match.game_id)
        )


@pytest.mark.parametrize(
    "kind", ["correct", "artist", "wrong", "unanswered", "missing"]
)
def test_reveal_song_result_uses_frozen_guess_not_total_points(match, kind):
    match.preload()
    match.answering()
    song, listeners = match.correct()
    chosen = {
        key: song.get(key)
        for key in ("song_key", "title", "artist", "artists", "artwork_url")
    }
    if kind in {"artist", "wrong"}:
        chosen = chosen | {"song_key": "other-track", "title": "Another Song"}
    if kind == "wrong":
        chosen["artists"] = [{"artist_key": "demo:unrelated", "name": "Other Artist"}]
    if kind == "unanswered":
        chosen = None
    if kind != "missing":
        match.submit(match.host, chosen, listeners)
    with match.db.read() as conn:
        public = game_view(
            match.game.repo, conn, match.game.repo.game(conn, match.game_id), match.host
        )
        assert "song_match" not in json.dumps(public)
    with match.db.transaction() as conn:
        conn.execute(
            "UPDATE songs SET title='Changed live title', artists_json=? WHERE room_id=?",
            (
                json.dumps([{"artist_key": "demo:changed", "name": "Changed"}]),
                match.room_id,
            ),
        )
    match.close()
    with match.db.read() as conn:
        game = match.game.repo.game(conn, match.game_id)
        revealed = game_view(match.game.repo, conn, game, match.host)["round"]["reveal"]
        answer = revealed["my_answer"]
        assert "answers" not in revealed
        assert answer["player_id"] == match.host
        assert answer["song_match"] == ("unanswered" if kind == "missing" else kind)
        assert answer["status"] == ("missing" if kind == "missing" else "submitted")
        if kind == "missing":
            assert answer["points"] == 0
        else:
            assert answer["points"] > 0
        # Another player who never submitted is independently unanswered.
        guest_reveal = game_view(match.game.repo, conn, game, match.ids[1])["round"][
            "reveal"
        ]
        guest_answer = guest_reveal["my_answer"]
        assert "answers" not in guest_reveal
        assert guest_answer["player_id"] == match.ids[1]
        assert guest_answer["status"] == "missing"
        assert guest_answer["song_match"] == "unanswered"
        assert guest_answer["song_guess"] is None
        assert guest_answer["who_player_ids"] is None
        assert guest_answer["points"] == 0
