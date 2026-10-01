"""Seeded catalog adapter; assignments remain private to the Rooms domain."""

import json
import secrets
import sqlite3
from pathlib import Path

from backend.core.paths import CATALOG_PATH
ASSIGNMENT_SIZE = 36


def seed_demo(conn: sqlite3.Connection, path: Path | None = None) -> None:
    """Replace the global catalog without changing room copies or frozen games."""
    entries = json.loads((path if path is not None else CATALOG_PATH).read_text())
    if not isinstance(entries, list):
        raise ValueError("Demo catalog must be an array")
    ids = set()
    validated = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid demo catalog entry")
        entry_id = entry.get("id")
        credits = entry.get("artists")
        if not isinstance(entry_id, str) or not entry_id or entry_id in ids:
            raise ValueError("Demo song IDs must be nonempty and unique")
        ids.add(entry_id)
        if entry.get("pool_kind") not in {"personal", "decoy"}:
            raise ValueError("Invalid demo pool kind")
        if not all(isinstance(entry.get(key), str) and entry[key] for key in ("title", "artist", "preview_url")):
            raise ValueError("Demo song metadata is incomplete")
        if not isinstance(credits, list) or not 1 <= len(credits) <= 20:
            raise ValueError("Demo artist credits are required")
        if not all(isinstance(credit, dict) and isinstance(credit.get("artist_key"), str)
                   and credit["artist_key"].startswith("demo:") and isinstance(credit.get("name"), str)
                   and credit["name"] for credit in credits):
            raise ValueError("Invalid demo artist credits")
        if not entry["preview_url"].startswith("/static/demo/"):
            raise ValueError("Demo audio must use a bundled asset URL")
        if entry.get("artwork_url") is not None and (
            not isinstance(entry["artwork_url"], str) or not entry["artwork_url"].startswith("/static/demo/")
        ):
            raise ValueError("Demo artwork must use a bundled asset URL")
        validated.append((entry_id, entry["pool_kind"], entry.get("isrc"), entry["title"],
                          entry["artist"], json.dumps(credits), entry["preview_url"], entry.get("artwork_url")))
    if not any(row[1] == "personal" for row in validated):
        raise ValueError("Demo catalog needs at least one personal song")
    # The file owns this lookup table; upsert alone retains removed fixtures.
    # Room song copies and frozen snapshots intentionally keep their own data.
    conn.execute("DELETE FROM demo_catalog")
    conn.executemany(
        """INSERT INTO demo_catalog (id, pool_kind, isrc, title, artist, artists_json, preview_url, artwork_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", validated)


def assign(conn: sqlite3.Connection, room_id: str, player_id: str) -> None:
    catalog = list(conn.execute("SELECT * FROM demo_catalog WHERE pool_kind = 'personal' ORDER BY id"))
    if not catalog:
        raise RuntimeError("Demo catalog is not initialized")
    rng = secrets.SystemRandom()
    for song in rng.sample(catalog, min(ASSIGNMENT_SIZE, len(catalog))):
        identity = "isrc:" + song["isrc"].strip().upper() if song["isrc"] else "demo:" + song["id"]
        conn.execute(
            """INSERT INTO songs (id, room_id, identity_key, isrc, title, artist, artists_json, preview_url, artwork_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(room_id, identity_key) DO NOTHING""",
            (secrets.token_hex(16), room_id, identity, song["isrc"], song["title"], song["artist"],
             song["artists_json"], song["preview_url"], song["artwork_url"]),
        )
        song_id = conn.execute("SELECT id FROM songs WHERE room_id=? AND identity_key=?", (room_id, identity)).fetchone()[0]
        conn.execute("INSERT INTO player_songs (room_id, player_id, song_id, familiarity) VALUES (?, ?, ?, ?)",
                     (room_id, player_id, song_id, rng.choice(("easy", "medium", "hard"))))


def decoys(conn: sqlite3.Connection) -> list[dict]:
    return [{"song_key": "demo-decoy:" + row["id"], "isrc": row["isrc"], "title": row["title"],
             "artist": row["artist"], "artists": json.loads(row["artists_json"]),
             "preview_url": row["preview_url"], "artwork_url": row["artwork_url"], "listeners": []}
            for row in conn.execute("SELECT * FROM demo_catalog WHERE pool_kind='decoy' ORDER BY id")]
