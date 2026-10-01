from copy import deepcopy
from random import Random

import pytest

from backend.game.selection import prepare_plan, skip_limit_exceeded


def pools(personal=96, decoys=24):
    songs = [{"song_key": f"personal-{index}", "listeners": [
        {"player_id": f"player-{index % 3}", "familiarity": ["easy", "medium", "hard"][(index // 3) % 3]}
    ]} for index in range(personal)]
    songs += [{"song_key": f"decoy-{index}", "listeners": []} for index in range(decoys)]
    return songs


ROSTER = ["player-0", "player-1", "player-2"]


def test_full_plan_is_frozen_deterministic_bounded_and_has_unique_candidates():
    songs = pools()
    untouched = deepcopy(songs)
    plan = prepare_plan(songs, ROSTER, 15, Random(19))
    assert plan == prepare_plan(songs, ROSTER, 15, Random(19))
    assert songs == untouched
    assert [slot["round_number"] for slot in plan] == list(range(1, 16))
    assert all(len(slot["candidates"]) == 4 for slot in plan)
    candidates = [candidate for slot in plan for candidate in slot["candidates"]]
    assert len({candidate["song_key"] for candidate in candidates}) == 60
    assert all("options" not in candidate for candidate in candidates)


@pytest.mark.parametrize("rounds,expected_decoys", [(5, 1), (10, 2), (15, 3)])
def test_exact_original_decoy_count_and_no_first_decoy(rounds, expected_decoys):
    plan = prepare_plan(pools(), ROSTER, rounds, Random(7))
    originals = [slot["candidates"][0] for slot in plan]
    assert originals[0]["difficulty"] != "decoy"
    assert sum(item["difficulty"] == "decoy" for item in originals) == expected_decoys


def test_player_rotation_is_balanced_and_reserves_preserve_honest_familiarity():
    songs = pools()
    by_key = {song["song_key"]: song for song in songs}
    plan = prepare_plan(songs, ROSTER, 10, Random(31))
    originals = [slot["candidates"][0] for slot in plan if slot["candidates"][0]["difficulty"] != "decoy"]
    counts = [sum(candidate["picked_player_id"] == player for candidate in originals) for player in ROSTER]
    assert max(counts) - min(counts) <= 1
    for slot in plan:
        for candidate in slot["candidates"]:
            listeners = by_key[candidate["song_key"]]["listeners"]
            if candidate["difficulty"] == "decoy":
                assert not listeners
                assert candidate["picked_player_id"] is None
            else:
                assert {"player_id": candidate["picked_player_id"], "familiarity": candidate["difficulty"]} in listeners


def test_decoy_pool_unavailable_falls_back_to_personal_song():
    plan = prepare_plan(pools(decoys=0), ROSTER, 10, Random(17))
    assert all(slot["candidates"] for slot in plan)
    assert all(candidate["difficulty"] != "decoy" for slot in plan for candidate in slot["candidates"])


def test_difficulty_falls_back_and_skips_player_with_no_remaining_songs():
    songs = pools(personal=30, decoys=0)
    for song in songs:
        song["listeners"] = [{"player_id": "player-1", "familiarity": "medium"}]
    plan = prepare_plan(songs, ROSTER, 5, Random(2), difficulty="hard", decoys=False)
    assert all(candidate["difficulty"] == "medium" and candidate["picked_player_id"] == "player-1"
               for slot in plan for candidate in slot["candidates"])


def test_exhausted_pool_does_not_loop_or_duplicate_candidates():
    plan = prepare_plan(pools(personal=4, decoys=0), ROSTER, 15, Random(3), decoys=False)
    candidates = [candidate for slot in plan for candidate in slot["candidates"]]
    assert len(candidates) == 4
    assert len({candidate["song_key"] for candidate in candidates}) == 4
    assert any(not slot["candidates"] for slot in plan)


@pytest.mark.parametrize("requested,allowed,exceeded", [(5, 1, 2), (10, 3, 4), (15, 4, 5)])
def test_strict_thirty_percent_skip_boundary(requested, allowed, exceeded):
    assert not skip_limit_exceeded(allowed, requested)
    assert skip_limit_exceeded(exceeded, requested)


def test_small_pool_can_play_without_requiring_distractors():
    plan = prepare_plan(pools(personal=2, decoys=0), ROSTER, 5, Random(1))
    assert sum(len(slot["candidates"]) for slot in plan) == 2
