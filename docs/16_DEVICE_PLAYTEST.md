# Launch and device testing

There are two launchers. The Demo launcher enables Demo rooms only; the Spotify launcher enables both Normal and Demo rooms. Both room choices remain visible, and Normal is disabled in the Demo launch. The teacher can use Demo without acquiring Spotify or Apple credentials.

## Demo: teacher setup and offline play

Install Python 3.12 or newer and download the repository. On macOS or Linux, run:

```bash
bash tools/run_demo.sh
```

On Windows, run the same portable entry point with Python:

```powershell
py -3 tools/launch_game.py demo
```

The first launch creates the project `.venv` and installs the single root `requirements.txt` when required. Dependency installation needs internet or an already populated pip package cache. If the pinned installation is missing, the launcher also downloads and verifies the 98.02 MiB, 100-song Drive pack once. No Google login is needed. A failed download or invalid installation stops launch with setup guidance. To install from a previously downloaded ZIP without Drive, run `python3 tools/setup_demo_pack.py --archive /path/to/whos-on-repeat-demo-100.zip` (or `py -3` on Windows). After setup, audio, song search, rooms and game state work offline. No `.env`, API keys, music account, Cloudflare, Node build or ffmpeg is needed for Demo installation or play.

The launcher prints two playable addresses: `http://127.0.0.1:<port>/` for the hosting computer, and the detected LAN address for other devices on the same network. Open the LAN address on phones and allow the server through the host firewall if prompted. Wi-Fi client isolation can prevent devices reaching each other; a tunnel is not required for normal local-network Demo play. The server listens on all interfaces, but `0.0.0.0` is a binding address and is not the URL to share. If automatic LAN detection is unavailable, use the hosting computer's LAN IP with the printed port.

Create a Demo room, join from the other devices using the shared invite link, and click **Start game**. This activates the host speaker before starting the match; use **Resume audio** if the browser later suspends playback. Standard rules require three players. For a quick two-player demonstration, use:

```bash
bash tools/run_demo.sh --playtest
# Windows: py -3 tools/launch_game.py demo --playtest
```

For evaluation on one computer, use two separate browser profiles or different browsers for the two players. Ordinary tabs share a session cookie and therefore represent the same player.

Demo ignores `.env` and inherited provider, HTTPS and tunnel settings. Its default SQLite directory is `data/demo`, separate from the existing real-game directory. The sole default pack is the pinned versioned Drive installation at `catalog/local/packs/<pack>-<sha12>/`, with 80 personal songs and 20 Nobody songs. Each player receives 36 personal songs; search covers all 100 recordings. The launcher downloads missing music before starting the server; application startup and games never fetch Demo music. `--demo-pack <directory>` selects an explicit complete local pack; an invalid selection stops preflight. There is no alternate bundled or festival pack. See `catalog/README.md` for pinned installation details.

## Real game: credentials and a shared HTTPS origin

Real mode requires the configured Spotify application, its approved users, and an Apple developer catalog signing key. Configure the ignored project `.env` with `SPOTIFY_CLIENT_ID`, `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY_PATH`, `APPLE_STOREFRONT`, and `APP_PUBLIC_URL`. The real launcher reads literal settings; it does not execute `.env` as a shell script. Quote paths containing spaces. Relative paths resolve against the repository. Explicit environment settings take precedence over `.env`.

`APP_PUBLIC_URL` must be the shared HTTPS origin. Set `SPOTIFY_REDIRECT_URI` to that origin plus `/api/music/spotify/callback`, then **save the exact callback** in the Spotify developer dashboard. The launcher validates the origin, callback, credentials and Apple ES256 key locally; successful preflight does not guarantee that the providers will accept an account or credential remotely.

Run:

```bash
bash tools/run_real_game.sh
# Windows: py -3 tools/launch_game.py real
```

Open the printed HTTPS address on every device. Local HTTP entry pages redirect to that address so the HTTPS room session cookie works. The launcher enables secure cookies and both Normal and Demo rooms. Demo uses the same shared HTTPS address and pinned Demo pack as the offline launcher. `--demo-pack` can choose an explicit prepared pack for either launch. `--playtest` explicitly enables two-player tests and repeated approved Spotify accounts with different nicknames. Without `--playtest` or an explicit `PLAYTEST_MODE=true` setting, normal launches retain the standard admission rules.

Cloudflare runs separately from the application. If using a quick tunnel, install `cloudflared` on the **computer hosting the server**, then keep this command running in another terminal:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

The resulting HTTPS link is reachable from phones and other computers with internet access; guests do not install Cloudflare. A new host must create its own tunnel. Quick tunnel addresses change when the tunnel is recreated, so update `.env` and save the new Spotify callback before launching the real game. The previous host's URL is not portable configuration. The real launcher does not start, stop, install or reconfigure tunnels. If changing `--port`, forward the tunnel to that same port. A stable HTTPS deployment can supply the same shared origin without Cloudflare.

## Preflight and isolated verification

Both launchers accept `--port`, `--data-dir`, `--playtest`, and `--check`:

```bash
bash tools/run_demo.sh --check --port 8010 --data-dir /tmp/repeat-demo-check
bash tools/run_real_game.sh --check
```

`--check` validates configuration, the installed pack, the Python environment, root requirement pins and port availability. The default pack must already be installed; this check never downloads missing music. It creates no environment or application data, installs nothing and starts no server. A missing `.venv` is reported with the instruction to run without `--check` for first setup. A port already in use is reported without stopping its owner. Startups stay in the foreground; Ctrl-C stops the server. The scripts can be invoked by absolute path from another working directory.

During device verification, check create/join, local search, selecting a song, host playback, guesses, reveal, leaderboard, and starting a new game. Sound still plays through the host speaker; audio on every device remains deferred. Checking a prepared real recording in another game reuses its verified public mapping; expiring preview URLs renew separately. A larger music metadata import is optional and is not needed for Demo or launch setup:

```bash
.venv/bin/python tools/setup_catalog.py --info
.venv/bin/python tools/setup_catalog.py --all
```
