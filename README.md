# Who's On Repeat

A music party game: listen to a song, guess its title and identify which players listen to it. Each player answers on their own screen; the **host plays the audio**.

## Run

**For assessment, use Demo.** It includes 100 real song previews and simulated listening libraries. No Spotify account or API keys are needed, and you can test it by yourself in two browser sessions.

You need **Python 3.12+**, a modern browser and internet access for the first setup. From the project folder, run:

**macOS / Linux**

```bash
bash tools/run_demo.sh --playtest
```

**Windows**

```powershell
py -3 tools/launch_game.py demo --playtest
```

The launcher creates the Python environment, installs dependencies and downloads the music pack (about 98 MiB). Later Demo games work offline. `--playtest` allows two players; regular games require at least three.

### Try a game on one computer

1. Open the **Open on this computer** URL printed by the launcher, normally **http://127.0.0.1:8000/**. Keep this tab as the host.
2. Enter a nickname such as **Host**, select **Demo** and click **Create demo room**.
3. In the lobby, click **Invite a friend** and copy the link.
4. Open the invite in a **private/incognito window or another browser**, enter another nickname such as **Guest**, and click **Join room**. The room code is filled in by the link.
5. Return to the host tab and click **Start game**. This click enables audio; the song plays from the host tab only. Keep both sessions open.
6. In each tab, search for a song, select a result, choose the listeners (or **Nobody**) and submit the answer. Rounds advance to reveal and rankings.

You can also join from a phone or another computer on the same Wi-Fi.

Stop the server with **Ctrl-C** in the terminal. If port 8000 is already in use, add `--port 8001` to your launch command and use the newly printed URL.

Opening the main address shows Create/Join. Refreshing a room's URL reconnects to that room; invitation links open Join.

### Real music and Demo

**Real** uses Spotify listening history and asks new players to connect their music before joining. **Demo** uses simulated libraries and the same gameplay without an external account. An invitation determines the room's mode. Personal Apple Music import is marked **Coming later**; Apple catalog search and previews are used in configured Real games.

Real requires a configured Spotify developer app, approved participants, Apple catalog signing credentials and a shared HTTPS address with a registered OAuth callback. Credentials are excluded from this repository, so Real is disabled during Demo launch. See [Spotify setup](docs/13_SPOTIFY_IMPLEMENTATION.md) and [real-game launch instructions](docs/16_DEVICE_PLAYTEST.md).

**To try Spotify:** email me your name and Spotify account email so I can authorize you and arrange access to the configured game. This does not configure Real mode in your own checkout.

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

When the installer reports **Demo music verified**, rerun the Demo launch command. If you saved the ZIP elsewhere, use its actual path in the command.

See [music pack setup](catalog/README.md) for more help. Add `--check` to a launch command to check setup without starting the server.

## Direct server startup

After installing `requirements.txt`, start the server directly:

```bash
python -m backend
```

The server listens on port `8000` and stores SQLite data under `data/`. Set `PORT` and `DATA_DIR` to change these defaults. It can start without music or provider credentials; available modes depend on that setup. For a playable Demo, use the launcher above. Restart the server if you install music while it is running.

## Verify

With the project Python environment installed and **Node 24+**, run all tests:

```bash
bash tools/verify.sh
```

With the project Python environment activated, measure core unit coverage:

```bash
python -m pytest -q tests/unit \
  --cov=backend.rooms.service --cov=backend.game.service \
  --cov=backend.game.scoring --cov=backend.game.selection \
  --cov=backend.game.preparation --cov=backend.game.song_titles \
  --cov-report=term-missing --cov-fail-under=90
```

Core unit line coverage is **94.79%**: Rooms **94.38%**, Game **94.94%**. The verification script enforces **90% overall and in each domain**, above the assignment's 70% minimum.

The Oct 4 public-source run passed **323 unit + 245 integration = 568 Python tests**, plus **206 frontend tests**. Private acquisition-tool tests are excluded.

Tests use temporary data and offline provider substitutes; no keys or music download are needed. On Windows, run the Python and Node commands from [the verification script](tools/verify.sh). See [testing strategy](docs/18_TESTING_STRATEGY.md) for test scope and further results.

## Architecture

The app runs in one process with two core domains: **Rooms** handles players and membership; **Game** handles rounds and scoring. Both use SQLite. Spotify and Demo share an import and admission path. The browser separates presentation, transport and host audio.

- [Architecture and boundaries](docs/05_ARCHITECTURE.md)
- [Data model](docs/06_DATA_MODEL.md)
- [API and runtime](docs/07_API_AND_RUNTIME.md)
- [Code map](docs/09_CODEBASE_MAP.md)

## Assignment evidence

[ADR.md](ADR.md) records architecture decisions, [AI_USAGE.md](AI_USAGE.md) records AI assistance, and the [assignment checklist](docs/17_ASSIGNMENT_REVIEW.md) tracks the required deliverables.
