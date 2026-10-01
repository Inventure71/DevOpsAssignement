"""Public game projections with guesses restricted to their authenticated owner."""

import json

from backend.game.scoring import classify_song_guess


GAME_FIELDS = (
    "id", "status", "phase", "state_version", "phase_ends_at_ms", "end_reason",
)
ROUND_FIELDS = (
    "id", "round_number", "attempt", "readiness_generation",
    "readiness_deadline_at_ms", "starts_at_ms", "deadline_at_ms",
)
SONG_DISPLAY_FIELDS = ("title", "artist", "artwork_url")


def game_view(repo, conn, game, player_id, host=False):
    if game is None:
        return None

    plan = json.loads(game["round_plan_json"])
    result = _game_overview(repo, conn, game, plan)
    current = repo.current(conn, game["id"])
    if current is None:
        return result

    round_view = _round_projection(repo, conn, game, current, plan, player_id, host)
    result["round"] = round_view
    ready = set(round_view["ready_player_ids"])
    excluded = set(round_view["excluded_player_ids"])
    result["missing_player_ids"] = [
        player["player_id"]
        for player in repo.roster(conn, game["id"])
        if player["player_id"] not in ready | excluded
    ]
    return result


def _game_overview(repo, conn, game, plan):
    settings = json.loads(game["settings_json"])
    skipped = _skipped_rounds(repo.attempts(conn, game["id"]), plan, game["end_reason"])
    return {
        **{key: game[key] for key in GAME_FIELDS},
        "requested_rounds": settings["round_count"],
        "playable_rounds": settings["round_count"] - len(skipped),
        "leaderboard": repo.leaderboard(conn, game["id"]),
        "missing_player_ids": [],
        "round": None,
        "preparation": {
            "checked": sum(len(slot.get("checks", {})) for slot in plan),
            "total": sum(len(slot["candidates"]) for slot in plan),
        },
    }


def _skipped_rounds(attempts, plan, end_reason):
    skipped = {slot["round_number"] for slot in plan if slot.get("skipped")}
    latest = {attempt["round_number"]: attempt for attempt in attempts}
    for slot in plan:
        attempt = latest.get(slot["round_number"])
        if attempt is None or attempt["status"] != "void":
            continue
        if attempt["void_reason"] == end_reason:
            continue
        has_replacement = any(
            index >= attempt["attempt"]
            and slot["checks"].get(candidate["song_key"]) is True
            for index, candidate in enumerate(slot["candidates"])
        )
        if not has_replacement:
            skipped.add(slot["round_number"])
    return skipped


def _round_projection(repo, conn, game, current, plan, player_id, host):
    answers = repo.answers(conn, current["id"])
    own = next((answer for answer in answers if answer["player_id"] == player_id), None)
    slot = next(slot for slot in plan if slot["round_number"] == current["round_number"])
    result = {
        **{key: current[key] for key in ROUND_FIELDS},
        "waveform": slot.get("waveforms", {}).get(current["song_key"]),
        "submitted_player_ids": [
            answer["player_id"] for answer in answers if answer["status"] == "submitted"
        ],
        "ready_player_ids": json.loads(current["ready_player_ids_json"]),
        "excluded_player_ids": json.loads(current["excluded_player_ids_json"]),
        "my_answer": _submission_receipt(own),
        "reveal": None,
    }
    if host and current["status"] in ("ready", "playing"):
        result["audio_candidate_id"] = current["song_key"]
    if current["status"] == "revealed":
        result["reveal"] = _reveal(game, current, own, player_id)
    return result


def _submission_receipt(answer):
    if answer is None or answer["status"] != "submitted":
        return None
    return {
        "song_guess": public_guess(answer),
        "who_player_ids": json.loads(answer["who_player_ids_json"]),
    }


def _reveal(game, current, own, player_id):
    song = next(
        song for song in json.loads(game["songs_snapshot_json"])
        if song["song_key"] == current["song_key"]
    )
    return {
        "song": _guess_display(song),
        "listener_ids": [listener["player_id"] for listener in song["listeners"]],
        "my_answer": _reveal_answer(own, song, player_id),
    }


def _reveal_answer(answer, song, player_id):
    if answer is None or answer["status"] == "missing":
        return {
            "player_id": player_id,
            "status": "missing",
            "points": 0,
            "song_guess": None,
            "song_match": "unanswered",
            "who_player_ids": None,
        }
    guess = json.loads(answer["song_guess_json"])
    return {
        "player_id": answer["player_id"],
        "status": answer["status"],
        "points": answer["points"],
        "song_guess": _guess_display(guess),
        "song_match": classify_song_guess(song, guess),
        "who_player_ids": json.loads(answer["who_player_ids_json"]),
    }


def audio_manifest(game):
    songs = {song["song_key"]: song for song in json.loads(game["songs_snapshot_json"])}
    plan = json.loads(game["round_plan_json"])
    return {
        "candidates": [
            {
                "candidate_id": candidate["song_key"],
                "preview_url": songs[candidate["song_key"]]["preview_url"],
            }
            for slot in plan for candidate in slot["candidates"]
        ],
    }


def public_guess(answer):
    return _guess_display(json.loads(answer["song_guess_json"]))


def _guess_display(guess):
    if guess is None:
        return None
    return {key: guess.get(key) for key in SONG_DISPLAY_FIELDS}
