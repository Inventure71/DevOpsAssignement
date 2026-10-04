"""Seeded catalog adapter; assignments remain private to the Rooms domain."""

import json
import secrets
import sqlite3
from pathlib import Path
from urllib.parse import unquote

from backend.catalog.identity import normalized_words, recording_title

ASSIGNMENT_SIZE = 36


def seed_demo(conn: sqlite3.Connection, path: Path) -> None:
    """Replace the global catalog without changing room copies or frozen games."""
    entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError("Demo catalog must be an array")
    ids = set()
    recordings = {}
    validated = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid demo catalog entry")
        entry_id = entry.get("id")
        credits = entry.get("artists")
        if not isinstance(entry_id, str) or not entry_id or entry_id in ids:
            raise ValueError("Demo song IDs must be nonempty and unique")
        ids.add(entry_id)
        isrc = entry.get("isrc")
        if isrc is not None and not isinstance(isrc, str):
            raise ValueError("Demo ISRC must be text or null")
        isrc = (isrc.strip().upper() or None) if isrc is not None else None
        if entry.get("pool_kind") not in {"personal", "decoy"}:
            raise ValueError("Invalid demo pool kind")
        if not all(
            isinstance(entry.get(key), str) and entry[key]
            for key in ("title", "artist", "preview_url")
        ):
            raise ValueError("Demo song metadata is incomplete")
        if not isinstance(credits, list) or not 1 <= len(credits) <= 20:
            raise ValueError("Demo artist credits are required")
        if not all(
            isinstance(credit, dict)
            and isinstance(credit.get("artist_key"), str)
            and credit["artist_key"].startswith("demo:")
            and isinstance(credit.get("name"), str)
            and credit["name"]
            for credit in credits
        ):
            raise ValueError("Invalid demo artist credits")
        if not entry["preview_url"].startswith("/static/demo/local/"):
            raise ValueError("Demo audio must use the selected local pack URL")
        if entry.get("artwork_url") is not None and (
            not isinstance(entry["artwork_url"], str)
            or not entry["artwork_url"].startswith("/static/demo/local/")
        ):
            raise ValueError("Demo artwork must use the selected local pack URL")
        if isrc is not None:
            # A pack is authoritative: conflicting identities must be corrected
            # before seeding, rather than silently changing listener ownership.
            metadata = (
                recording_title(entry["title"]),
                normalized_words(entry["artist"]),
                frozenset(
                    (credit["artist_key"], normalized_words(credit["name"]))
                    for credit in credits
                ),
            )
            if isrc in recordings:
                pool_kind, existing_metadata = recordings[isrc]
                if pool_kind != entry["pool_kind"]:
                    raise ValueError("Demo ISRC cannot be both personal and decoy")
                if metadata != existing_metadata:
                    raise ValueError("Conflicting demo metadata for the same ISRC")
                # Pack order chooses the preferred display metadata and media
                # when several rows describe the same verified recording.
                continue
            recordings[isrc] = (entry["pool_kind"], metadata)
        validated.append(
            (
                entry_id,
                entry["pool_kind"],
                isrc,
                entry["title"],
                entry["artist"],
                json.dumps(credits),
                entry["preview_url"],
                entry.get("artwork_url"),
            )
        )
    if not any(row[1] == "personal" for row in validated):
        raise ValueError("Demo catalog needs at least one personal song")
    # The file owns this lookup table; upsert alone retains removed fixtures.
    # Room song copies and frozen snapshots intentionally keep their own data.
    conn.execute("DELETE FROM demo_catalog")
    conn.executemany(
        """INSERT INTO demo_catalog (id, pool_kind, isrc, title, artist, artists_json, preview_url, artwork_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        validated,
    )


def validate_pack_assets(pack: Path) -> int:
    """Reject missing or unsafe media before startup changes application data."""
    assets = (pack / "assets").resolve()
    prefix = "/static/demo/local/"
    try:
        catalog = pack / "demo_catalog.json"
        with sqlite3.connect(":memory:") as connection:
            connection.execute(
                "CREATE TABLE demo_catalog (id TEXT, pool_kind TEXT, isrc TEXT, "
                "title TEXT, artist TEXT, artists_json TEXT, preview_url TEXT, "
                "artwork_url TEXT)"
            )
            seed_demo(connection, catalog)
            counts = dict(
                connection.execute(
                    "SELECT pool_kind,COUNT(*) FROM demo_catalog GROUP BY pool_kind"
                )
            )
            if counts.get("personal", 0) < 15 or counts.get("decoy", 0) < 1:
                raise ValueError(
                    "Demo needs at least 15 personal clips and one Nobody clip"
                )
        entries = json.loads(catalog.read_text(encoding="utf-8"))
        if not isinstance(entries, list) or not entries:
            raise ValueError("Demo catalog must be a nonempty array")
        for entry in entries:
            for key in ("preview_url", "artwork_url"):
                value = entry.get(key)
                if value is None and key == "artwork_url":
                    continue
                if not isinstance(value, str) or not value.startswith(prefix):
                    raise ValueError("Asset URL does not belong to this Demo pack")
                target = (assets / unquote(value[len(prefix) :])).resolve()
                if (
                    not target.is_relative_to(assets)
                    or not target.is_file()
                    or target.stat().st_size == 0
                ):
                    raise ValueError("Missing or invalid Demo asset")
        if not (assets / "credits.html").is_file():
            raise ValueError("Demo music credits are missing")
    except (OSError, ValueError, TypeError, AttributeError, sqlite3.Error) as error:
        raise ValueError(
            f"Demo music pack at {pack} is missing or incomplete: {error}. "
            "Run tools/setup_demo_pack.py before starting the server."
        ) from error
    return len(entries)


def preview_sample(conn: sqlite3.Connection) -> dict:
    """Expose one shared catalog sample without player listening evidence."""
    row = conn.execute(
        "SELECT title,artist,preview_url,artwork_url FROM demo_catalog "
        "WHERE pool_kind='personal' ORDER BY id LIMIT 1"
    ).fetchone()
    if row is None:
        raise RuntimeError("Demo catalog is not initialized")
    return dict(row)


def assign(conn: sqlite3.Connection, room_id: str, player_id: str) -> None:
    catalog = list(
        conn.execute(
            "SELECT * FROM demo_catalog WHERE pool_kind = 'personal' ORDER BY id"
        )
    )
    if not catalog:
        raise RuntimeError("Demo catalog is not initialized")
    rng = secrets.SystemRandom()
    count = min(ASSIGNMENT_SIZE, len(catalog))
    for song in rng.sample(catalog, count):
        identity = (
            "isrc:" + song["isrc"].strip().upper()
            if song["isrc"]
            else "demo:" + song["id"]
        )
        conn.execute(
            """INSERT INTO songs (id, room_id, identity_key, isrc, title, artist, artists_json, preview_url, artwork_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(room_id, identity_key) DO NOTHING""",
            (
                secrets.token_hex(16),
                room_id,
                identity,
                song["isrc"],
                song["title"],
                song["artist"],
                song["artists_json"],
                song["preview_url"],
                song["artwork_url"],
            ),
        )
        song_id = conn.execute(
            "SELECT id FROM songs WHERE room_id=? AND identity_key=?",
            (room_id, identity),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO player_songs (room_id, player_id, song_id, familiarity) VALUES (?, ?, ?, ?)",
            (room_id, player_id, song_id, rng.choice(("easy", "medium", "hard"))),
        )


def decoys(conn: sqlite3.Connection) -> list[dict]:
    return [
        {
            "song_key": "demo-decoy:" + row["id"],
            "isrc": row["isrc"],
            "title": row["title"],
            "artist": row["artist"],
            "artists": json.loads(row["artists_json"]),
            "preview_url": row["preview_url"],
            "artwork_url": row["artwork_url"],
            "listeners": [],
        }
        for row in conn.execute(
            "SELECT * FROM demo_catalog WHERE pool_kind='decoy' ORDER BY id"
        )
    ]


def search_fixtures(conn):
    """Export only shared fixture answer metadata to the application."""
    return [
        {
            "song_key": "demo:" + row["id"],
            "title": row["title"],
            "artist": row["artist"],
            "artists": json.loads(row["artists_json"]),
            "artwork_url": row["artwork_url"],
        }
        for row in conn.execute(
            "SELECT id,title,artist,artists_json,artwork_url FROM demo_catalog ORDER BY title,id"
        )
    ]
