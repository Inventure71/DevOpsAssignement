"""Durable public metadata index, independent of rooms and listening evidence."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from backend.catalog.identity import normalized_words
from backend.catalog.links import SCHEMA as LINKS_SCHEMA
from backend.catalog.links import VerifiedLinks, fingerprint

SCHEMA_VERSION = 3


SCHEMA = """
CREATE TABLE IF NOT EXISTS catalog_songs (
 song_key TEXT PRIMARY KEY, title TEXT NOT NULL, artist TEXT NOT NULL,
 artists_json TEXT NOT NULL, isrc TEXT, artwork_url TEXT,
 title_normalized TEXT NOT NULL, artist_normalized TEXT NOT NULL,
 provenance TEXT NOT NULL, updated_at REAL NOT NULL, priority INTEGER
);
CREATE VIRTUAL TABLE IF NOT EXISTS catalog_fts USING fts5(
 title_normalized, artist_normalized, content='catalog_songs', content_rowid='rowid',
 tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS catalog_insert AFTER INSERT ON catalog_songs BEGIN
 INSERT INTO catalog_fts(rowid,title_normalized,artist_normalized)
 VALUES(new.rowid,new.title_normalized,new.artist_normalized); END;
CREATE TRIGGER IF NOT EXISTS catalog_delete AFTER DELETE ON catalog_songs BEGIN
 INSERT INTO catalog_fts(catalog_fts,rowid,title_normalized,artist_normalized)
 VALUES('delete',old.rowid,old.title_normalized,old.artist_normalized); END;
CREATE TRIGGER IF NOT EXISTS catalog_update AFTER UPDATE ON catalog_songs BEGIN
 INSERT INTO catalog_fts(catalog_fts,rowid,title_normalized,artist_normalized)
 VALUES('delete',old.rowid,old.title_normalized,old.artist_normalized);
 INSERT INTO catalog_fts(rowid,title_normalized,artist_normalized)
 VALUES(new.rowid,new.title_normalized,new.artist_normalized); END;
CREATE TABLE IF NOT EXISTS catalog_queries (
 scope TEXT NOT NULL, query TEXT NOT NULL, songs_json TEXT NOT NULL,
 expires_at REAL NOT NULL, PRIMARY KEY(scope,query)
);
CREATE TABLE IF NOT EXISTS preview_references (
 cache_key TEXT PRIMARY KEY, result_json TEXT NOT NULL, expires_at REAL NOT NULL
);

"""


def public_song(song):
    """Validate and allowlist catalog data before persistence or signing."""
    if not isinstance(song, dict):
        return None
    if not all(
        isinstance(song.get(key), str) and 0 < len(song[key]) <= 300
        for key in ("song_key", "title", "artist")
    ):
        return None
    artists = song.get("artists")
    if not isinstance(artists, list) or not artists or len(artists) > 20:
        return None
    credits = []
    for credit in artists:
        if not isinstance(credit, dict) or not all(
            isinstance(credit.get(key), str) and 0 < len(credit[key]) <= 300
            for key in ("artist_key", "name")
        ):
            return None
        clean = {key: credit[key] for key in ("artist_key", "name")}
        if isinstance(credit.get("aliases"), list):
            clean["aliases"] = [
                alias
                for alias in credit["aliases"][:20]
                if isinstance(alias, str) and 0 < len(alias) <= 300
            ]
        credits.append(clean)
    artwork = song.get("artwork_url")
    result = {key: song[key] for key in ("song_key", "title", "artist")}
    result.update(
        artists=credits,
        artwork_url=artwork
        if isinstance(artwork, str)
        and artwork.startswith("https://")
        and len(artwork) <= 2000
        else None,
    )
    isrc = song.get("isrc")
    if isinstance(isrc, str) and 0 < len(isrc) <= 32:
        result["isrc"] = isrc.upper()
    return result


def song_from_row(row):
    return {
        "song_key": row["song_key"],
        "title": row["title"],
        "artist": row["artist"],
        "artists": json.loads(row["artists_json"]),
        "isrc": row["isrc"],
        "artwork_url": row["artwork_url"],
    }


class CatalogStore:
    def __init__(self, path):
        self.path = Path(path)
        self.links = VerifiedLinks(self)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=5, isolation_level=None, uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
        finally:
            conn.close()

    def initialize(self, *, seed=False):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            shared = "rooms" in tables
            # PRAGMA user_version belongs to the application's storage migrations.
            # Catalog versions are independent even when both share one file.
            row = (
                conn.execute(
                    "SELECT version FROM component_schema_versions WHERE component='catalog'"
                ).fetchone()
                if "component_schema_versions" in tables
                else None
            )
            database_version = conn.execute("PRAGMA user_version").fetchone()[0]
            version = row["version"] if row else (0 if shared else database_version)
            if version not in (0, SCHEMA_VERSION) or (
                not shared and database_version not in (0, SCHEMA_VERSION)
            ):
                raise RuntimeError("Unsupported catalog schema version")
            if "catalog_songs" in tables:
                columns = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(catalog_songs)")
                }
                required = {
                    "song_key",
                    "title",
                    "artist",
                    "artists_json",
                    "isrc",
                    "artwork_url",
                    "title_normalized",
                    "artist_normalized",
                    "provenance",
                    "updated_at",
                    "priority",
                }
                if version != SCHEMA_VERSION or not required <= columns:
                    raise RuntimeError(
                        "Unsupported catalog schema; expected current fields"
                    )
            if "catalog_selections" in tables:
                raise RuntimeError(
                    "Unsupported catalog schema; retired selection table"
                )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS component_schema_versions "
                "(component TEXT PRIMARY KEY, version INTEGER NOT NULL)"
            )
            if conn.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal":
                raise RuntimeError("Catalog storage must support SQLite WAL mode")
            conn.executescript("BEGIN IMMEDIATE;\n" + SCHEMA + LINKS_SCHEMA)
            if "catalog_fts" not in tables:
                conn.execute("INSERT INTO catalog_fts(catalog_fts) VALUES('rebuild')")
            conn.execute(
                "INSERT OR REPLACE INTO component_schema_versions VALUES('catalog', ?)",
                (SCHEMA_VERSION,),
            )
            if not shared:
                conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            conn.commit()
            empty = (
                conn.execute("SELECT COUNT(*) FROM catalog_songs").fetchone()[0] == 0
            )
        if seed and empty:
            from backend.catalog.importer import import_canonical

            starter = Path(__file__).parent / "starter" / "musicbrainz-starter.csv"
            with starter.open(encoding="utf-8", newline="") as stream:
                import_canonical(stream, self)

    @staticmethod
    def _save(conn, songs, provenance, now):
        for song in songs:
            conn.execute(
                """INSERT INTO catalog_songs (song_key,title,artist,artists_json,isrc,artwork_url,title_normalized,
                artist_normalized,provenance,updated_at,priority) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(song_key) DO UPDATE SET title=excluded.title,artist=excluded.artist,
                artists_json=excluded.artists_json,isrc=excluded.isrc,artwork_url=excluded.artwork_url,
                title_normalized=excluded.title_normalized,artist_normalized=excluded.artist_normalized,
                provenance=excluded.provenance,updated_at=excluded.updated_at,priority=excluded.priority""",
                (
                    song["song_key"],
                    song["title"],
                    song["artist"],
                    json.dumps(song["artists"]),
                    song.get("isrc"),
                    song.get("artwork_url"),
                    normalized_words(song["title"]),
                    normalized_words(song["artist"]),
                    provenance,
                    now,
                    song.get("_catalog_priority"),
                ),
            )

    def save_songs(self, songs, provenance, now):
        clean = []
        for song in songs:
            entry = public_song(song)
            if entry is not None:
                priority = song.get("_catalog_priority")
                if (
                    isinstance(priority, int)
                    and not isinstance(priority, bool)
                    and 0 <= priority <= 2**63 - 1
                ):
                    entry["_catalog_priority"] = priority
                clean.append(entry)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._save(conn, clean, provenance, now)
            conn.commit()
        return len(clean)

    def save_query(self, scope, query, songs, now, ttl=86400):
        clean = [entry for song in songs[:20] if (entry := public_song(song))]
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._save(conn, clean, scope, now)
            conn.execute(
                "INSERT OR REPLACE INTO catalog_queries VALUES(?,?,?,?)",
                (scope, query, json.dumps(clean), now + (ttl if clean else 60)),
            )
            conn.execute(
                "DELETE FROM catalog_queries WHERE expires_at<?", (now - 86400,)
            )
            conn.commit()
        return clean

    def query(self, scope, query, now):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT songs_json FROM catalog_queries WHERE scope=? AND query=? AND expires_at>?",
                (scope, query, now),
            ).fetchone()
        return json.loads(row["songs_json"]) if row else None

    def search(self, query, limit=20, *, selectable=False, scope=None):
        terms = normalized_words(query).split()
        if not terms:
            return []
        # Only generated quoted tokens enter FTS syntax; bind the whole expression.
        expression = " AND ".join(
            '"' + term.replace('"', '""') + '"*' for term in terms
        )
        normalized = normalized_words(query)
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT s.* FROM catalog_fts
                JOIN catalog_songs s ON s.rowid=catalog_fts.rowid
                WHERE catalog_fts MATCH ? AND (?=0 OR s.song_key NOT LIKE 'musicbrainz:%')
                ORDER BY (s.title_normalized=?) DESC,
                (s.song_key NOT LIKE 'musicbrainz:%') DESC,
                COALESCE(s.priority,9223372036854775807),bm25(catalog_fts,4.0,1.0),s.title,s.artist,s.song_key LIMIT ?""",
                (expression, int(selectable), normalized, limit * 2),
            ).fetchall()
            metadata = [song_from_row(row) for row in rows]
            mappings = (
                self.links.find_many(scope, "guess", metadata, conn=conn)
                if scope
                else {}
            )
        songs, seen = [], set()
        for source in metadata:
            mapped = mappings.get((source["song_key"], fingerprint(source)), [])
            # Provider identities stay provider identities. Only bulk references
            # need replacement with a positively verified selectable target.
            song = (
                mapped[0]
                if source["song_key"].startswith("musicbrainz:") and mapped
                else source
            )
            if song["song_key"] not in seen:
                songs.append(song)
                seen.add(song["song_key"])
                if len(songs) >= limit:
                    break
        return songs

    def preview(self, key, now):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT result_json FROM preview_references WHERE cache_key=? AND expires_at>?",
                (key, now),
            ).fetchone()
        return (True, json.loads(row["result_json"])) if row else (False, None)

    def save_preview(self, key, result, now, ttl):
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO preview_references VALUES(?,?,?)",
                (key, json.dumps(result), now + ttl),
            )
            conn.execute(
                "DELETE FROM preview_references WHERE expires_at<?", (now - 86400,)
            )
