# Demo music pack

Demo uses one pinned 100-song pack: 80 personal-pool recordings and 20 independent
Nobody songs. Each player receives 36 randomly selected personal songs with
simulated familiarity. Decoys are never assigned to a player. Normal mode instead
uses each player's Spotify observations and Apple preview resolution.

`demo_catalog.json` is the canonical public metadata for these 100 recordings.
`demo_pack_source.json` pins the downloadable archive and its inventory. Audio,
ZIPs, provenance and installation files stay under ignored `catalog/local/`;
there are no bundled synthetic or festival packs.

## Install the Drive pack

The [100-song ZIP](https://drive.google.com/file/d/1nmv-F4OettnXqMj5JZNp_WzO1XZSCpOp/view)
is 102,785,177 bytes (98.02 MiB). The committed source descriptor pins its Drive
file ID, byte count, ZIP SHA-256 and inner manifest SHA-256. Replacing the remote
file does not silently change the music: different bytes fail verification.

Both launchers install the default pack when it is missing, before starting the
server. The teacher needs no Google login, Apple/Spotify key, FFmpeg or private
acquisition script. Internet is needed once for dependencies and this download;
subsequent launches and games use local files offline. To prepare music separately:

```bash
python3 tools/setup_demo_pack.py
# Offline, read-only integrity check of the installed pinned pack:
python3 tools/setup_demo_pack.py --check
# Install from a previously downloaded ZIP, without contacting Drive:
python3 tools/setup_demo_pack.py --archive /path/to/whos-on-repeat-demo-100.zip
# Windows uses py -3 instead of python3.
```

The installer handles Drive's large-file confirmation page, verifies the archive
before extraction, rejects unsafe paths/links and validates every file against
the pinned inventory. A complete installation is published atomically under
`catalog/local/packs/whos-on-repeat-demo-100-24455f95611e/`. The reusable download
is cached under `catalog/local/downloads/`. Both locations are Git-ignored.
Existing installations are verified offline; `--check` installs nothing and
fails if the pack is missing or corrupt. Setup does not change application data.

A missing or invalid pack stops launch with an actionable error. After an
interrupted installation, remove `catalog/local/.drive-install.lock` only after
its installer has stopped, then retry. The installer never changes Drive sharing
settings or uploads files. An explicit `--demo-pack <directory>` selects a
complete local pack for either launcher; invalid explicit selections also fail.
Application startup validates installed assets but never downloads Demo music.

## Runtime ownership and validation

`backend/rooms/demo.py` validates and replaces the shared `demo_catalog` lookup
at startup. Existing room assignments and frozen games keep their own song facts;
reseeding does not rewrite their history. The precommit cleanup removed obsolete
local rooms/games before deleting their old media. Public provider metadata,
verified links and caches were retained.

Equivalent rows with the same normalized ISRC count as one recording before
player libraries are sampled; the first row supplies the preferred metadata and
media. Missing or blank ISRCs remain distinct by Demo ID. Conflicting title,
artist identity or personal/decoy placement rejects a pack before reseeding.
Every referenced asset must stay inside the selected pack and be present and
nonempty. Media URLs begin with `/static/demo/local/`; `/music-credits` serves
that pack's credits. Missing artwork uses the UI's music-icon fallback.

Demo search uses the complete 100-song metadata lookup rather than a player's
36-song assignment or the separate public MusicBrainz index. It never contacts
external providers. `/api/demo/preview` gives the UI lab one active catalog sample;
the lab uses its actual title, artist and audio URL, with metadata-only alternate
guesses for display scenarios.

HTTP/SQLite integration tests exercise ten-/fifteen-round game loops, signed local
search, readiness, answers, scoring and history. The Drive installer verifies the
real archive and every extracted checksum. Metadata-only test fixtures remain
under `tests/support/`; they are not another playable Demo catalog. Physical
speaker and phone acceptance require device testing.

## Provenance and private preparation

The pack contains 100 original, unmodified Apple preview excerpts, approximately
30 seconds each. It contains no full songs. Private acquisition tooling and media
remain Git-ignored and are not the teacher's installation path; the public Drive
installer needs no signing key or media encoder.

Apple's [developer terms](https://developer.apple.com/support/terms/apple-developer-program-license-agreement/)
and [iTunes preview terms](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/index.html)
restrict downloading/rehosting previews. Packaging and checksums do not establish
an educational exemption or grant redistribution rights; these files are not
CC-licensed or cleared for redistribution.
