# 04 — Proof of Concept

The isolated `POC` experiment tested music access, preview delivery and synchronized playback before application design. This page records its questions and dated findings. Current behavior is defined in [game rules](03_GAME_RULES.md), [architecture](05_ARCHITECTURE.md) and [API/runtime](07_API_AND_RUNTIME.md).

## Original questions

| Question | Acceptance target |
| --- | --- |
| Apple developer-token signing | Successful catalog search |
| Apple browser authorization and personal lists | Music User Token; at least ten unique songs from heavy rotation, recent tracks and library |
| Playable previews | At least 80% coverage through Apple, then iTunes/Deezer fallbacks; three audible browser samples |
| Synchronized playback | Two devices start within about 300 ms |
| Spotify alternative | PKCE import of top/recent tracks with recording identifiers |
| Apple chart decoys | At least 30 songs with ISRC and playable previews |

Apple signing used `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY_PATH` and storefront `es`. Browser authorization required an Apple Music subscription. The Spotify experiment registered `http://127.0.0.1:8765/callback` and requested `user-top-read user-read-recently-played`. Authorization tokens remained in memory.

## First live run — 2026-09-29

| Check | Observed result |
| --- | --- |
| Apple public catalog | Search, charts, storefronts, genres, suggestions and ISRC lookup returned HTTP 200. Five sampled search results had ISRC and previews. One ISRC returned five catalog matches. |
| Apple personal access | MusicKit opened the subscription purchase flow; the available account had no active subscription. Heavy rotation, recent tracks and library returned 403/`40300` with only a developer token. Personal imports remained untested. |
| Apple decoys | 50 chart songs; all had ISRC and preview URLs; request took 332 ms. Chart audibility remained to be checked. |
| Preview delivery | HTTP 206, `audio/x-m4p`, 2,048 sampled bytes. The tester subsequently played Apple-resolved previews from the Spotify corpus in the browser. Coverage percentages and the three-clip count were not retained. |
| Spotify input | Web API PKCE authorization succeeded and the tester confirmed personal songs loaded. Exact counts and ISRC percentage were not retained. The dashboard's Soloist key did not authorize these Web API endpoints. |
| Two-device room | The first link failed because the server bound to loopback. After binding to `0.0.0.0`, the tester joined from the second device successfully. Numeric start drift was not retained. |

MusicKit's browser token was origin-restricted; server catalog calls used a separate token. These results established usable public Apple access and a functional Spotify input path. The percentage and synchronization targets remained unmeasured.

## Decisions after the experiment

- **2026-09-29:** separate personal listening import from public catalog/preview delivery, and Rooms from Game. Manual/Demo inputs were the proposed first milestone.
- **2026-09-30:** replace manual song selection with hidden assigned Demo pools. Real players must authorize automatic imports; the host provides shared audio and the server coordinates start times.
- **2026-10-02:** choose Spotify personal data with Apple public search, previews and decoys. Alternative-provider research is recorded in [provider options](12_MUSIC_PROVIDER_OPTIONS.md).
- **2026-10-04:** Spotify and simulated Demo use the shared `MusicSource → MusicImporter → MusicAdmissionHandler → Rooms` path. Apple personal listening remains deferred pending a subscribed tester. See [current music setup](13_SPOTIFY_IMPLEMENTATION.md).

## Measurements still needed

Retain aggregate song counts, ISRC coverage, playable-preview coverage and two-device start drift on the next live run. Exercise the configured Spotify account group through a complete game and check audible playback on supported devices. Apple personal imports need a subscribed tester. [Testing strategy](18_TESTING_STRATEGY.md) separates these checks from automated verification.
