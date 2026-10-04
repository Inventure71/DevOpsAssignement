# Launch and device testing

Demo enables Demo rooms. Real enables both Real (`normal` internally) and Demo rooms. Both choices appear on entry; availability comes from the server configuration.

## Demo: teacher setup and offline play

Install Python 3.12 or newer and download the repository. On macOS or Linux:

```bash
bash tools/run_demo.sh
```

On Windows:

```powershell
py -3 tools/launch_game.py demo
```

First launch creates `.venv`, installs `requirements.txt` and downloads/verifies the pinned 100-song pack (about 98 MiB). Setup requires internet or cached dependencies and a downloaded pack. To install an existing ZIP:

```bash
python3 tools/setup_demo_pack.py --archive /path/to/whos-on-repeat-demo-100.zip
```

Use `py -3` on Windows. After setup, Demo runs offline with local audio, search and SQLite state. Its default data directory is `data/demo`. The pack has 80 personal songs and 20 Nobody songs; each player receives 36 personal songs, and search covers all 100. `--demo-pack <directory>` selects a complete local pack. See [pack details](../catalog/README.md).

The launcher prints a loopback address for the host and a LAN address for other devices. Open the LAN address on phones connected to the same network; allow the server through the host firewall. If detection fails, use the host's LAN IP and printed port. Wi-Fi client isolation may block access. Share the LAN URL rather than the `0.0.0.0` binding address.

Create a room, share its invite, join from another device and click **Start game** to activate the host speaker. Use **Resume audio** if the browser suspends it. Standard games require three players; two-player testing uses:

```bash
bash tools/run_demo.sh --playtest
```

Windows: `py -3 tools/launch_game.py demo --playtest`. On one computer, use separate browser profiles or different browsers; ordinary tabs share the player cookie.

## Real game: credentials and a shared HTTPS origin

Configure the project `.env` with `SPOTIFY_CLIENT_ID`, `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY_PATH`, `APPLE_STOREFRONT` and `APP_PUBLIC_URL`. Spotify participants need approved account access. Quote paths containing spaces; relative paths resolve against the repository. Environment settings override `.env`.

Set `APP_PUBLIC_URL` to the shared HTTPS origin. Set `SPOTIFY_REDIRECT_URI` to that origin plus `/api/music/spotify/callback` and register the exact callback in the Spotify dashboard. Start:

```bash
bash tools/run_real_game.sh
```

Windows: `py -3 tools/launch_game.py real`. Open the printed HTTPS address on every device. Local entry pages redirect there to retain the secure session cookie. Both room modes use that origin. `--playtest` allows two players and repeated approved Spotify accounts with different nicknames; standard admission applies otherwise.

For a Cloudflare quick tunnel, run this separately on the server computer:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

Use the server's port if changed. Keep the tunnel running. A recreated quick tunnel gets a new address: update `.env` and register its Spotify callback before launching. Guests open the HTTPS link. A stable HTTPS deployment can serve the same role.

Choose Real, enter player details and select **Connect your music**. Spotify supplies personal listening history. Apple catalog/previews use the server signing key; Apple personal listening appears as Coming later. Invitations carry room mode; an existing cookie restores its player. Back cancels a pending connection, while a completed admission restores the room.

## Preflight and isolated verification

Both launchers accept `--port`, `--data-dir`, `--demo-pack`, `--playtest` and `--check`:

```bash
bash tools/run_demo.sh --check --port 8010 --data-dir /tmp/repeat-demo-check
bash tools/run_real_game.sh --check
```

`--check` validates configuration, installed music, Python dependencies and port availability. Run a normal launch for first setup. Startups remain in the foreground; Ctrl-C stops the server.

Check the actual devices:

1. Open the printed LAN or HTTPS address on a second device and join through the invite.
2. Start the game and confirm the host speaker plays each clip. During the round, search and select a song.
3. Submit song/listener guesses; confirm controls lock while host audio continues.
4. Verify reveal, leaderboard and automatic next-round transitions.
5. Recover from a temporary disconnect or suspended host audio, then start another game.

The host speaker supplies shared sound. Optional larger metadata imports use `tools/setup_catalog.py --info` or `--all`; Demo setup uses its installed pack.
