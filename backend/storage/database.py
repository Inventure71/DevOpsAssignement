"""SQLite connections and transactional, versioned schema initialization."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from backend.core.paths import MIGRATIONS_DIR


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
            if version > 1:
                raise RuntimeError(f"Unsupported schema version: {version}")
            if version == 0:
                sql = (MIGRATIONS_DIR / "001_initial.sql").read_text()
                try:
                    # executescript commits any earlier transaction, so BEGIN belongs in it.
                    conn.executescript("BEGIN IMMEDIATE;\n" + sql + "\nPRAGMA user_version = 1;\nCOMMIT;")
                except BaseException:
                    if conn.in_transaction:
                        conn.rollback()
                    raise
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError("Existing database contains foreign-key violations")

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
