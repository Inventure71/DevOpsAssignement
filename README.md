# Who's On Repeat

A music party game: listen to a song, guess its title and identify which players listen to it. Each player answers on their own screen; the **host plays the audio**.

## Run

**For assessment, please use Demo.** It includes 100 real song previews and simulated player libraries, so no Spotify account or API keys are needed. You can try a complete game by yourself using two browser tabs.

You need **Python 3.12+**, a modern browser and internet access for the first setup. From the project folder, run:

**macOS / Linux**

```bash
bash tools/run_demo.sh --playtest
```

**Windows**

```powershell
py -3 tools/launch_game.py demo --playtest
```

The launcher creates the Python environment, installs dependencies and downloads the pinned music pack (about 98 MiB). Later Demo launches and games work offline. There is no frontend build, Google login, Apple key or tunnel to configure. `--playtest` allows two players; normal game rules require at least three.

### Try a game in two tabs

1. Open the **Open on this computer** URL printed by the launcher, normally **http://127.0.0.1:8000/**. Keep this tab as the host.
2. Enter a nickname such as **Host**, select **Demo** and click **Create demo room**.
3. In the lobby, click **Invite a friend** and copy the invite URL. If the browser shows a share dialog, copy the link from there.
4. Open a **second tab**, paste that invite URL, enter another nickname such as **Guest**, and click **Join room**. The room code is filled in by the link.
5. Return to the host tab and click **Start game**. This click enables audio; the song plays from the host tab only. Keep both tabs open.
6. In each tab, search for a song, select a result, choose the listeners (or **Nobody**) and submit the answer. Rounds advance to reveal and rankings.

If the second tab reconnects as Host instead of creating Guest, open the invite in a private/incognito window or another browser: tabs at the same address share session cookies. The usual host loopback URL and LAN invite use separate addresses. You can also open the invite on a phone or another computer on the same Wi-Fi.

Stop the server with **Ctrl-C** in the terminal. If port 8000 is already in use, add `--port 8001` to your launch command and use the newly printed URL.

### Why Spotify mode is unavailable in the submitted Demo

Spotify mode uses each player's actual listening history. It requires my private Apple Music signing key for catalog/previews, a configured Spotify developer app with approved participant accounts, and a shared HTTPS address with its exact OAuth callback registered. Those credentials are excluded from this repository. Consequently, a fresh checkout cannot run Spotify mode without separate provider setup, and its option is disabled during Demo launch.

Demo exercises the same room, round, search, scoring and results flow using local music and simulated listening histories. If you want to configure your own provider credentials, see [Spotify setup](docs/13_SPOTIFY_IMPLEMENTATION.md) and [real-game launch instructions](docs/16_DEVICE_PLAYTEST.md).

**Optional Spotify testing:** If you would like to try the Spotify version, please email me your name and the email address associated with your Spotify account. I can add you to the application's authorized test users and arrange access to the configured game. Authorizing your account alone does not configure Spotify mode in a fresh checkout; Demo remains available without this step.

### Music setup troubleshooting

If the automatic download fails, install the music pack manually:

1. Open [Download the 100-song Demo pack](https://drive.google.com/file/d/1nmv-F4OettnXqMj5JZNp_WzO1XZSCpOp/view) and click **Download** in Google Drive (about 98 MiB).
2. Create `catalog/local/downloads/` inside the project folder and save the file there as **`whos-on-repeat-demo-100.zip`**. Keep it zipped.
3. From the project folder, run the installation command for your platform:

**macOS / Linux**

```bash
python3 tools/setup_demo_pack.py --archive catalog/local/downloads/whos-on-repeat-demo-100.zip
```

**Windows**

```powershell
py -3 tools/setup_demo_pack.py --archive catalog/local/downloads/whos-on-repeat-demo-100.zip
```

The installer checks the ZIP and extracts it into the correct pack directory; you do not need to move individual songs. Once it reports **Demo music verified**, rerun the Demo launch command above. The ZIP and installed music are Git-ignored. If you saved the ZIP elsewhere, replace the archive path with its actual location (use quotes if the path contains spaces).

See [music pack setup](catalog/README.md) for offline integrity checks. After setup, `--check` on either launch command performs a read-only preflight without starting a server. Use the printed browser URL; `0.0.0.0` is only the server's bind address.

## Direct server startup

After installing `requirements.txt`, the deployment command is:

```bash
python -m backend
```

It binds `0.0.0.0`, reads `PORT` (default `8000`) and initializes the single SQLite
file under `DATA_DIR` (default `data`). It needs no `.env`, credentials, interactive
migration or music download to start. `/health/ready` checks server/database
readiness; `/api/config` reports which game modes are available.

Without installed music, Demo is disabled and its admission/preview requests
return an explanation. A configured Normal provider path does not need Demo
media. For a playable assessment game, use the Demo launcher above: it prepares
Python dependencies and the same verified 100-song music pack as installation
steps before starting the server. That first installation needs internet or an
already downloaded ZIP; subsequent games work offline. Installing music into a
running bare-server checkout requires a restart before Demo becomes available.

## Verify

With Python dependencies installed and **Node 24+**, run unit, SQLite/HTTP
integration and frontend checks:

```bash
bash tools/verify.sh
```

The exact core unit-coverage command is:

```bash
python -m pytest -q tests/unit \
  --cov=backend.rooms.service --cov=backend.game.service \
  --cov=backend.game.scoring --cov=backend.game.selection \
  --cov=backend.game.preparation \
  --cov-report=term-missing --cov-fail-under=90
```

Measured on 2026-10-04 from an isolated public-source copy: **286 unit tests
passed; combined core line coverage was 94.05% (601 of 639 statements)**.
Rooms measured **92.13%** and Game **94.79%**. The script enforces **90% for
both the combined core and each domain**, above the assignment's 70% minimum;
integration coverage is not included in the core unit figure.

The complete public-source run passed **504 Python tests (286 unit + 218
integration)** and **178 frontend tests**. Tests use temporary data and need no
provider keys or downloaded music. The existing Python environment was supplied
for verification; this was not a fresh dependency download or a Windows hardware
check. On Windows, run the Python and Node commands from
[the verification script](tools/verify.sh).

See [test ownership](docs/18_TESTING_STRATEGY.md) and
[dated verification evidence](docs/08_IMPLEMENTATION_STATUS.md).

## Architecture

The assignment's single-process application separates HTTP/application commands, Rooms and Game services, owned SQLite repositories and music-provider adapters. The browser separates presentation, transport and host audio. All application tables live in `DATA_DIR/whos_on_repeat.sqlite3` (schema 6, catalog component 3).

- [Architecture and boundaries](docs/05_ARCHITECTURE.md)
- [Data model](docs/06_DATA_MODEL.md)
- [API and runtime](docs/07_API_AND_RUNTIME.md)
- [Code map](docs/09_CODEBASE_MAP.md)
- [Catalog optimization](docs/14_CATALOG_OPTIMIZATION.md)

## Assignment evidence

[ADR.md](ADR.md) contains five decisions. [AI_USAGE.md](AI_USAGE.md) records AI assistance; its explanation drafts need the author's review. [Assignment checklist](docs/17_ASSIGNMENT_REVIEW.md) tracks submission evidence. The local report PDF is a draft and is excluded from source control, alongside credentials, downloaded music, application data and generated artifacts.
