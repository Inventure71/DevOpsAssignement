# Temporary four-song catalog

`demo_catalog.json` contains exactly four fictional personal-pool songs,
`song-001` through `song-004`. Their bundled MP3s are original mathematical
synthesizer compositions retained from an earlier development fixture set.
They contain no borrowed recordings, samples, lyrics or provider data. Each
mono MP3 contains 30 seconds of audio at 32 kbit/s. One temporary SVG cover is
retained; the other artwork references are null. The reveal UI renders a music-icon fallback for missing or broken artwork.

The bulk catalog, extra assets and generator were removed from the Demo
checkpoint. App startup uses these four fixtures without ffmpeg or music
credentials. This seed supports lobby/data-flow checks and is intentionally too
small for a complete match under the existing distinct-song, decoy and
replacement rules; Start first requires at least ten songs per player. Tests
and the local load probe construct larger temporary metadata fixtures without
adding them to the runtime catalog.

The next catalog milestone replaces these temporary tracks with recognizable
real songs, including the requested Kanye selections. The redesigned frontend is uncommitted work on `feature/frontend`; real catalog
population remains a separate milestone.

Catalog entries use browser URLs under `/static/demo/`; their files live in
`catalog/assets/clips/` and `catalog/assets/covers/`. `backend/app.py` serves
`catalog/assets/` at `/static/demo`, independently of presentation code.
`backend/rooms/demo.py` validates and seeds the shared SQLite catalog. URLs remain
stable regardless of source-tree layout. To populate the next catalog, update
metadata and its referenced assets together; keep temporary test-only pools
under `tests/support/`.

The song-name typeahead can separately query Apple’s public metadata search. Those
results are answer choices selected by the player, not four issued round options.
They neither add songs to `demo_catalog.json` nor download audio or import personal
history. The runtime playback pool remains these four tracks until explicitly
populated. Public catalog search lives in `backend/catalog/`, outside Rooms’
hidden per-player familiarity and the checked playback plan.
