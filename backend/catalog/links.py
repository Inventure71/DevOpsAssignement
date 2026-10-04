"""Durable, scoped, positively verified public recording relationships."""

import hashlib
import json

from backend.catalog.identity import normalized_words, recording_title


# Bump when recording verification rules change.
MATCH_RULE_VERSION = 1


SCHEMA = """
CREATE TABLE IF NOT EXISTS verified_links (
 scope TEXT NOT NULL, purpose TEXT NOT NULL,
 source_key TEXT NOT NULL, source_fingerprint TEXT NOT NULL,
 target_key TEXT NOT NULL, target_fingerprint TEXT NOT NULL,
 source_json TEXT, target_json TEXT NOT NULL, verified_at REAL NOT NULL,
 PRIMARY KEY(scope,purpose,source_key,source_fingerprint,target_key,target_fingerprint)
);
"""


def fingerprint(song):
    """Persist recording identities until their verification rules change."""
    identity = [
        MATCH_RULE_VERSION,
        recording_title(song["title"]),
        normalized_words(song["artist"]),
        str(song.get("isrc") or "").upper(),
        sorted(
            (credit["artist_key"], normalized_words(credit["name"]))
            for credit in song["artists"]
        ),
    ]
    return hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def clean_song(song):
    # The store owns the common public allowlist; defer import to avoid a cycle.
    from backend.catalog.store import public_song

    clean = public_song(song)
    if clean is None:
        raise ValueError("Invalid verified catalog metadata")
    return clean


class VerifiedLinks:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def _save(conn, scope, purpose, source, target, now):
        if (
            not isinstance(scope, str)
            or not scope
            or purpose not in {"guess", "recording"}
        ):
            raise ValueError("Invalid verified catalog scope or purpose")
        source, target = clean_song(source), clean_song(target)
        source_identity, target_identity = fingerprint(source), fingerprint(target)
        stale = conn.execute(
            """SELECT rowid,target_fingerprint FROM verified_links
            WHERE scope=? AND purpose=? AND source_key=? AND source_fingerprint=?
            AND target_key=? AND target_fingerprint<>? ORDER BY rowid""",
            (
                scope,
                purpose,
                source["song_key"],
                source_identity,
                target["song_key"],
                target_identity,
            ),
        ).fetchall()
        current = conn.execute(
            """SELECT rowid FROM verified_links WHERE scope=? AND purpose=?
            AND source_key=? AND source_fingerprint=? AND target_key=? AND target_fingerprint=?""",
            (
                scope,
                purpose,
                source["song_key"],
                source_identity,
                target["song_key"],
                target_identity,
            ),
        ).fetchone()
        for row in stale:
            conn.execute(
                """DELETE FROM verified_links WHERE scope=? AND purpose=?
                AND source_key=? AND source_fingerprint=? AND target_key=? AND target_fingerprint=?""",
                (
                    scope,
                    purpose,
                    target["song_key"],
                    row["target_fingerprint"],
                    source["song_key"],
                    source_identity,
                ),
            )
            if current is None:
                # Keep the provider preference order when refreshing its snapshot.
                conn.execute(
                    "UPDATE verified_links SET target_fingerprint=? WHERE rowid=?",
                    (target_identity, row["rowid"]),
                )
                current = row
            else:
                conn.execute(
                    "DELETE FROM verified_links WHERE rowid=?", (row["rowid"],)
                )
        # Only the explicitly supplied forward source revision supersedes its
        # old target snapshot. Replacing in the reverse direction would discard
        # other independently verified revisions of the original source.
        for first, second in ((source, target), (target, source)):
            conn.execute(
                """INSERT INTO verified_links VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(scope,purpose,source_key,source_fingerprint,target_key,target_fingerprint)
                DO UPDATE SET source_json=excluded.source_json,target_json=excluded.target_json,
                verified_at=excluded.verified_at""",
                (
                    scope,
                    purpose,
                    first["song_key"],
                    fingerprint(first),
                    second["song_key"],
                    fingerprint(second),
                    json.dumps(first),
                    json.dumps(second),
                    now,
                ),
            )

    def save(self, scope, purpose, source_song, target_song, now):
        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._save(conn, scope, purpose, source_song, target_song, now)
            conn.commit()

    def find_many(self, scope, purpose, source_songs, *, conn=None):
        """Read a search page with one connection and one indexed SQL query."""
        if conn is None:
            with self.store.connect() as connection:
                return self.find_many(scope, purpose, source_songs, conn=connection)
        sources = {(song["song_key"], fingerprint(song)) for song in source_songs}
        if not sources:
            return {}
        predicates = " OR ".join(
            "(source_key=? AND source_fingerprint=?)" for _ in sources
        )
        parameters = [scope, purpose]
        for key, identity in sorted(sources):
            parameters.extend((key, identity))
        rows = conn.execute(
            f"""SELECT source_key,source_fingerprint,target_json FROM verified_links
            WHERE scope=? AND purpose=? AND ({predicates}) ORDER BY rowid""",
            parameters,
        )
        found = {}
        for row in rows:
            target = clean_song(json.loads(row["target_json"]))
            found.setdefault((row["source_key"], row["source_fingerprint"]), []).append(
                target
            )
        return found

    def find(self, scope, purpose, source_song):
        source = clean_song(source_song)
        return self.find_many(scope, purpose, [source]).get(
            (source["song_key"], fingerprint(source)), []
        )

    def reject(self, scope, purpose, source_song, target_key):
        """Remove only a known incorrect edge and its explicit reverse."""
        source = clean_song(source_song)
        identity = fingerprint(source)
        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """SELECT target_fingerprint FROM verified_links WHERE
                scope=? AND purpose=? AND source_key=? AND source_fingerprint=? AND target_key=?""",
                (scope, purpose, source["song_key"], identity, target_key),
            ).fetchall()
            conn.execute(
                """DELETE FROM verified_links WHERE scope=? AND purpose=?
                AND source_key=? AND source_fingerprint=? AND target_key=?""",
                (scope, purpose, source["song_key"], identity, target_key),
            )
            for row in rows:
                conn.execute(
                    """DELETE FROM verified_links WHERE scope=? AND purpose=? AND source_key=?
                    AND source_fingerprint=? AND target_key=? AND target_fingerprint=?""",
                    (
                        scope,
                        purpose,
                        target_key,
                        row["target_fingerprint"],
                        source["song_key"],
                        identity,
                    ),
                )
            conn.commit()
