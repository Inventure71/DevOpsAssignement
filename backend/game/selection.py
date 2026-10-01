"""Prepare a bounded full-game sequence, including distinct frozen reserves."""

from random import Random
from typing import Any, Mapping, Sequence


def skip_limit_exceeded(skipped: int, requested: int) -> bool:
    if requested <= 0 or not 0 <= skipped <= requested:
        raise ValueError("Invalid skipped/requested counts")
    return 10 * skipped > 3 * requested


def _key(song: Mapping[str, Any]) -> str:
    return str(song.get("song_key", song.get("id", "")))


def _familiarities(song: Mapping[str, Any]) -> dict[str, str]:
    return {str(item["player_id"]): item["familiarity"] for item in song.get("listeners", [])}


def prepare_plan(
    songs: Sequence[Mapping[str, Any]],
    roster: Sequence[str | Mapping[str, Any]],
    round_count: int,
    rng: Random,
    *,
    difficulty: str = "mixed",
    decoys: bool = True,
) -> list[dict[str, Any]]:
    """Build originals first, then reserves; all candidate song keys are unique.

    Selected or failed candidate clips cannot repeat.
    A slot with insufficient valid candidates remains empty so
    the application can apply the cumulative skip policy after preload checks.
    """
    if not 1 <= round_count <= 15 or difficulty not in {"easy", "mixed", "hard"}:
        raise ValueError("Invalid game settings")
    player_ids = [str(item.get("player_id", item.get("id"))) if isinstance(item, dict)
                  else str(item) for item in roster]
    if not player_ids or len(set(player_ids)) != len(player_ids):
        raise ValueError("A unique non-empty roster is required")
    by_key = {_key(song): song for song in songs}
    if "" in by_key or len(by_key) != len(songs):
        raise ValueError("Song keys must be unique and non-empty")
    familiarities = {key: _familiarities(song) for key, song in by_key.items()}
    personal = [key for key in by_key if familiarities[key]]
    decoy_pool = [key for key, song in by_key.items() if not familiarities[key]
                  and song.get("pool_kind", "decoy") == "decoy"]
    decoy_slots = set(rng.sample(range(2, round_count + 1), round_count // 5)) if decoys else set()
    available = set(by_key)
    rotation: list[str] = []
    rotation_index = 0

    def next_player() -> str:
        nonlocal rotation, rotation_index
        if rotation_index >= len(rotation):
            rotation = player_ids[:]
            rng.shuffle(rotation)
            rotation_index = 0
        player = rotation[rotation_index]
        rotation_index += 1
        return player

    def preferred_levels(prefer: str | None) -> list[str]:
        if prefer is None:
            prefer = (rng.choices(["easy", "medium", "hard"], [50, 35, 15])[0]
                      if difficulty == "mixed" else difficulty)
        return {"easy": ["easy", "medium", "hard"],
                "medium": ["medium", "easy", "hard"],
                "hard": ["hard", "medium", "easy"]}[prefer]

    def draw_normal(preferred_player: str, prefer: str | None = None) -> dict[str, Any] | None:
        levels = preferred_levels(prefer)
        players = [preferred_player, *(player for player in player_ids if player != preferred_player)]
        for player in players:
            for level in levels:
                candidates = [key for key in personal if key in available
                              and familiarities[key].get(player) == level]
                rng.shuffle(candidates)
                for key in candidates:
                    available.remove(key)
                    return {"song_key": key, "difficulty": level, "picked_player_id": player}
        return None

    def draw_decoy() -> dict[str, Any] | None:
        candidates = [key for key in decoy_pool if key in available]
        rng.shuffle(candidates)
        for key in candidates:
            available.remove(key)
            return {"song_key": key, "difficulty": "decoy", "picked_player_id": None}
        return None

    slots: list[dict[str, Any]] = []
    for number in range(1, round_count + 1):
        candidate = draw_decoy() if number in decoy_slots else None
        if candidate is None:
            candidate = draw_normal(next_player())
        slots.append({"round_number": number, "candidates": [candidate] if candidate else []})
    # Reserve allocation in passes keeps early slots from exhausting later ones.
    for _ in range(3):
        for slot in slots:
            if not slot["candidates"]:
                continue
            original = slot["candidates"][0]
            if original["difficulty"] == "decoy":
                candidate = draw_decoy() or draw_normal(player_ids[(slot["round_number"] - 1) % len(player_ids)])
            else:
                candidate = draw_normal(original["picked_player_id"], original["difficulty"])
            if candidate is not None:
                slot["candidates"].append(candidate)
    return slots
