> Current storage update (2026-10-04): Catalog owns public tables inside
> `DATA_DIR/whos_on_repeat.sqlite3`, alongside logically separate Rooms/Game
> tables. Provider/search contracts are injected; no private Rooms SQL remains
> in public search. Pre-release separate-file imports and old catalog-schema
> upgrade paths have been retired. Instructions below use the current one-file path.

# Persistent catalog and preview preparation

The server owns one SQLite WAL file with independently owned tables.
Rooms/Game tables contain private room, listener and game facts. Catalog tables contain public
recording metadata, the FTS5 index, provider query coverage, recording-selection
mappings and short-lived preview references. Catalog queries never read private
song/listener tables, and no imported Spotify history is copied into suggestions.
Each storage operation uses a short connection/transaction; provider requests
run outside transactions and room command locks.

## Search and selection

The existing authenticated `GET /api/rooms/{room_id}/song-search?q=...` remains
compatible: rows contain `title`, `artist`, `artwork_url`, and a room-signed
`token`. Public provider rows are persisted and served locally when there is an
exact title match or fresh complete coverage of the same normalized query.
A group of partial matches does not establish complete query coverage.
Otherwise there is one bounded provider lookup, with
existing duplicate-request coalescing and a process-wide request budget.
Successful query coverage lasts 24 hours; empty results last 60 seconds. Indexed
metadata survives coverage expiry and server restart. Provider outages can serve
previously verified local rows. Shared demo fixtures retain their existing
selection behavior.

An additive `local=true` query parameter also searches MusicBrainz bulk metadata
without an external request. Unverified bulk rows have `resolve_required: true`
and their signed token contains an unresolved-reference marker. They cannot be
submitted as guesses. When the player chooses one, send:

```http
POST /api/rooms/{room_id}/song-selection
Content-Type: application/json

{"token":"the signed search-result token"}
```

The server authenticates the player and verifies token room and expiry. It
matches public provider metadata against the version-aware title and credited
artist. Multiple editions are equivalent only if their version-aware title and
complete structured artist-ID sets agree, consistent with existing guess
classification; different artist identities return an ambiguity error with bounded, freshly signed
public alternatives in `error.details.alternatives`. The
response is the normal song-result shape with a selectable token. The mapping
is persisted without a time limit under its provider/storefront scope, and later
searches can directly return that provider identity. Every equivalent,
unambiguous positive match saves a separate forward and reverse link. Mapping does not collapse live,
remix, instrumental or remaster versions. Scoring remains unchanged and never
performs provider I/O at the answer deadline.

FTS searches use bound, generated quoted prefix tokens. Unicode case and accent
normalization allow queries such as `deja vu` to match `Déjà Vu`; all query words
must match. Exact titles and verified provider identities rank first, followed
by the public canonical priority score. Ranking never uses player ownership or
listening frequency. Typo correction is intentionally not guessed by this
initial implementation; a genuine local miss still uses the provider fallback.
The explicit local-first endpoint returns bounded matches from the available
index. Its results are not an exhaustive search of the external provider catalog;
bulk ingestion improves coverage without claiming that every provider recording
is present locally.

## Warm the catalog

Fresh application databases receive 64 real MusicBrainz CC0 starter recordings
(about 14 KB). This is a small usable starter, not a representative mainstream
catalog. Its source, extraction/selection method, SHA-256 and license are in
`backend/catalog/starter/provenance.json`. Membership is curated from a bounded
public sample; search ranking still uses the public dataset priority. An
existing nonempty catalog is not reseeded.

### Download during setup

The repository contains the small starter and setup code, not the bulk catalog.
Run from the repository root with the same exported `DATA_DIR` as the application
(default `./data`; configuration files are not loaded automatically):

```bash
.venv/bin/python tools/setup_catalog.py --info
.venv/bin/python tools/setup_catalog.py --all
```

The setup tool pins the official source recorded in starter provenance. `--info`
fetches only small source headers/checksum metadata and reports paths and transfer
size without creating a database or downloading the archive. Actual setup
requires `zstd` on `PATH`, downloads resumably, verifies the published SHA-256,
and streams only `canonical_musicbrainz_data.csv` through the existing batched
importer. Other CSVs are not imported and no archive files are extracted.
Interrupted imports can be rerun; recording IDs are upserted. The default import
limit is 100,000 input rows; `--all` reads all eligible metadata records. Both
modes transfer the full archive, because its compression does not offer a
separate download for only our required columns.

For the pinned 2026-10-03 dump, a live HTTP header check reported an archive of
2,379,610,408 bytes (2.38 GB / 2.22 GiB). A bounded compressed prefix confirmed
that the metadata CSV member is 7,698,950,966 bytes (7.70 GB / 7.17 GiB).
Streaming avoids retaining that uncompressed CSV. The search database has
additional index and normalized-field overhead: an isolated approximately
100,000-row import occupied 47.8 MB. This is a sample measurement, not a measured
size for the complete dataset. Leave space for both the compressed archive and
the growing database/WAL; the tool does not make the whole dataset a small file.

Generated `whos_on_repeat.sqlite3` files and `catalog-downloads/` directories are
ignored even under a custom in-repository data directory. The importer retains
recording ID, title, artist identities/names, public priority and search fields;
it discards unused album/release and combined-lookup columns. This canonical
dataset supplies representative MusicBrainz metadata, not every recording in
every streaming provider. Unsupported composite artist credits are still
skipped, and missing recordings still use provider fallback.

Setup does not verify every metadata row against Apple. Verification remains
lazy on selection; successful mappings are shared by games and rooms using the
same catalog database/provider storefront and survive restarts without expiry.
Room-specific signed tokens are freshly issued rather than reused across rooms.

### Durable catalog verifications

Schema version 3 stores verified links independently from expiring query coverage
and media URLs. Each link records the provider/storefront, verification purpose,
source and target public identities, identity fingerprints and verification time.
Fingerprints cover version-aware title, ISRC and every credited artist ID/name.
Changed source identity requires new verification; elapsed time does not.
`MATCH_RULE_VERSION` must be bumped if the meaning of a positive match changes.
Guess equivalence and stricter playback recording verification have distinct
purposes, so a regional guess edition never becomes a strict audio match by
inference. Links never copy listening ranks, player IDs or source history into
catalog search.

MusicBrainz-to-Apple/iTunes guess matches are saved in both directions. The
Apple recording adapter also saves directly verified Spotify-to-Apple links and,
when matching ISRCs are present, Spotify-to-ISRC and ISRC-to-Apple links with their
explicit reverses. Distinct source IDs seen through a shared preview cache each
receive their verified links. No relation to an unimplemented provider or
unverified transitive relation is manufactured.

The current catalog schema is created directly. Pre-release selection-table
upgrades have been removed; current verified links remain durable across restarts.

Download the **canonical metadata CSV**, rather than MusicBrainz canonical
recording redirects. The latter intentionally combine some recording versions
and are inappropriate for this game's strict version matching. The source is
[MusicBrainz canonical metadata](https://musicbrainz.org/doc/Canonical_MusicBrainz_data),
licensed as [core CC0 data](https://musicbrainz.org/doc/About/Data_License).
No large download or scheduled ingestion runs automatically.

```bash
.venv/bin/python tools/import_catalog.py /path/canonical_musicbrainz_data.csv \
  --database /path/to/data/whos_on_repeat.sqlite3 --limit 100000
```

The tool streams plain or gzip-compressed UTF-8 CSV, commits at most 500 records
per batch, and defaults to reading only 10,000 rows. Explicit `--all` imports the
whole file. Extract `.tar.zst` archives separately using an available `zstd`/tar
utility; the application adds no decompression dependency or downloader.
The CSV must have `recording_mbid`, `recording_name`, `artist_credit_name` and
`artist_mbids` columns. Public `score` is optional and bounds-checked. Canonical
rows with composite artist credits are skipped: this flat export supplies IDs
but no separate names for each artist, so splitting display names would invent
identities. Missing songs remain searchable through the public provider.
Reimporting refreshes existing recording IDs and their FTS entries; removed
upstream records are not automatically deleted. Import counts report accepted
input rows, not unique recording count. Canonical IDs can change between dumps;
old rows remain metadata references and are still matched before selection.

## Preview references and bounded imports

Only metadata/reference mappings are cached; no audio is downloaded into the
server catalog. Positive preview references expire after at most 20 minutes,
bounded further by recognized numeric `exp`/`expires` URL parameters. Negative
matches last 60 seconds and provider errors 10 seconds. Reading a persisted URL
does not extend its original expiry. Cache identities include provider,
storefront, ISRC (or source track ID), version-aware title and complete normalized
artist credits. Safe HTTPS Apple media-host checks remain in force, as do strict
ISRC/version checks in the audio adapter. Concurrent identical requests share
one lookup. Cached media is attached to each original player's song object;
familiarity, observed history and ownership are never reused from another
player. Expired or rejected URLs trigger matching again; browser preparation
checks still detect delivery failures and use frozen reserve clips.

When a URL expires, an existing strict recording link fetches the current media
reference directly by the saved Apple ID, using the provider's
[catalog songs by ID endpoint](https://developer.apple.com/documentation/applemusicapi/get-multiple-catalog-songs-by-id).
This does not repeat ISRC/name matching searches. Returned metadata still passes
the recording safety checks. A valid identity with no working preview keeps its
link and briefly caches the media failure. A missing ID or temporary provider
failure also keeps its verified relationship; if all known IDs are missing, the
adapter can discover and save another directly verified edition. Only an ID
that returns a proven different recording rejects that specific edge and its
reverse, without deleting other provider/storefront links.

Spotify already interleaves easy, medium and hard candidates. Imports resolve
those candidates in ordered batches of four, stopping after 24 playable personal
tracks and 12 host decoys (the final batch may add up to three extra successes).
Low availability continues through the remaining candidates; the ten-playable
admission minimum and three-decoy minimum are unchanged. All 60 observed personal
songs are retained for private ownership evidence, even if preview resolution
was skipped. Successful imports return account identity, observed ownership,
playable songs and decoys. Admission failures retain useful candidate/playable
counts and provider errors. Game plans use available songs and retain the existing
reserves/skip policy.

With all candidates available, the first host performs 36 preview resolutions
instead of 90; another player importing the same recordings can reuse all
references. Separate cold/warm search and preview tests verify provider-call
counts rather than inferring speed from elapsed time. Real two-player shared-
account matches run for 5, 10 and 15 rounds, including a failed original clip
replaced by a reserve. This remains a single-process application; persistent
catalog storage alone does not make independent app workers safe for room
ordering or game coordination.
