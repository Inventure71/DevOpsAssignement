# 04 — Proof of Concept

Test the riskiest parts **before** designing the architecture around them (SDLC "Proof of Concept" phase).
This file is also the **brief for the agent that implements the PoC**. The results section is filled in afterwards.

## Questions the PoC must answer
| # | Question | Why it matters |
|---|---|---|
| Q1 | Can the server create an Apple Music **developer token** from my key? | Needed for every Apple call |
| Q2 | Can a player **sign in with Apple Music in the browser** and give us a user token? | Needed for FR6 (import history) |
| Q3 | What listening data do we actually get: **heavy rotation, recently played, library**? How many songs, and with which fields (ISRC)? | Difficulty levels (game rules §4) depend on these three lists; FR9 needs ≥10 songs per player |
| Q4 | What share of those songs have a **playable 30-second preview**? Do iTunes Search / Deezer fill the gaps? | NFR4, and SMART goal G4 (≥80% of rounds playable) |
| Q5 | Can two browsers **start the same clip at the same moment** from a server-given start time, and how far apart are they? | "All devices" audio mode |
| Q6 *(optional)* | Can Spotify sign-in return top tracks + recently played, with ISRC? | Spotify is the backup for Apple (risk table) |
| Q7 | Do Apple Music's **top charts** return songs with ISRC and playable previews, using only the developer token? | Decoy songs (FR21) |

## Rules for the implementing agent
- **Isolated code.** Put it in `POC/` at the repo root and keep it on the dedicated `POC` branch. It does not count toward the application implementation. Don't merge or reuse PoC code in the app later without review.
- **Don't** create or edit `requirements.txt` or any app code. Install PoC packages in a separate virtualenv inside `POC/`.
- **Secrets:** read the Apple key and IDs only from environment variables. Never print, log or save tokens or the key. Commit only the PoC source, tests and sanitized reports; exclude its virtual environment and caches.
- **Sign-in is done by me** in the browser. The agent never types passwords.
- Keep it minimal: one small Python script + one HTML page is enough.
- Commit messages: plain and descriptive, with no AI mention or co-author trailer.

## Prerequisites (done by me first)
1. In the Apple Developer portal: create a **Media ID** and a **key** with MusicKit ("Media Services") enabled, and download the `.p8` file (store it outside the repo)
2. Note the **Team ID** and **Key ID**
3. Export them:
   - `APPLE_TEAM_ID`
   - `APPLE_KEY_ID`
   - `APPLE_PRIVATE_KEY_PATH` (path to the `.p8` file)
4. An active Apple Music subscription is required only for Q2–Q3 and for the
   original Apple-history input to Q4. Catalog search, charts, ISRC lookup and
   preview discovery use the developer token without a personal subscription.

## What to build
### Step 1: developer token (Q1)
- A Python script that builds a **JWT** signed with **ES256**:
  header `{alg: ES256, kid: APPLE_KEY_ID}`, claims `{iss: APPLE_TEAM_ID, iat: now, exp: now + a few hours}`
- Test it with one catalog call: `GET https://api.music.apple.com/v1/catalog/{storefront}/search?term=<song>&types=songs`
- Print only the song name, artist, ISRC and whether `previews[0].url` exists

### Step 2: browser sign-in (Q2)
- A tiny local web page (served on `127.0.0.1`) that loads **MusicKit JS v3**, configures it with the developer token, and calls `authorize()` when I click "Sign in with Apple Music"
- On success, send the Music User Token to the local script **in memory only** (not written to disk)
- Note whether sign-in works on plain `http://127.0.0.1`, or needs HTTPS

### Step 3: listening data (Q3)
With headers `Authorization: Bearer <developer token>` + `Music-User-Token: <user token>`, call:
- `GET /v1/me/history/heavy-rotation`
- `GET /v1/me/recent/played/tracks`
- `GET /v1/me/library/songs` (with the catalog relationship, to get ISRC)

For each list, record:
- Number of songs returned
- The page-size limits met
- Whether ISRC is present
- How long the call took

### Step 4: previews (Q4)
For every unique song from step 3, or from the Spotify import in step 7, try in order:
1. Apple catalog `previews[0].url` (look up by ISRC: `/v1/catalog/{storefront}/songs?filter[isrc]=…`)
2. **iTunes Search API**: `https://itunes.apple.com/search?term=<title artist>&entity=song&limit=5`, field `previewUrl` (no key needed)
3. **Deezer**: `https://api.deezer.com/track/isrc:<ISRC>`, field `preview` (no key needed)

Report the % of songs with a preview after each source. Play 3 clips in the browser page with `<audio>` to check they actually play.

### Step 5: synced start (Q5)
- The page asks the script for "start at server time T = now + 3 s", then starts the same preview at T in **two browsers** (e.g. laptop + phone on the same network)
- Measure how far apart they start (by ear, and/or by logging `audio.currentTime` against the server time)

### Step 6: decoy pool (Q7)
- `GET /v1/catalog/{storefront}/charts?types=songs&limit=50` with the developer token only
- Record how many songs come back, whether ISRC is present, and the % with `previews[0].url`

### Step 7 *(optional)*: Spotify (Q6)
- Authorization Code with PKCE flow, using only the application's client ID
  (no client secret), redirect `http://127.0.0.1:<port>/callback` (Spotify
  doesn't accept `localhost`), and scopes
  `user-top-read user-read-recently-played`
- `GET /v1/me/top/tracks?time_range=short_term|medium_term|long_term` and `GET /v1/me/player/recently-played`
- Record counts and whether `external_ids.isrc` is present
- Convert valid tracks to the same in-memory song shape used by Q4, deduplicate
  them by ISRC (then normalized title/artist), and display only title, primary
  artist, ISRC and source-list labels
- Use that list as Q4 input so Apple catalog matching and preview coverage can
  be tested without an Apple Music subscription

## Success criteria
| Question | Pass if |
|---|---|
| Q1 | A catalog search returns results with the token |
| Q2 | Sign-in returns a user token |
| Q3 | ≥10 unique songs for my account, and each of the three lists returns data (or we learn which one doesn't) |
| Q4 | ≥80% of songs have a playable preview after all sources |
| Q5 | Two devices start within about 300 ms of each other |
| Q6 | *(optional)* Top/recent tracks produce a deduplicated song list and top tracks include ISRC |
| Q7 | ≥30 chart songs with ISRC and a playable preview |

**If a check fails**, record what happened. That decides the fallback (manual picks, Spotify, no "all devices" mode) before architecture starts.

---

## Results — first live run (2026-09-29)

### Test context and limits

- Apple developer credentials were configured for storefront `es`.
- The available Apple account does not have an active Apple Music subscription.
  MusicKit opened Apple's authorization UI, but Apple presented the subscription
  purchase flow and did not return a Music User Token.
- Developer-token catalog checks were run live. The three personal `/v1/me/...`
  endpoints were also called without a Music User Token to verify the boundary;
  each rejected the request as expected.
- Spotify Premium is available. A dedicated Web API application named
  `Who's On Repeat PoC` was created in Spotify development mode with the exact
  redirect `http://127.0.0.1:8765/callback`. Spotify authorization completed
  and the tester confirmed that personal songs loaded correctly. Exact counts
  were not retained before the in-memory server was restarted.
- Apple-resolved previews for the Spotify corpus played successfully in the
  browser. The exact coverage percentages were not retained. The two-device
  room also worked after the LAN binding was corrected, but its numeric timing
  measurements were not retained.

### Apple developer-token capability audit

These calls used no Music User Token and no Apple Music subscription:

| Capability | Live result | What it establishes |
|---|---:|---|
| Storefront lookup | HTTP 200 | Storefront metadata is available |
| Genre lookup | HTTP 200 | Catalog genres are available |
| Song search | HTTP 200 | Songs and metadata are searchable |
| Album, artist and playlist search | HTTP 200 | The catalog surface is broader than the original song probe |
| Search suggestions | HTTP 200 | Search hints/top results are available |
| Song, album and playlist charts | HTTP 200 | Chart-based decoy pools are available |
| Song lookup by ISRC | HTTP 200; 5 catalog matches for the sampled ISRC | Spotify/manual songs can be reconciled with Apple recordings |
| Song fields | ISRC, preview, artwork and duration present in the sample | The game-relevant catalog fields are available |
| Preview delivery | HTTP 206; `audio/x-m4p`; 2,048 bytes sampled | The preview URL serves audio bytes; audible playback is still pending |

The MusicKit JS developer token is restricted to the loopback page origin. A
request without the matching `Origin` header was rejected; the same request
with the registered origin succeeded. Server-to-server catalog calls use a
separate token without a browser-origin claim.

### Spotify setup discoveries

- The dashboard's **Spotify Soloist API Key** is a separate product and does
  not authorize the Web API endpoints for top or recently played tracks.
- The PoC needs a normal Spotify Web API application and its client ID.
- Authorization Code with PKCE is supported for user-specific data. The local
  PoC generates a one-time S256 verifier/challenge and therefore does not need,
  reveal or retain the application's client secret.
- The callback URI is exact and loopback-only:
  `http://127.0.0.1:8765/callback`.
- The authorization redirect was verified locally to contain the S256 PKCE
  challenge and only `user-top-read user-read-recently-played` scopes.
- Spotify tokens and the PKCE verifier remain in server memory. Spotify's
  deprecated track preview URL is deliberately ignored because Apple preview
  coverage is the measurement under test.

### LAN synchronization discovery

The first room link was unreachable from the second device because the server
was listening only on `127.0.0.1` while the page advertised a LAN address. The
room API itself had not failed; the listener was inaccessible outside the Mac.

The server was restarted with `--host 0.0.0.0`. At that run it listened on `*:8765`, and
both `http://127.0.0.1:8765/api/health` and
`http://10.205.3.146:8765/api/health` returned HTTP 200 from the Mac. macOS
Firewall was disabled, block-all was disabled, and both devices must still be
on the same non-isolated Wi-Fi network. The page no longer advertises a
second-device link when the server was started in loopback-only mode. The
tester then opened the regenerated room on the second device and confirmed
that it worked correctly. No numeric drift measurement was retained.

### Personal Apple endpoint boundary

| Endpoint, developer token only | Live result | Conclusion |
|---|---:|---|
| `/v1/me/history/heavy-rotation` | HTTP 403; Apple code `40300` | Requires a Music User Token |
| `/v1/me/recent/played/tracks` | HTTP 403; Apple code `40300` | Requires a Music User Token |
| `/v1/me/library/songs` | HTTP 403; Apple code `40300` | Requires a Music User Token |

This is an expected authorization rejection, not evidence that the endpoints
fail for a subscribed user.

### Question outcomes

| Q | Result | Numbers | Decision |
|---|---|---|---|
| Q1 | **Passed** | 5/5 search results had ISRC and an Apple preview URL | The developer token and catalog integration are usable |
| Q2 | **Blocked by prerequisite** | Authorization UI opened; subscription purchase required; no Music User Token | Do not treat catalog success as personal-data authorization |
| Q3 | **Blocked by prerequisite** | heavy rotation: 403/40300 · recent: 403/40300 · library: 403/40300 | Needs a subscribed tester or a different personal-data provider |
| Q4 | **Functionally verified; measurements pending** | Spotify songs loaded, Apple-first preview resolution ran, and previews played · exact percentages and 3-clip count not retained | Rerun once and preserve the generated aggregate report |
| Q5 | **Functional manual pass; timing measurement pending** | First room link failed because the server was loopback-only · after rebinding, the tester confirmed the regenerated room worked on the second device · drift still _ ms | Preserve the next run's measured drift and audible confirmations |
| Q6 | **Functionally verified; measurements pending** | OAuth/PKCE succeeded and the tester confirmed that personal songs loaded · exact counts/ISRC percentage not retained | Rerun once and preserve the generated aggregate report |
| Q7 | **API criterion passed; playback pending** | chart songs: 50 · with ISRC: 100% · with preview URL: 100% · both: 50 · 332 ms | Apple charts are suitable for the decoy pool; browser audibility is still a separate check |

### Impact on the design (2026-09-29)

Apple developer-token access is sufficient for catalog metadata, storefronts,
genres, search, ISRC matching, chart-based decoys and preview discovery without
an Apple Music subscription. Apple personal listening data remains unverified
because the available account cannot obtain a Music User Token.

Spotify is usable as the source of the tester's personal songs. Those songs go
through the Apple-first ISRC lookup and iTunes/Deezer preview fallback. This
keeps personal-data import separate from preview delivery and tests Apple with
real listening choices. Exact coverage and ISRC measurements still need to be
captured before changing product targets.

Manual picks and demo data form the first playable milestone. Planning and
requirements now mark Apple history, Spotify import and all-device audio as
conditional additions. G4 uses real manual picks instead of requiring Apple
history from an account whose access could not be tested. Spotify familiarity
mapping and numerical preview/timing acceptance remain open; no missing
measurements have been inferred from the functional checks.

### PoC handoff (2026-09-29)

The experiment stays isolated on `POC`. The actual app will be written from
scratch using the findings above; its code will not import or reuse this lab.
The next step is high-level design (`05_ARCHITECTURE.md`, ADR-2): separate
Rooms from Game, and personal-history import from preview delivery. Remaining
measurements gate optional integrations, not the start of the demo/manual core.
The recorded PoC tests cover experimental mechanics, not the assignment's
required Rooms/Game business-logic coverage.

### Later product decision (2026-09-30)

The manual fallback discussed in the Sep 29 handoff was removed after the user
confirmed that players should neither select nor inspect the game song pool.
The first playable milestone now uses assigned hidden demo data. Real personal
songs require automatic import; provider choice and familiarity mapping remain
open. This scope change adds no new PoC measurements. See `06_DATA_MODEL.md`
for the room-local song model, frozen roster and retention decisions.

### Remaining validation

1. Rerun Q6 and retain the unique-song count and ISRC percentage from the
   generated report.
2. Rerun Q4 against the imported Spotify corpus; record Apple match percentage,
   Apple preview percentage and cumulative iTunes/Deezer coverage.
3. Play three resolved clips in the browser.
4. Repeat the now-working two-device room once while preserving drift, absolute
   start error and audible confirmation on both devices.
5. If available, repeat Q2–Q4 once with a subscribed Apple Music tester; keep
   that result separate from the Spotify-backed result.
