"""Streaming MusicBrainz CC0 metadata ingestion."""

import csv
import json
import time
from itertools import islice
from uuid import UUID


REQUIRED = {"recording_mbid", "recording_name", "artist_credit_name", "artist_mbids"}


def _mbids(value):
    # Canonical PostgreSQL array exports and JSON arrays are both supported.
    value = value.strip()
    if value.startswith("["):
        identifiers = json.loads(value)
    else:
        identifiers = [item.strip(' "') for item in value.strip("{}").split(",")]
    return [str(UUID(identifier)) for identifier in identifiers]


def canonical_song(row):
    if not all(isinstance(row.get(key), str) for key in REQUIRED):
        return None
    try:
        recording = str(UUID(row["recording_mbid"]))
        artist_ids = _mbids(row["artist_mbids"])
        title, artist = row["recording_name"].strip(), row["artist_credit_name"].strip()
        if (
            not title
            or not artist
            or len(title) > 300
            or len(artist) > 300
            or len(artist_ids) != 1
        ):
            # The flat export lacks separate names for composite artist credits;
            # don't invent individual identities by splitting '&' or commas.
            return None
        try:
            score = row.get("score")
            priority = int(score) if isinstance(score, str) and score.strip() else None
        except ValueError:
            priority = None
        if priority is not None and not 0 <= priority <= 2**63 - 1:
            priority = None
        return {
            "_catalog_priority": priority,
            "song_key": "musicbrainz:recording:" + recording,
            "title": title,
            "artist": artist,
            "artists": [
                {"artist_key": "musicbrainz:artist:" + artist_ids[0], "name": artist}
            ],
            "artwork_url": None,
        }
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None


def import_canonical(stream, store, limit=None, batch_size=500, clock=time.time):
    """Bound memory and write-lock duration; limit counts input rows, not matches."""
    reader = csv.DictReader(stream)
    if not REQUIRED.issubset(reader.fieldnames or []):
        raise ValueError(
            "Expected MusicBrainz canonical metadata CSV columns: "
            + ", ".join(sorted(REQUIRED))
        )
    rows = reader if limit is None else islice(reader, limit)
    batch, read, imported, skipped = [], 0, 0, 0
    for row in rows:
        read += 1
        song = canonical_song(row)
        if song is None:
            skipped += 1
            continue
        batch.append(song)
        if len(batch) >= batch_size:
            imported += store.save_songs(batch, "musicbrainz:canonical:CC0", clock())
            batch.clear()
    if batch:
        imported += store.save_songs(batch, "musicbrainz:canonical:CC0", clock())
    return {"rows_read": read, "imported": imported, "skipped": skipped}
