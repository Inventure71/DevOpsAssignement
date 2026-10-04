"""SQLite connections and transactional, versioned schema initialization."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from backend.core.paths import MIGRATIONS_DIR

MIGRATIONS = (
    "001_initial.sql",
    "002_song_selections.sql",
    "003_blob_colors.sql",
    "004_music_admission.sql",
    "005_playtest.sql",
    "006_round_preparation.sql",
)


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.read() as conn:
            if conn.execute("SELECT json_valid('[]')").fetchone()[0] != 1:
                raise RuntimeError("SQLite JSON functions are required")
            if conn.execute("PRAGMA journal_mode = WAL").fetchone()[0] != "wal":
                raise RuntimeError("Database storage must support SQLite WAL mode")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > len(MIGRATIONS):
                raise RuntimeError(f"Unsupported schema version: {version}")
            for target, filename in enumerate(MIGRATIONS, start=1):
                if version < target:
                    self._migrate(conn, target, filename)
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError("Existing database contains foreign-key violations")

    def _migrate(self, conn: sqlite3.Connection, target: int, filename: str) -> None:
        sql = (MIGRATIONS_DIR / filename).read_text()
        try:
            # executescript commits earlier transactions; BEGIN belongs in the script.
            conn.executescript(
                "BEGIN IMMEDIATE;\n"
                + sql
                + f"\nPRAGMA user_version = {target};\nCOMMIT;"
            )
        except BaseException:
            if conn.in_transaction:
                conn.rollback()
            raise

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.read() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
