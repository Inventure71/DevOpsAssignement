"""Persistence operations owned by Rooms; callers own transaction boundaries."""

import sqlite3


def room(conn: sqlite3.Connection, room_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    return dict(row) if row else None


def players(conn: sqlite3.Connection, room_id: str) -> list[dict]:
    return [dict(row) for row in conn.execute(
        "SELECT * FROM players WHERE room_id = ? ORDER BY joined_at_ms, id", (room_id,)
    )]


def player(conn: sqlite3.Connection, room_id: str, player_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM players WHERE room_id = ? AND id = ?", (room_id, player_id)).fetchone()
    return dict(row) if row else None


def bump_revision(conn: sqlite3.Connection, room_id: str) -> None:
    conn.execute("UPDATE rooms SET revision = revision + 1 WHERE id = ?", (room_id,))


def song_counts(conn: sqlite3.Connection, room_id: str) -> dict[str, int]:
    return {row["player_id"]: row["count"] for row in conn.execute(
        "SELECT player_id, COUNT(*) AS count FROM player_songs WHERE room_id = ? GROUP BY player_id", (room_id,)
    )}
