"""Explicit metadata-only pools for full-match tests and the local load probe.

These entries are isolated from the four-song runtime catalog. Reusing its four
audio references keeps rule and persistence tests independent of media volume;
this fixture does not claim to provide distinct recordings or test playback.
"""

import json
from pathlib import Path


def write_large_catalog(path: Path) -> Path:
    entries = []
    for number in range(1, 121):
        artist_number = (number - 1) % 12 + 1
        clip_number = (number - 1) % 4 + 1
        artist_name = f"Test Artist {artist_number}"
        entries.append({
            "id": f"test-song-{number:03d}",
            "pool_kind": "personal" if number <= 96 else "decoy",
            "isrc": None,
            "title": f"Test Song {number:03d}",
            "artist": artist_name,
            "artists": [{"artist_key": f"demo:test-artist-{artist_number}", "name": artist_name}],
            "preview_url": f"/static/demo/clips/song-{clip_number:03d}.mp3",
            "artwork_url": "/static/demo/covers/act-01.svg" if number % 2 == 0 else None,
        })
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path
