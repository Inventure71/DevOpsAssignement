# Demo music pack

Demo's pinned pack contains 100 recordings: 80 personal-pool songs and 20 independent Nobody songs. Each player receives 36 personal recordings with simulated familiarity. The Demo source and local resolver use the same import/admission path as Spotify; [architecture](../docs/05_ARCHITECTURE.md#music-admission-and-the-public-catalog) defines the boundary.

[demo_catalog.json](demo_catalog.json) holds public metadata. [demo_pack_source.json](demo_pack_source.json) pins the [Drive ZIP](https://drive.google.com/file/d/1nmv-F4OettnXqMj5JZNp_WzO1XZSCpOp/view), its size, ZIP SHA-256 and inner manifest SHA-256. Downloads and installations live under ignored `catalog/local/`.

## Install the Drive pack

Both launchers install the default pack before starting the server. The first download is about 98 MiB; subsequent launches verify local files and Demo games work offline. Setup needs no provider credentials or media encoder.

From the repository root:

```bash
python3 tools/setup_demo_pack.py
python3 tools/setup_demo_pack.py --check
python3 tools/setup_demo_pack.py --archive /path/to/whos-on-repeat-demo-100.zip
```

On Windows, replace `python3` with `py -3`. `--check` verifies the installed pack offline; `--archive` installs from a downloaded ZIP.

The installer handles Drive confirmation, verifies archive/inventory checksums, rejects unsafe paths and links, and publishes a complete installation atomically under `catalog/local/packs/`. Downloads are cached in `catalog/local/downloads/`. A corrupt or incomplete pack stops the launcher. After an interrupted installation, remove `.drive-install.lock` only once its installer has stopped, then retry.

`--demo-pack <directory>` selects another complete local pack. Bare `python -m backend` starts with Demo unavailable if the configured pack is absent; install it and restart to enable Demo. Existing corrupt assets fail startup validation before application data changes.

## Runtime ownership and validation

Startup reseeds the shared `demo_catalog`; existing room assignments and frozen games retain their copies. Equal normalized ISRCs represent one recording, with the first row supplying preferred media. Conflicting title/artist identities or personal/decoy placement reject the pack. Blank ISRCs remain distinct by Demo ID.

Assets must be present, nonempty and contained inside the selected pack. `/static/demo/local/` serves media and `/music-credits` serves its attribution. Demo guess search uses the complete shared catalog; player assignments remain private. See [data model](../docs/06_DATA_MODEL.md) and [testing strategy](../docs/18_TESTING_STRATEGY.md).

## Provenance and terms

The pack contains original Apple preview excerpts of approximately 30 seconds. Private acquisition tooling is separate from the public installer. Apple's [developer terms](https://developer.apple.com/support/terms/apple-developer-program-license-agreement/) and [preview terms](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/index.html) restrict downloading/rehosting previews; this pack has no established redistribution clearance. Its checksums verify integrity, while `/music-credits` supplies attribution.
