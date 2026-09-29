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
- **Throwaway code.** Put it in `poc/` at the repo root. That folder is **gitignored**, so it's never committed and never counts toward the app. Don't reuse PoC code in the app later without review.
- **Don't** create or edit `requirements.txt` or any app code. Install PoC packages in a separate virtualenv inside `poc/`.
- **Secrets:** read the Apple key and IDs only from environment variables. Never print, log or save tokens or the key. Never commit anything from `poc/`.
- **Sign-in is done by me** in the browser. The agent never types passwords.
- Keep it minimal: one small Python script + one HTML page is enough.
- Commit messages: plain and descriptive, with no AI mention or co-author trailer.

## Prerequisites (done by me first)
1. In the Apple Developer portal: create a **Media ID** and a **key** with MusicKit ("Media Services") enabled, and download the `.p8` file (store it outside the repo, or in `poc/`, which is gitignored)
2. Note the **Team ID** and **Key ID**
3. Export them:
   - `APPLE_TEAM_ID`
   - `APPLE_KEY_ID`
   - `APPLE_PRIVATE_KEY_PATH` (path to the `.p8` file)
4. Use my own Apple Music account (active subscription) for Q2–Q4

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
For every unique song from step 3, try in order:
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
- Authorization-code flow with redirect `http://127.0.0.1:<port>/callback` (Spotify doesn't accept `localhost`), scopes `user-top-read user-read-recently-played`
- `GET /v1/me/top/tracks?time_range=short_term|medium_term|long_term` and `GET /v1/me/player/recently-played`
- Record counts and whether `external_ids.isrc` is present

## Success criteria
| Question | Pass if |
|---|---|
| Q1 | A catalog search returns results with the token |
| Q2 | Sign-in returns a user token |
| Q3 | ≥10 unique songs for my account, and each of the three lists returns data (or we learn which one doesn't) |
| Q4 | ≥80% of songs have a playable preview after all sources |
| Q5 | Two devices start within about 300 ms of each other |
| Q6 | *(optional)* Top tracks come back with ISRC |
| Q7 | ≥30 chart songs with ISRC and a playable preview |

**If a check fails**, record what happened. That decides the fallback (manual picks, Spotify, no "all devices" mode) before architecture starts.

---

## Results *(filled in after the PoC)*
| Q | Result | Numbers | Decision |
|---|---|---|---|
| Q1 | | | |
| Q2 | | | |
| Q3 | | heavy rotation: _ · recent: _ · library: _ · with ISRC: _% | |
| Q4 | | Apple: _% · +iTunes: _% · +Deezer: _% | |
| Q5 | | drift: _ ms | |
| Q6 | | | |
| Q7 | | chart songs: _ · with preview: _% | |

**Impact on the design:** _what changes because of these results_
