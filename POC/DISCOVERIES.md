# Scrappy PoC discovery report

Date: 2026-09-29

## Executive summary

The core game flow is feasible without an Apple Music subscription:

1. Spotify supplies the tester's personal song history.
2. Apple Music's catalog matches those songs by ISRC.
3. Apple, iTunes Search, and Deezer supply preview candidates.
4. A small LAN room lets a second device receive and start the same preview.

The unavailable part is Apple personal listening history. Apple catalog access
works with a developer token, but heavy rotation, recently played, and library
endpoints require a Music User Token from a subscribed Apple Music account.

This is evidence for the product design, not production-ready application code.
The implementation is intentionally small, memory-only, and isolated on the
dedicated `POC` branch.

## What the PoC contains

- `apple_music_poc.py`: local server, Apple developer-token generation, Apple
  catalog probes, MusicKit hand-off, Spotify PKCE sign-in, preview resolution,
  report generation, and room synchronization.
- `index.html`: browser controls and results for questions Q1-Q7.
- `test_apple_music_poc.py`: automated coverage for token, provider, security,
  report, and LAN-mode behavior.
- `requirements-poc.txt`: dependencies isolated from the application.
- `README.md`: setup, run, LAN, and verification instructions.

Tokens, PKCE verifiers, imported songs, and provider responses stay in server
memory. The generated report contains aggregate measurements rather than the
user's song titles or credentials.

## Results

| Question | Outcome | Evidence | Consequence |
|---|---|---|---|
| Q1 - Apple developer token | Passed | Live catalog search succeeded; 5/5 sampled results contained an ISRC and Apple preview URL | Apple catalog integration is usable |
| Q2 - Apple browser sign-in | Blocked by account prerequisite | MusicKit opened Apple's flow, which required purchasing a subscription; no Music User Token was issued | A subscribed tester is required to validate Apple personal access |
| Q3 - Apple listening data | Blocked by account prerequisite | Heavy rotation, recently played, and library each returned HTTP 403 with Apple code `40300` without a user token | Do not design personal import around Apple alone |
| Q4 - Preview coverage | Functional pass; exact coverage pending | Imported Spotify songs were matched and their previews played in the browser | Apple-first preview resolution is viable, but the coverage target still needs recorded measurements |
| Q5 - Two-device room | Functional manual pass; timing pending | The first URL was unreachable while the server was loopback-only; after binding to `0.0.0.0`, the regenerated room worked correctly on the second device | Keep LAN mode explicit and capture numeric drift in a repeat run |
| Q6 - Spotify import | Functional pass; exact counts pending | OAuth with PKCE completed and the tester's personal songs loaded correctly | Spotify can provide the personal-song corpus for this tester |
| Q7 - Apple charts | API criterion passed | 50 chart songs returned; 50/50 had ISRC and preview URLs; request took 332 ms | Apple charts can supply decoys without personal Apple access |

## Provider discoveries

### Apple Music

- There is no "Apple Music Pro" requirement. A normal Apple Music subscription
  is needed for personal account data, not for public catalog data.
- The developer token identifies and authorizes the developer integration. It
  is separate from a user's sign-in and Music User Token.
- With only the developer token, the live PoC successfully accessed
  storefronts, genres, song/album/artist/playlist search, search suggestions,
  charts, song lookup by ISRC, artwork, duration, and preview URLs.
- Preview URLs returned audio bytes without a personal Apple subscription, and
  the tester confirmed browser preview playback through the Spotify-backed run.
- MusicKit's browser token is origin-restricted. A request with the registered
  loopback origin succeeded; the same token without that origin was rejected.
- Server-to-server catalog calls therefore use a separate developer token that
  does not carry the browser-origin restriction.
- `/v1/me/history/heavy-rotation`, `/v1/me/recent/played/tracks`, and
  `/v1/me/library/songs` are behind the Music User Token boundary.

### Spotify

- The Spotify Soloist API key shown in the dashboard is a different product; it
  does not authorize Web API access to top and recently played tracks.
- A normal Spotify Web API application is required so Spotify can identify the
  client and allowlist the exact callback URL.
- Authorization Code with PKCE works with the public client ID. This local PoC
  does not need, expose, or retain a client secret.
- The requested scopes are only `user-top-read` and
  `user-read-recently-played`.
- The callback must match exactly: `http://127.0.0.1:8765/callback`.
- Top tracks across three time ranges and recently played tracks are normalized
  into one song shape, then deduplicated by ISRC or normalized title/artist.
- Spotify's deprecated track preview field is deliberately not part of the
  preview strategy; Spotify supplies song identity and Apple remains the first
  preview source under test.

### Preview strategy

The resolver tries providers in this order:

1. Apple catalog lookup by ISRC.
2. iTunes Search by title and artist.
3. Deezer lookup by ISRC.

This separates personal-data import from audio delivery. It also means the
project can test Apple matching and preview availability using real listening
choices even when the available Apple account is unsubscribed.

## LAN synchronization discovery

The initial second-device failure was a network-listener problem, not a room
protocol failure. A server bound to `127.0.0.1` cannot be reached from a phone,
even if the page displays the Mac's LAN address.

LAN mode now requires an explicit `--host 0.0.0.0` start. In that mode the
server listens on all interfaces and advertises the LAN URL. In loopback mode,
the page no longer presents an unreachable second-device link. Apple and
Spotify authentication remain on `127.0.0.1`; the phone receives only the
shared preview and synchronization routes.

The tester confirmed that the regenerated room worked correctly on the second
device. A future run must retain measured drift and absolute start error before
claiming the roughly 300 ms synchronization target.

## Design decisions supported by the PoC

- Use Spotify as the personal listening source for the currently available
  tester.
- Use Apple catalog data for ISRC reconciliation, previews, metadata, artwork,
  and chart-based decoys.
- Retain iTunes Search and Deezer as preview fallbacks.
- Do not promise Apple history import until it is tested with a subscribed
  account.
- Keep manual picks and demo data as product fallbacks.
- Treat LAN synchronization as functionally proven but not quantitatively
  accepted until drift is recorded.
- Do not reuse this PoC directly as production architecture. Production work
  needs durable session design, deployment-safe OAuth callbacks, explicit
  privacy handling, observability, and provider-failure behavior.

## Measurements still needed

1. Retain the Spotify unique-song count and ISRC percentage.
2. Retain Apple match rate, Apple preview rate, and cumulative fallback coverage
   for the Spotify corpus.
3. Record three explicit browser playback confirmations.
4. Record two-device drift and absolute start error.
5. If a subscribed Apple Music tester becomes available, repeat personal Apple
   sign-in and listening-data probes as a separate result.

## Run and verify

From the repository root:

```bash
POC/.venv/bin/python POC/apple_music_poc.py serve
```

For a second device on the same trusted Wi-Fi:

```bash
POC/.venv/bin/python POC/apple_music_poc.py serve --host 0.0.0.0
```

Run the automated checks:

```bash
POC/.venv/bin/python -m py_compile POC/apple_music_poc.py POC/test_apple_music_poc.py
POC/.venv/bin/pytest -q POC/test_apple_music_poc.py
```

Final local verification on 2026-09-29 passed all 26 automated tests. The
embedded browser JavaScript parsed successfully, and the running server
returned HTTP 200 through both loopback and the Mac's current LAN address. The
test suite emits one dependency deprecation warning from Starlette's test
client; it is not a PoC test failure.

Full implementation instructions and credential setup are in `README.md`. The
original experiment questions and detailed live evidence remain in
`../docs/04_POC.md`.
