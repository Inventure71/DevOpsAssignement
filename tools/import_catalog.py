#!/usr/bin/env python3
"""Import an explicitly downloaded CSV into the public catalog tables in the application database."""

import argparse
import gzip
import json
import sys
from pathlib import Path

# Direct script execution also works without installing the project package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.catalog.importer import import_canonical
from backend.catalog.store import CatalogStore
from backend.storage.database import Database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "csv", type=Path, help="canonical_musicbrainz_data.csv or .csv.gz"
    )
    parser.add_argument(
        "--database",
        required=True,
        type=Path,
        help="Application SQLite path (DATA_DIR/whos_on_repeat.sqlite3)",
    )
    parser.add_argument(
        "--limit", type=int, default=10000, help="Maximum CSV rows; default 10000"
    )
    parser.add_argument(
        "--all", action="store_true", help="Explicitly import the whole file"
    )
    args = parser.parse_args()
    if args.limit <= 0:
        parser.error("--limit must be positive")
    Database(args.database).initialize()
    store = CatalogStore(args.database)
    store.initialize()
    opener = gzip.open if args.csv.suffix == ".gz" else open
    with opener(args.csv, "rt", encoding="utf-8-sig", newline="") as stream:
        result = import_canonical(stream, store, limit=None if args.all else args.limit)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
