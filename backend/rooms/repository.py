"""Persistence operations owned by Rooms; callers own transaction boundaries."""

import sqlite3


def room(conn: sqlite3.Connection, room_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    return dict(row) if row else None


def room_by_code(conn: sqlite3.Connection, code: str) -> dict | None:
    row = conn.execute("SELECT * FROM rooms WHERE code = ?", (code,)).fetchone()
    return dict(row) if row else None


def create_room(conn: sqlite3.Connection, room_id: str, code: str, mode: str, now_ms: int) -> None:
    conn.execute(
        "INSERT INTO rooms (id, code, mode, created_at_ms) VALUES (?, ?, ?, ?)",
        (room_id, code, mode, now_ms),
    )


def players(conn: sqlite3.Connection, room_id: str) -> list[dict]:
    return [dict(row) for row in conn.execute(
        "SELECT * FROM players WHERE room_id = ? ORDER BY joined_at_ms, id", (room_id,)
    )]


def player(conn: sqlite3.Connection, room_id: str, player_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM players WHERE room_id = ? AND id = ?", (room_id, player_id)).fetchone()
    return dict(row) if row else None


def player_by_token_hash(conn: sqlite3.Connection, room_id: str, token_hash: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM players WHERE room_id=? AND session_token_hash=?", (room_id, token_hash)
    ).fetchone()
    return dict(row) if row else None


def nickname_taken(
    conn: sqlite3.Connection, room_id: str, nickname_key: str, exclude_player_id: str | None = None
) -> bool:
    return conn.execute(
        "SELECT 1 FROM players WHERE room_id=? AND nickname_key=? AND (? IS NULL OR id!=?)",
        (room_id, nickname_key, exclude_player_id, exclude_player_id),
    ).fetchone() is not None


def music_account_taken(conn, room_id, account_hash):
    return conn.execute('SELECT 1 FROM players WHERE room_id=? AND music_account_hash=?',
                        (room_id, account_hash)).fetchone() is not None


def add_player(
    conn: sqlite3.Connection, *, room_id: str, player_id: str, nickname: str,
    nickname_key: str, character_id: str, music_status: str, token_hash: str,
    is_host: bool, now_ms: int,
    music_provider: str | None = None, music_account_hash: str | None = None,
) -> None:
    conn.execute(
        """INSERT INTO players (id, room_id, nickname, nickname_key, character_id, music_status,
           session_token_hash, is_host, joined_at_ms, last_seen_at_ms, music_provider, music_account_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (player_id, room_id, nickname, nickname_key, character_id, music_status,
         token_hash, int(is_host), now_ms, now_ms, music_provider, music_account_hash),
    )


def record_heartbeat(conn: sqlite3.Connection, room_id: str, player_id: str, now_ms: int) -> None:
    conn.execute(
        "UPDATE players SET last_seen_at_ms=? WHERE room_id=? AND id=?", (now_ms, room_id, player_id)
    )


def update_identity(
    conn: sqlite3.Connection, room_id: str, player_id: str,
    nickname: str, nickname_key: str, character_id: str,
) -> None:
    conn.execute(
        "UPDATE players SET nickname=?, nickname_key=?, character_id=? WHERE room_id=? AND id=?",
        (nickname, nickname_key, character_id, room_id, player_id),
    )


def remove_player(conn: sqlite3.Connection, room_id: str, player_id: str) -> None:
    conn.execute("DELETE FROM players WHERE room_id=? AND id=?", (room_id, player_id))


def prune_unreferenced_songs(conn: sqlite3.Connection, room_id: str) -> None:
    conn.execute(
        "DELETE FROM songs WHERE room_id=? AND pool_kind='personal' AND NOT EXISTS (SELECT 1 FROM player_songs WHERE song_id=songs.id)",
        (room_id,),
    )


def bump_revision(conn: sqlite3.Connection, room_id: str) -> None:
    conn.execute("UPDATE rooms SET revision = revision + 1 WHERE id = ?", (room_id,))


def song_counts(conn: sqlite3.Connection, room_id: str) -> dict[str, int]:
    return {row["player_id"]: row["count"] for row in conn.execute(
        """SELECT ps.player_id, COUNT(*) AS count FROM player_songs ps JOIN songs s ON s.id=ps.song_id
           WHERE ps.room_id=? AND s.preview_url IS NOT NULL GROUP BY ps.player_id""", (room_id,)
    )}


def song_memberships(conn: sqlite3.Connection, room_id: str) -> list[dict]:
    return [dict(row) for row in conn.execute(
        "SELECT song_id, player_id, familiarity FROM player_songs WHERE room_id=?", (room_id,)
    )]


def songs(conn: sqlite3.Connection, room_id: str) -> list[dict]:
    return [dict(row) for row in conn.execute(
        "SELECT * FROM songs WHERE room_id=? ORDER BY id", (room_id,)
    )]


def set_state(conn: sqlite3.Connection, room_id: str, state: str) -> None:
    conn.execute("UPDATE rooms SET state=?, revision=revision+1 WHERE id=?", (state, room_id))


def host(conn: sqlite3.Connection, room_id: str) -> dict | None:
    row = conn.execute(
        "SELECT id, last_seen_at_ms FROM players WHERE room_id=? AND is_host=1", (room_id,)
    ).fetchone()
    return dict(row) if row else None


def complete_room(conn: sqlite3.Connection, room_id: str, now_ms: int) -> None:
    conn.execute(
        "UPDATE rooms SET last_completed_at_ms=?, state='lobby', revision=revision+1 WHERE id=?",
        (now_ms, room_id),
    )


def expired_room_ids(conn: sqlite3.Connection, now_ms: int, retention_ms: int) -> list[str]:
    return [row[0] for row in conn.execute(
        "SELECT id FROM rooms WHERE COALESCE(last_completed_at_ms, created_at_ms) + ? <= ?",
        (retention_ms, now_ms),
    )]


def delete_room(conn: sqlite3.Connection, room_id: str) -> None:
    conn.execute("DELETE FROM rooms WHERE id=?", (room_id,))
