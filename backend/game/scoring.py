"""Exact, server-timed scoring over frozen song facts."""

import unicodedata
from fractions import Fraction
from typing import Any, Mapping, Sequence


def half_up(value: Fraction) -> int:
    """Round a non-negative exact value, with ties rounded upward."""
    if value < 0:
        raise ValueError("Scores must be non-negative")
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


def _key(song: Mapping[str, Any]) -> str:
    return str(song.get("song_key", song.get("id", "")))


def _artist_keys(song: Mapping[str, Any]) -> set[str]:
    return {str(artist["artist_key"]) for artist in song.get("artists", [])}


def _title(song: Mapping[str, Any]) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(song.get("title", ""))).casefold().split())


def _listeners(song: Mapping[str, Any]) -> set[str]:
    return {
        str(listener["player_id"] if isinstance(listener, dict) else listener)
        for listener in song.get("listeners", [])
    }


def classify_song_guess(song: Mapping[str, Any], chosen: Mapping[str, Any] | None) -> str:
    """Classify frozen song facts independently of listener points or timing."""
    if chosen is None:
        return "unanswered"
    if not isinstance(chosen, Mapping):
        raise ValueError("Invalid song selection")
    same_artist = bool(_artist_keys(song) & _artist_keys(chosen))
    if ((bool(_key(song)) and _key(chosen) == _key(song)) or
            (same_artist and bool(_title(song)) and _title(chosen) == _title(song))):
        return "correct"
    return "artist" if same_artist else "wrong"


def score_answer(
    song: Mapping[str, Any],
    chosen: Mapping[str, Any] | None,
    who_player_ids: Sequence[str],
    elapsed_ms: int,
    answer_ms: int,
    difficulty: str,
) -> int:
    """Score a submitted answer; missing submissions are handled by the service.

    Empty listener selections are explicit Nobody. Artist matching uses frozen
    structured identities, never title/artist display strings.
    """
    if answer_ms <= 0:
        raise ValueError("answer_ms must be positive")
    multipliers = {"easy": Fraction(1), "medium": Fraction(3, 2),
                   "hard": Fraction(2), "decoy": Fraction(1)}
    if difficulty not in multipliers:
        raise ValueError("Unknown difficulty")
    song_match = classify_song_guess(song, chosen)
    correct_song = song_match == "correct"
    if correct_song:
        elapsed = min(max(elapsed_ms, 0), answer_ms)
        song_points = 100 + half_up(Fraction(50 * (answer_ms - elapsed), answer_ms))
    elif song_match == "artist":
        song_points = 50
    else:
        song_points = 0

    listeners, selected = _listeners(song), set(who_player_ids)
    if not listeners:
        who_score = Fraction(int(not selected))
    else:
        correct, wrong = len(selected & listeners), len(selected - listeners)
        who_score = Fraction(max(0, correct - wrong), len(listeners))
    perfect = Fraction(3, 2) if correct_song and who_score == 1 else Fraction(1)
    return half_up((song_points + 100 * who_score) * multipliers[difficulty] * perfect)
