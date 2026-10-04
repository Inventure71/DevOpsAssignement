> Historical checkpoint/research document. Current architecture, complete offline Demo and storage/setup are described in [README](../README.md), [architecture](05_ARCHITECTURE.md) and [implementation status](08_IMPLEMENTATION_STATUS.md). Four-song references below describe the earlier development seed.

# Five-player Normal mode implementation

Checkpoint: 2026-10-02. Normal uses **one Spotify development app with at most five approved accounts, including the host**, plus Apple developer catalog search and preview resolution. Demo remains an explicit, separate mode with capacity ten; its current four fictional songs support lobby/media checks, not a complete match. File imports and multiple Spotify clients are future work.

## Boundaries and data flow

1. Entry chooses Spotify or Demo. A Normal host or new participant starts a cookie-bound OAuth PKCE admission; no room/player is created yet. Existing room credentials restore the same player without a new Spotify login.
2. Spotify verifies the account and supplies short/medium/long top tracks and recently played tracks. Deduplication preserves structured artist identities and source/rank evidence, balancing familiarity strata into at most 60 songs. Short-term top 20 are easy; other short/medium/recent songs medium; long-term only songs hard. The easiest overlap wins. This estimates familiarity from affinity/rank, not exact historical play counts.
3. Apple resolves candidates by ISRC, then title/artist search. Even an ISRC hit must match title/version and lead artist before preview enrichment. Allowed HTTPS media hosts and bounded delivery probes reject unavailable references. Spotify identities remain canonical; matching credited names can add verified Apple artist-ID aliases. Missing featured identities are not invented.
4. Import requires at least ten playable personal songs. Host import obtains up to 30 independent Apple chart candidates and requires at least three playable decoys. A bounded imported dataset defines listener membership; absence is not proof someone has never heard a song. Unavailable observed personal songs retain ownership so another import can supply media without losing listeners.
5. Provider work completes outside database transactions. Rooms then validates lobby state, capacity, nickname and account uniqueness atomically. Normal room capacity is five, Demo ten. The Spotify application's five-account allowance is shared across rooms, not renewed for every new room.
6. The existing Game service freezes the roster and pool, plans rounds/reserves, checks browser loading/decoding during setup, gates synchronized readiness, scores private answers and advances through reveal, rankings and completion. Originals have up to three replacements; skipped slots exceeding 30% of the original requested round count cancel the match. Admission counts alone do not guarantee a viable plan for every round setting.
7. Broad Apple catalog search returns room-bound signed song metadata. Players need no Apple login for this search. Recording matches use frozen identity or compatible normalized title with shared structured artist keys/aliases; artist partial credit uses frozen keys/aliases. No provider call belongs in scoring or the answer-deadline path. Other players' answers remain private, including from the host.

`backend/music/` owns provider transport, adapters, media checks, imports and admission receipts. `backend/api/music.py` owns their HTTP/cookie boundary. `backend/application/music_admission.py` guards receipt validity within the admission transaction. `backend/rooms/music.py` owns imported pool persistence. `backend/catalog/` owns search cache/budgets and signed selections; Game sees plain frozen values. `frontend/application/music-admission.mjs` owns OAuth navigation and import polling, separately from the import progress screen.

## Identity, lifecycle and limits

OAuth state/verifiers and import tokens stay in bounded expiring server memory. The temporary cookie is HttpOnly, SameSite=Lax, scoped to `/api/music/spotify`, with Secure under HTTPS. Receipts expire after 15 minutes; there are at most 64 receipts and eight processing jobs, with two import workers. Callback state is single-use and bound to the initiating browser. A wrong-browser callback cannot consume the rightful receipt.

Only room-credential digests and room-scoped music-account digests enter SQLite; access/refresh tokens do not. Migration 004 adds the account uniqueness index and song `pool_kind`. Conflicting title/version or credited artist under a reused ISRC receives a separate variant identity, preserving ownership and media. ISRC alone cannot award full song credit. Shared title normalization handles Unicode, punctuation/diacritics and trailing featured-credit labels; live, remix, instrumental and remaster versions stay distinct. Status can reissue the room cookie on an identical completion retry. Explicit authorization retry cancels the unfinished receipt first; connection retry resumes its existing import. Completion renews its bounded delivery receipt; polling renews the temporary cookie. A cancelled/expired receipt cannot later create a room. Restart interrupts unfinished admissions, which the player can retry. It does not create nickname-based recovery or device transfer.

Catalog search shares a five-minute, 128-query cache and coalesces identical requests. Configured Apple search has a local protective budget of 60 requests per minute; that is not a published Apple quota or an unlimited-access promise. The no-credentials public iTunes fallback uses 18/minute. Apple/provider HTTP 429, request timeouts and unavailable audio produce explicit errors. Apple Retry-After starts a shared cooldown across catalog operations without sleeping workers; HTTP errors and failed admission receipts preserve safe retry guidance. Preview checks are cached/coalesced separately with bounded concurrency; browser decode checks still run during game setup.

## Configuration and real-account setup

Normal needs `SPOTIFY_CLIENT_ID`, `SPOTIFY_REDIRECT_URI`, `APPLE_TEAM_ID`, `APPLE_KEY_ID` and `APPLE_PRIVATE_KEY_PATH`; `APPLE_STOREFRONT` defaults to `es`. Spotify PKCE does not require a client secret. Spotify supplies personal listening history; Apple supplies public search, previews and decoys. Process environment configuration and signing keys stay outside Git. The real-game launcher loads literal settings from `.env`; direct `python -m backend` does not load that file.

The default application callback is `http://127.0.0.1:8000/api/music/spotify/callback` (port follows `PORT`). Register that exact URL in the Spotify app. The PoC's `http://127.0.0.1:8765/callback` is different. Every participant must be approved in that app; the host consumes one of the five places. The browser entry origin must match the callback origin so its temporary cookie returns.

Loopback works on the server computer. Five separate devices need a reachable HTTPS application URL and its exact registered callback, plus Secure cookies; opening `127.0.0.1` on another phone reaches that phone, not the game server.

## Checkable work and evidence

- [x] Provider adapters and conservative preview resolution with bounded auth/rate failures.
- [x] Verified admission, five-player Normal capacity and atomic persistence.
- [x] Browser sign-in/import states, callback recovery and explicit Demo choice.
- [x] Frontend behavior tests and native desktop/mobile entry inspection.
- [x] Five-player games of 5/10/15 rounds, private scoring/rankings, cancellation, expiry and migration checks.
- [x] Live Apple developer catalog search/charts and one ISRC preview-delivery probe.
- [ ] Register the exact application callback and verify five allowlisted Spotify accounts.
- [ ] Complete actual five-account browser imports/game and supported-device audio checks.
- [ ] Review changed files and publish the approved Git checkpoint.

Live Apple verification returned 20 search results, 30 chart candidates, and an ISRC-matched Stronger preview with HTTP 206/CORS support. This proves catalog and reference delivery for those samples. Native browser Web Audio separately decoded the real Apple Stronger AAC preview as 29.975 seconds, two channels at 48 kHz. Neither result proves complete import coverage or physical speaker audibility. The frontend revision passed 76 Node tests, including ten admission lifecycle tests. All 228 Python tests pass with 94% Rooms/Game coverage; provider boundaries are faked in the five-player loop tests. Final Python/full-loop evidence belongs in [implementation status](08_IMPLEMENTATION_STATUS.md).

The user deferred callback-dashboard configuration, allowlist confirmation and real five-account QA until returning. Automated fixtures exercise the game and admission boundaries; they must not be reported as five real Spotify accounts.
