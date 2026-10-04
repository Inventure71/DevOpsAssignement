# Spotify and Apple integration

Real mode uses Spotify personal listening data and Apple public search, previews and chart decoys. Demo uses local recordings with simulated familiarity. Apple personal listening is shown as **Coming later**, pending validation with a subscribed account.

## Source boundaries

`SpotifyListeningAdapter` and `DemoListeningAdapter` implement `MusicSource.read` and return `ListeningData`. Both feed `MusicImporter`, then `MusicAdmissionHandler` and Rooms. Spotify authorization is owned separately by `SpotifyAuthorization`; `MusicAdmissions` manages connection receipts and import jobs. AppleCatalog and PreviewResolver enrich playable recordings without changing their original listener ownership.

Spotify reads short-, medium- and long-term top tracks plus recent tracks, deduplicates recording identities and balances up to 60 candidates. Short-term top 20 are easy, long-term-only tracks hard, and other candidates medium; the easiest overlap wins. All observed songs retain private ownership evidence, including those without playable media. Import preparation and cache policy are in [catalog optimization](14_CATALOG_OPTIMIZATION.md).

Real connection happens before membership. OAuth uses PKCE with a browser-bound, single-use state; room/account checks occur atomically after provider work. Access tokens stay in expiring process memory. The provider-neutral endpoints are `/api/music/{config,admissions,status,cancel,acknowledge}`; the Spotify callback stays `/api/music/spotify/callback`. Lifecycle, cancellation and recovery details are in the [API contract](07_API_AND_RUNTIME.md#12-real-music-connection-runtime).

## Configuration and setup

Fill a local `.env` using [.env.example](../.env.example):

| Settings | Purpose |
| --- | --- |
| `SPOTIFY_CLIENT_ID`, `SPOTIFY_REDIRECT_URI` | Web API app and exact registered callback; PKCE requires no client secret |
| `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY_PATH` | Apple developer catalog signing; keep the `.p8` key outside Git |
| `APPLE_STOREFRONT` | Catalog region; defaults to `es` |
| `APP_PUBLIC_URL`, `COOKIE_SECURE` | Shared HTTPS origin and secure cookies for separate devices |

Approve each participating account in the Spotify development app. Its five-account allowance includes the host and is shared across rooms. Entry and callback must share the same origin for the admission cookie to return.

```bash
bash tools/run_real_game.sh --check
bash tools/run_real_game.sh
```

The Real launcher reads `.env`, validates credentials and installs the [Demo pack](../catalog/README.md) if needed. Direct `python -m backend` reads exported environment variables; set `GAME_MODE=normal` for Real capability.

The application's default loopback callback is `http://127.0.0.1:8000/api/music/spotify/callback`, with the port following `PORT`. It works on the server computer. Separate devices need a reachable HTTPS origin and matching registered callback. The historical PoC callback, `http://127.0.0.1:8765/callback`, is different.

## Verification history

The 2026-10-02 live Apple checks returned search results, chart candidates and an ISRC-matched Stronger preview over HTTP 206. Browser Web Audio decoded that AAC preview as 29.975 seconds, two channels at 48 kHz. Full real-account coverage and physical-device audibility still need a complete live session. Current automated evidence belongs in [testing strategy](18_TESTING_STRATEGY.md); the original experiment is in [PoC results](04_POC.md).
