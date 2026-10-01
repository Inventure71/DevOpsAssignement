from fractions import Fraction

import pytest

from backend.game.scoring import classify_song_guess, half_up, score_answer


def facts(key="correct", listeners=("Anna", "Ben"), artists=("demo:one",)):
    return {"song_key": key, "listeners": [{"player_id": p, "familiarity": "medium"} for p in listeners],
            "artists": [{"artist_key": artist, "name": "Display"} for artist in artists]}


@pytest.mark.parametrize("seconds,option,who,expected", [
    (4, 0, ["Anna", "Ben"], 540),
    (5, 0, ["Anna", "Ben"], 536),
    (19, 0, ["Ben"], 230),
    (10, 0, ["Anna", "Carl"], 188),
    (8, 0, ["Anna", "Ben", "Carl", "Dana", "Eve", "Frank", "Gina"], 195),
    (2, 1, ["Anna", "Ben"], 150),
    (2, 2, ["Anna", "Ben"], 225),
    (5, 1, [], 0),
])
def test_normal_worked_examples(seconds, option, who, expected):
    song = facts()
    options = [song, facts("wrong", artists=("demo:other",)), facts("shared")]
    assert score_answer(song, options[option], who, seconds * 1000, 20_000, "medium") == expected


@pytest.mark.parametrize("seconds,option,who,expected", [
    (6, 0, [], 353), (10, 0, ["Anna"], 125),
    (3, 1, [], 100), (3, 2, [], 150),
])
def test_decoy_worked_examples(seconds, option, who, expected):
    song = facts(listeners=())
    options = [song, facts("wrong", artists=("demo:other",)), facts("shared")]
    assert score_answer(song, options[option], who, seconds * 1000, 20_000, "decoy") == expected


@pytest.mark.parametrize("elapsed,expected", [(-100, 150), (0, 150), (10_000, 125), (20_000, 100), (30_000, 100)])
def test_correct_song_speed_boundaries(elapsed, expected):
    song = facts(listeners=("Anna",))
    assert score_answer(song, song, [], elapsed, 20_000, "easy") == expected


def test_structured_multiple_artist_matches_award_once_without_perfect():
    song = facts(artists=("demo:a", "demo:b"))
    wrong = facts("wrong", artists=("demo:b", "demo:a", "demo:c"))
    assert score_answer(song, wrong, ["Anna", "Ben"], 0, 20_000, "hard") == 300


def test_artist_display_names_do_not_match_identities():
    song, wrong = facts(), facts("wrong", artists=("provider:other",))
    assert score_answer(song, wrong, [], 0, 20_000, "easy") == 0


def test_listener_only_answers_and_submitted_nobody():
    assert score_answer(facts(), None, ["Anna", "Ben"], 0, 20_000, "easy") == 100
    assert score_answer(facts(listeners=()), None, [], 0, 20_000, "decoy") == 100


def test_listener_fraction_and_wrong_picks_exactly_cancel():
    song = facts(listeners=("Anna", "Ben", "Carl"))
    assert score_answer(song, None, ["Anna"], 0, 20_000, "easy") == 33
    assert score_answer(song, None, ["Anna", "Wrong"], 0, 20_000, "easy") == 0
    assert score_answer(song, None, ["Anna", "Ben", "Carl"], 0, 20_000, "easy") == 100


def test_rounding_and_invalid_input():
    assert half_up(Fraction(375, 2)) == 188
    assert half_up(Fraction(5, 2)) == 3
    with pytest.raises(ValueError):
        score_answer(facts(), None, [], 0, 0, "easy")
    with pytest.raises(ValueError):
        score_answer(facts(), True, [], 0, 20_000, "easy")


def test_catalog_title_matches_normalized_unicode_and_same_structured_artist():
    song = facts(key='room:local') | {'title': 'Ｂｉｌｌｉｅ   Jean'}
    selected = facts(key='apple:track:42') | {'title': 'billie jean'}
    assert score_answer(song, selected, ['Anna', 'Ben'], 0, 20_000, 'easy') == 375
    selected['artists'] = [{'artist_key': 'apple:different', 'name': 'Display'}]
    assert score_answer(song, selected, [], 0, 20_000, 'easy') == 0


@pytest.mark.parametrize("chosen,expected", [
    (facts(), "correct"),
    (facts("other-track"), "artist"),
    (facts("other-track", artists=("demo:unrelated",)), "wrong"),
    (None, "unanswered"),
])
def test_song_classification_is_independent_of_listener_score(chosen, expected):
    song = facts()
    assert classify_song_guess(song, chosen) == expected
    # A wrong song and no song can each earn positive listener points.
    assert score_answer(song, chosen, ["Anna", "Ben"], 0, 20_000, "easy") > 0


def test_song_classification_matches_titles_only_with_structured_artist_overlap():
    song = facts("room:local") | {"title": "Ｂｉｌｌｉｅ   Jean"}
    selected = facts("apple:other-id") | {"title": "billie jean"}
    assert classify_song_guess(song, selected) == "correct"
    selected['artists'] = [{"artist_key": "apple:someone-else", "name": "Display"}]
    assert classify_song_guess(song, selected) == "wrong"
