# Music-provider feasibility PoC

Everything in this directory is isolated proof-of-concept code for
`docs/04_POC.md`, preserved on the dedicated `POC` branch. It is not production
application code and does not write tokens, API responses, or results to disk.

## Set up

From the repository root:

```bash
python3 -m venv POC/.venv
POC/.venv/bin/pip install -r POC/requirements-poc.txt
```

Export the Apple values without copying them into this repository:

```bash
export APPLE_TEAM_ID='…'
export APPLE_KEY_ID='…'
export APPLE_PRIVATE_KEY_PATH='/absolute/path/to/AuthKey_….p8'
export APPLE_STOREFRONT='es' # optional; defaults to us
```

The Spotify-to-Apple personal-song test needs a Spotify application whose redirect URI is exactly
`http://127.0.0.1:8765/callback`:

```bash
export SPOTIFY_CLIENT_ID='…'
export SPOTIFY_REDIRECT_URI='http://127.0.0.1:8765/callback'
```

The local app uses Spotify Authorization Code with PKCE, so no client secret is
needed or stored.

## Run

Test Q1 directly (safe song fields are the only result data printed):

```bash
POC/.venv/bin/python POC/apple_music_poc.py catalog-test
```

Run the browser lab for Q1–Q7:

```bash
POC/.venv/bin/python POC/apple_music_poc.py serve
```

Open `http://127.0.0.1:8765`. Apple Music authorization must be performed by
the user in the browser. The page says whether plain loopback HTTP worked.

An Apple Music subscription is required only for Q2–Q3 personal Apple data.
Apple catalog search, charts, ISRC matching, and preview discovery use the
developer token and remain available without that subscription.

For the Spotify-backed path:

1. Sign in with Spotify.
2. Click **Load my Spotify songs** to fetch top tracks for all three time ranges
   plus recently played tracks.
3. Inspect the sanitized, deduplicated song list. Only title, primary artist,
   ISRC, and source-list labels are returned to the page.
4. Click **Test these songs with Apple**, then run Q4. The server looks up each
   Spotify ISRC in Apple first and uses iTunes/Deezer only for unresolved songs.
5. Play all three samples, then use the first resolved preview for Q5.

Spotify and Apple user tokens, upstream payloads, and the imported list remain
in memory. The copied report contains aggregate measurements, not song titles.

For Q5 with a phone on the same trusted network, opt into LAN access:

```bash
POC/.venv/bin/python POC/apple_music_poc.py serve --host 0.0.0.0
```

Use `http://127.0.0.1:8765` on the computer for Apple sign-in. Open the LAN URL
shown in the terminal on the phone. Apple token endpoints reject non-loopback
clients; the phone can only use the shared preview/synchronization routes.

The listening-data probe follows every Apple `next` link by default. Set
`POC_MAX_ITEMS_PER_LIST` to a positive integer only when a very large library
needs a deliberate sample cap; the report will mark that list as truncated.

## Verify

```bash
POC/.venv/bin/python -m py_compile POC/apple_music_poc.py
POC/.venv/bin/pytest -q POC/test_apple_music_poc.py
```

Live API results and the three-clip/two-device observations must be copied from
the page into `docs/04_POC.md` only after the real run. The page's “Copy report”
button copies sanitized Markdown; it never includes a key or token.
