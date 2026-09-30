# Temporary four-song catalog

`catalog/demo_catalog.json` contains exactly four fictional personal-pool songs,
`song-001` through `song-004`. Their bundled MP3s are original mathematical
synthesizer compositions retained from an earlier development fixture set.
They contain no borrowed recordings, samples, lyrics or provider data. Each
mono MP3 contains 30 seconds of audio at 32 kbit/s. One temporary SVG cover is
retained; null artwork references exercise the placeholder path.

The bulk catalog, extra assets and generator have been removed from this
checkpoint. App startup uses these four fixtures without ffmpeg or music
credentials. This seed supports lobby/data-flow checks and is intentionally too
small for a complete match under the existing distinct-song, decoy and
replacement rules; Start first requires at least ten songs per player. Tests
and the local load probe construct larger temporary
metadata fixtures without adding them to the runtime catalog.

The next catalog milestone replaces these temporary tracks with recognizable
real songs, including the requested Kanye selections. The existing UI is also
a draft scheduled for redesign; neither milestone is claimed complete here.

Catalog entries contain browser URLs under `/static/demo/`; their files live in
`temporary_frontend/static/demo/`. `backend/rooms/demo.py` validates and seeds the shared
SQLite catalog. URLs remain stable regardless of the source-tree layout.
To populate the next catalog, update metadata and its referenced assets together;
keep temporary test-only pools under `tests/support/`.
