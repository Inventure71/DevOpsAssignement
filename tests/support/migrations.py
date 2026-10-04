"""Populate historical layouts using the original SQL, without faking versions."""

from backend.core.paths import MIGRATIONS_DIR
from backend.storage.database import MIGRATIONS


def legacy_copy(source, target, version):
    for filename in MIGRATIONS[:version]:
        target.executescript((MIGRATIONS_DIR / filename).read_text())
    tables = [
        row["name"]
        for row in source.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY rowid"
        )
    ]
    for table in tables:
        columns = [row[1] for row in target.execute("PRAGMA table_info(" + table + ")")]
        if not columns:
            continue
        names = ",".join(columns)
        for row in source.execute("SELECT " + names + " FROM " + table):
            target.execute(
                "INSERT INTO "
                + table
                + " ("
                + names
                + ") VALUES ("
                + ",".join("?" for _ in columns)
                + ")",
                tuple(row),
            )
    target.execute(f"PRAGMA user_version={version}")
