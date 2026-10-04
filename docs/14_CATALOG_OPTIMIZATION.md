# Persistent catalog and preview preparation

Catalog owns public metadata, search coverage, verified identities and expiring media references in `DATA_DIR/whos_on_repeat.sqlite3`. Rooms/Game own private listening and match data in separate tables. Provider requests run outside SQLite transactions and room command locks. Table ownership is in the [data model](06_DATA_MODEL.md); HTTP selection and scoring contracts are in [API/runtime](07_API_AND_RUNTIME.md#public-song-search).

## Search and selection

FTS5 search normalizes case/accents, matches all query words and ranks exact titles and verified provider identities before public canonical priority. Public search is independent of player ownership.

Fresh complete query coverage or an indexed exact title can satisfy a search locally. Partial prefix hits alone cannot establish coverage; otherwise a bounded provider query runs. Successful query coverage lasts 24 hours, empty results 60 seconds. Indexed metadata survives expiry and restart, and verified local results can serve during provider outages.

`local=true` also searches bulk MusicBrainz metadata. Unverified rows carry `resolve_required: true`; selecting one resolves its room-signed reference through `POST /api/rooms/{room_id}/song-selection`. Matching uses version-aware titles and complete artist identities. Ambiguous matches return signed alternatives. Scoring uses its own more forgiving guess-title normalization; strict catalog/audio verification remains separate.

## Warm the catalog

Fresh empty catalogs receive the [64-recording CC0 starter](../backend/catalog/starter/provenance.json). For broader coverage, run from the repository root with the application's exported `DATA_DIR`:

```bash
.venv/bin/python tools/setup_catalog.py --info
.venv/bin/python tools/setup_catalog.py --all
```

`--info` reports the pinned official archive's size, checksum and destination. Setup requires `zstd` on `PATH`, resumes downloads, verifies SHA-256 and streams the canonical metadata CSV directly into SQLite. It defaults to 100,000 input rows; `--all` imports every eligible row. Both download the complete compressed archive. Reruns upsert recording IDs in batches of at most 500.

The 2026-10-03 source check measured a 2.38 GB compressed archive; an isolated approximately 100,000-row index occupied 47.8 MB. Allow space for the archive, database and WAL. The source is [MusicBrainz canonical metadata](https://musicbrainz.org/doc/Canonical_MusicBrainz_data), licensed as [core CC0 data](https://musicbrainz.org/doc/About/Data_License).

For an existing plain/gzip CSV:

```bash
.venv/bin/python tools/import_catalog.py /path/canonical_musicbrainz_data.csv \
  --database /path/to/data/whos_on_repeat.sqlite3 --limit 100000
```

The standalone importer defaults to 10,000 rows and also accepts `--all`. Required columns are `recording_mbid`, `recording_name`, `artist_credit_name` and `artist_mbids`; `score` is optional. Composite artist credits are skipped because the flat export lacks individual artist names. Reimport refreshes metadata and FTS entries; it retains records absent from a later dump. Verification against Apple happens lazily on selection.

## Durable catalog verifications

Verified links survive time and restart independently of media expiry. They are scoped by provider/storefront and purpose, with source/target identity fingerprints covering title/version, ISRC and every credited artist. Each positive match records explicit forward and reverse links; a changed identity or matching-rule version requires verification again. Guess equivalence and strict playback matching have separate purposes. Bump `MATCH_RULE_VERSION` when positive-match semantics change.

Expired previews refresh through the saved Apple recording ID. Missing media or temporary provider errors retain the verified identity; a proven wrong recording rejects only that edge and its reverse. See [Apple's lookup-by-ID endpoint](https://developer.apple.com/documentation/applemusicapi/get-multiple-catalog-songs-by-id).

## Preview references and bounded imports

Positive media references expire after at most 20 minutes, further bounded by recognized URL expiry parameters. Missing matches last 60 seconds; provider errors last 10 seconds. Reads preserve the original expiry. Cache keys include provider/storefront, ISRC or track ID, title/version and complete artist credits. Identical concurrent requests share a lookup. Each caller receives media attached to its own listening facts.

Spotify imports resolve ordered batches of four, targeting 24 playable personal songs and 12 host decoys; a final batch can add three more successes. Low availability continues through the remaining candidates. Admission requires ten playable personal songs and three host decoys. All observed personal candidates, up to 60, retain private ownership even when media resolution is skipped or fails. Demo uses the same importer with local source/resolver limits.

The catalog stores metadata and references; the browser prepares decoded audio and frozen reserves. Full-round preparation and skip policy are defined in [game rules](03_GAME_RULES.md#6-preparing-the-full-game-sequence). Verification is documented in [testing strategy](18_TESTING_STRATEGY.md).
