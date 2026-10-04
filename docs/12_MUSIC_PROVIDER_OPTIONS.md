> Historical checkpoint/research document. Current architecture, complete offline Demo and storage/setup are described in [README](../README.md), [architecture](05_ARCHITECTURE.md) and [implementation status](08_IMPLEMENTATION_STATUS.md). Four-song references below describe the earlier development seed.

# 12 — Music provider options and tradeoffs

Researched **2026-10-02** for Who's On Repeat. This comparison preserves the practical families of alternatives and their validation plans; it does not claim to audit every reseller on the internet. The accepted one-app five-account Spotify/Apple checkpoint is identified below. Other compared connectors remain research options, not implemented features.

## What we need to obtain

Three different capabilities must be evaluated separately:

| Capability | What the game needs | What it does not establish |
|---|---|---|
| Personal music input | A verified player's songs, with evidence of familiarity and source provenance | A public song catalog cannot tell us who listened to a song |
| Guess search | Broad title/artist search, stable recording identities and structured artist credits | Search does not need every player to connect a music account |
| Playback and artwork | A checked clip and optional image for each planned song and replacement | A metadata result or preview URL alone does not prove browser playback |

The code has bounded signed metadata search in `backend/catalog/search.py` and full-game selection in `backend/game/selection.py`. Configured search now uses the Apple developer adapter; no-credentials Demo retains public iTunes. The accepted checkpoint now implements Normal Spotify admission for at most five approved accounts, with Apple developer catalog search/previews. The runtime Demo catalog still contains four fictional songs; changing the search provider does not populate that catalog. See [the implementation checkpoint](13_SPOTIFY_IMPLEMENTATION.md) for current boundaries and verification gaps. The [existing PoC](04_POC.md) records Spotify authorization and Apple preview resolution on 2026-09-29, with quantitative coverage still pending.

## Main findings

1. A single new Spotify development app supports five approved accounts, including the host if the host connects. This is an app-wide account limit, independent of room size and concurrent play. Extended access removes it, but its current organizational eligibility is unsuitable for this coursework. [Spotify quota modes](https://developer.spotify.com/documentation/web-api/concepts/quota-modes)
2. **There is a multi-app option worth testing.** Spotify's July 2026 changelog increased the developer app limit from one to 25. Development apps owned by the same developer share request quota buckets. Two apps with separate groups of five approved users are therefore a plausible ten-person class setup, not a verified deployment or an unrestricted public service. The February guide's one-app entry is outdated for this specific point. [July changelog](https://developer.spotify.com/documentation/web-api/references/changes/july-2026)
3. ListenBrainz, Last.fm and stats.fm can supply music data they have collected or imported. They add accounts, setup and data-availability dependencies. They should be tested with fresh accounts before promising immediate admission.
4. Spotify history-file import avoids our app's Spotify account limit and can preserve real listening evidence. It adds preparation and upload work.
5. Public metadata APIs and many marketplace scrapers solve catalog search, not private listening-history access. Unofficial authenticated APIs exist, but their session handling and maintenance costs make them a weak default.

## Personal music input comparison

“More than five” below means independent player inputs without connecting all players to one new Spotify development app. It does not mean unlimited requests, instant history, or an already tested integration.

| Option | More than five? | Main tradeoff and current assessment |
|---|---|---|
| One Spotify Web API app | No, for new development apps | Best immediate fit for 3–5 approved testers; native top/recent data and existing PoC |
| Two configured Spotify apps | Plausible; validate | Preserves Spotify login for ten known classmates; doubles allowlist/client configuration and routing |
| Player-owned Spotify app | Plausible; validate | Each player needs developer setup and a Premium-owning account; unsuitable lobby friction |
| Grandfathered Spotify app | Only with existing extra approvals | Useful only if we already have one; an old creation date alone is insufficient |
| Spotify extended access | Yes, if approved | Current published eligibility includes a registered organization and 250k monthly active users; not a class-project plan |
| Spotify history export | Yes, file-based | Real historical data; export wait, upload parsing and stale-data tradeoffs |
| ListenBrainz | Yes, through its stored data | Extra account and Spotify connection; validate fresh-account import time and song count |
| Last.fm | Yes, through recorded scrobbles | Strong for existing users; a newly linked account lacks a rich historical record |
| stats.fm | Candidate; validate | Official SDK exists; account privacy, dataset availability and supported ownership authentication need checks |
| Apple Music | Different provider | User authorization and Apple Music account/subscription prerequisites; cannot read Spotify history |
| Deezer | Different provider; access uncertain | Personal-data OAuth onboarding is a separate obstacle even when public search works |
| YouTube Music | Different provider | No verified official drop-in listening-history API; exports or unofficial clients add substantial work |
| SoundCloud | Different provider | Likes/playlists can supply preferences; not Spotify history or verified play frequency |
| TIDAL | Different provider | Public OAuth/catalog APIs exist; suitable personal listening-history access not verified |
| Amazon Music | Different provider | Official developer portal still labels Web API a closed beta |
| Manual song list / playlist export | Yes, self-declared | Predictable class setup; changes “listened to” into self-reported familiarity |
| Bundled Demo assignments | Yes, fictional familiarity | Most deterministic full-loop testing; cannot claim personal listening history |
| Official API wrapper / hosted proxy | Usually no | A wrapper still uses the upstream credentials and access rules |
| Unofficial web-session API | Technically possible; unverified | Extra credential/session handling, breakage and anti-automation dependencies |

### Spotify: direct integration and multi-app configuration

Top tracks represent Spotify's calculated affinity across short, medium and long windows, not exact play counts. Recent tracks provide recent listening events, with up to 50 per request; this is not a complete lifetime archive. Preserve those source labels instead of presenting inferred difficulty as measured frequency. [Top tracks](https://developer.spotify.com/documentation/web-api/reference/get-users-top-artists-and-tracks), [recent tracks](https://developer.spotify.com/documentation/web-api/reference/get-recently-played)

**Two-client proposal, subject to a live check:** configure clients A and B on the backend; approve a fixed group of up to five accounts per client; bind each OAuth state, PKCE verifier, callback and import to its chosen client. One room can merge the resulting song inputs because the game identity is independent of the OAuth client. Handle a wrong-group 403 explicitly. Never exchange a code through another client or silently cycle clients as an error-recovery mechanism. Validate the dashboard and cross-client import first; published limits do not establish that this particular configuration works.

This is configuration for known classmates. It requires managing both user groups and credentials, shares developer request quotas, and offers no unrestricted public onboarding. A player-owned client has even higher setup cost. Neither option has been exercised in this research.

Existing apps with more than five approved users retain those approvals. An old app with only one user does not automatically gain a larger allowance. [Migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide)

Using only the host's Spotify token cannot retrieve the other players' private history. Client credentials can support public catalog operations, but cannot access user resources. A library such as Spotipy simplifies calls without changing these permissions. [Client credentials](https://developer.spotify.com/documentation/web-api/tutorials/client-credentials-flow), [Spotipy](https://github.com/spotipy-dev/spotipy)

### Intermediaries

**ListenBrainz:** players can connect Spotify on ListenBrainz and our game can read their stored listens. Manual setup avoids requiring our game to perform Spotify OAuth. A seamless in-game connection flow is different: ListenBrainz requires an approved MetaBrainz `listenbrainz:connect-services` scope. Do not promise that flow without approval. Its APIs expose recent listens and history exports; sufficient data, synchronization delay and correct ownership remain PoC gates. [Add data](https://listenbrainz.org/add-data/), [connection flow](https://listenbrainz.readthedocs.io/en/latest/users/connect-music-services.html), [listen API](https://listenbrainz.readthedocs.io/en/latest/users/api/core.html)

Use ordinary MetaBrainz profile authorization to verify the player separately. ListenBrainz's maintainer documentation notes that upstream recent-listen data can lag for hours. Statistics may also be absent for a fresh account. Consequently, manual connection avoids our own app allowance but does not guarantee a populated lobby within ten seconds. [Identity OAuth](https://musicbrainz.org/doc/Development/OAuth2), [Spotify-reader diagnostics](https://listenbrainz.readthedocs.io/en/latest/maintainers/spotify-reader.html), [statistics API](https://listenbrainz.readthedocs.io/en/latest/users/api/statistics.html)

**Last.fm:** read recent tracks and top tracks using an app API key and a username; the read methods do not require user authentication. Top tracks include play counts for recorded scrobbles. Spotify can be linked to record listening. A username is not proof of ownership, and creating an account is not equivalent to importing years of Spotify history. Verify ownership separately if this becomes a Normal admission method; test dataset availability for new users. [Recent tracks](https://www.last.fm/api/show/user.getRecentTracks), [top tracks](https://www.last.fm/api/show/user.getTopTracks), [Spotify tracking](https://www.last.fm/about/trackmymusic)

Last.fm has a supported web authorization flow that can establish the account owner before reading their public music data. [Web authorization](https://www.last.fm/api/webauth)

**stats.fm:** this is a real candidate, not merely a collection of unofficial wrappers. Its official GitHub organization publishes `statsfm.js`; the user manager exposes top tracks, recent streams and stream statistics. That establishes an API surface, not guaranteed anonymous access to every profile. Private data, fresh-account availability, ownership verification, supported external login, current import costs and service stability still need a PoC. Do not ask players to paste internal stats.fm login tokens as a substitute for supported admission. [Official SDK](https://github.com/statsfm/statsfm.js), [user API implementation](https://github.com/statsfm/statsfm.js/blob/main/src/lib/users/UsersManager.ts)

The SDK defines privacy settings for top tracks, recent plays and streams. Its existence should not be read as a service-level guarantee. The historical import support page now redirects to a replacement help center, so this report does not promise a current price or fixed synchronization time. Historical support guidance describes Spotify export import for complete counts/history; a fresh linked account should not be assumed to contain that dataset. [Privacy model](https://github.com/statsfm/statsfm.js/blob/main/src/interfaces/statsfm/user.ts), [import support](https://support.stats.fm/docs/import/spotify-import/)

### Other music services

| Service | Verified capability and practical obstacle | Assessment |
|---|---|---|
| Apple Music | MusicKit authorization, recent tracks, library and eligible-year Replay; developer signing credentials plus authorized Apple user data | Good for Apple subscribers; our PoC account did not meet the personal-data prerequisite. [MusicKit](https://developer.apple.com/musickit/), [recent tracks](https://developer.apple.com/documentation/applemusicapi/get-v1-me-recent-played-tracks), [Replay](https://developer.apple.com/documentation/applemusicapi/get-the-user%27s-replay-data) |
| Deezer | Public search succeeded; new app registration was not verified. A May 2026 community reply reports closure; staff describe existing IDs being disabled/reinstated | Public clips are a candidate; defer personal OAuth without working credentials. Community signup reports are not an official reopening promise. [Registration discussion](https://en.deezercommunity.com/features-feedback-44/app-registration-82666), [staff access discussion](https://en.deezercommunity.com/your-account-favorites-and-playlists-70/oauth-exception-81676) |
| YouTube Music | Official YouTube API cannot list watch history; Google Takeout exports data. `ytmusicapi` exposes history by emulating web requests and is not supported by Google | File import is the supported historical route; unofficial client remains experimental. [API boundary](https://developers.google.com/youtube/v3/docs/playlistItems/list), [Takeout](https://support.google.com/accounts/answer/3024190), [ytmusicapi](https://ytmusicapi.readthedocs.io/en/stable/) |
| SoundCloud | Official OAuth, likes, playlists, search and playback; API registration currently requires an Artist Pro account | Preferences rather than verified Spotify history; extra provider subscription/setup and different catalog. [Guide](https://developers.soundcloud.com/docs/api/guide), [API reference](https://developers.soundcloud.com/docs/api/explorer/) |
| TIDAL | Official OAuth and public API reference; a suitable personal history endpoint was not verified in the current research | Revisit only for actual TIDAL users with a successful personal-data PoC. [Authorization](https://developer.tidal.com/documentation/api-sdk/api-sdk-authorization), [reference](https://developer.tidal.com/reference) |
| Amazon Music | Official portal explicitly labels its Web API closed beta | Access gate makes it unsuitable for the immediate milestone. [Developer portal](https://developer.amazon.com/docs/music/landing_home.html) |

Moving to another provider does not transfer an existing Spotify listening history. Libraries, liked songs and playlists are preference evidence; they must not be treated as exact play frequency.

### Exports and user-declared inputs

Spotify provides JSON packages containing listening history and playlist/library data. Basic history covers the past year; the extended package covers lifetime streaming history. A file importer could obtain actual historical songs without Spotify OAuth in our application. An uploaded file is not authenticated ownership proof; label it as user-supplied evidence. Parse only necessary music fields, bound upload size, exclude podcasts, handle missing identities and different export schemas, and discard unrelated account data. Freshness and time spent requesting an export make this a prepared-session option rather than instant joining. [Spotify export contents](https://support.spotify.com/in-en/article/understanding-your-data/)

A CSV/song list or playlist export is easier to prepare, but says which songs the player chooses, not how often they listened. A public playlist URL is not a history API, and provider access to playlist contents must be verified. A local Demo pool is best for deterministic tests. Both require an explicit requirement decision before being presented as Normal mode; neither should silently replace failed Spotify imports.

### Unofficial APIs and marketplace services

SpotAPI emulates Spotify browser requests and documents cookie import or login with CAPTCHA-solving machinery. This could technically use access paths outside our development client, but the maintained project's feature claims are not proof that our top/recent import works today. Browser sessions are stronger credentials than a scoped read-only authorization; session expiry, login challenges and private endpoint changes become our maintenance problem. Recommendation: keep this out of the main coursework implementation. [SpotAPI maintained source](https://github.com/Aran404/SpotAPI)

RapidAPI/Apify-style services fall into three categories: official API proxies, public metadata scrapers, or authenticated private-session integrations. Only the last could plausibly replace personal history access, and it still requires a documented consent/session path. For example, a marketplace Spotify scraper explicitly limits itself to logged-out public data and excludes user listening history. Other listings advertise “listening habits”; that wording alone is not evidence of authenticated top tracks or timestamped listens. [Example public scraper limitations](https://apify.com/sourabhbgp/spotify-scraper)

No verified turnkey hosted service was found that supplies arbitrary consenting players' current Spotify top/recent data with immediate onboarding and no extra account setup. This is a research finding, not a proof that no such service exists.

## Catalog search, clips and recording matching

The search field should query a broad catalog as the user types, not download all existing songs. No provider covers every recording ever made. We need bounded results, cancellation, cache reuse and signed selections; those behaviors already exist. Personal pool membership must never affect public search results or expose which players know a song.

| Source | Useful capability | Tradeoff for this game |
|---|---|---|
| Spotify Search | Broad song catalog and structured credited artists | Backend authorization and quotas; public search does not solve personal imports |
| Apple public iTunes Search | Title/artist search, artwork and some previews | Already integrated; lightweight credentials setup; main artist field is insufficient for complete collaboration credit |
| Apple Music catalog | ISRC lookup, song metadata, charts/decoys and preview references | Developer token/key setup; personal user token is a separate concern |
| Deezer public API | Search, track/ISRC lookup and available previews | Useful supplemental clip source; verify region, version and coverage |
| MusicBrainz / Cover Art Archive | Recording IDs, credits, ISRC relationships and cover references | Good reconciliation layer; not an audio source or complete instantaneous autocomplete catalog |
| YouTube Data API / embedded player | Video search and video playback | Quotas, music/video ambiguity and answer-revealing player metadata; no direct Web Audio clip replacement |
| Jamendo | Searchable independent music and audio references | Different repertoire; does not satisfy a catalog centered on mainstream requested songs |
| Musicfetch | Hosted cross-platform metadata/ISRC matching | Paid service and another dependency; reduces reconciliation work, not personal import limits |
| AcoustID | Fingerprint identification of an existing audio file | Requires actual audio/fingerprint; not title search or a clip source |
| Bundled local catalog | Stable audio/artwork for tests and a prepared demo | Finite curated repertoire and maintenance; no personal-history import |

Detailed source checks and live sample results are recorded below. Clip discovery must verify recording/version, duration, HTTP delivery, browser decoding and audible playback. Cross-provider artist IDs differ: keep canonical identities and all credited artists, resolve aliases deliberately, and do not compare Spotify and Apple IDs directly. ISRC is a useful candidate lookup, not sufficient validation.

### Access, throughput and source evidence

- **Spotify:** Search returns up to ten results per request in development mode. Client credentials allow app-level public search; user imports remain separate. Track preview fields are deprecated and nullable. Keep a clip resolver rather than requiring Spotify preview availability. [Search reference](https://developer.spotify.com/documentation/web-api/reference/search)
- **iTunes:** public queries need no developer token; Apple's archived guidance states approximately 20 requests/minute, subject to change. Debounce alone is insufficient for ten players: shared caching and provider limits are necessary. [Search documentation](https://performance-partners.apple.com/resources/documentation/itunes-store-web-service-search-api/), [result fields](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/UnderstandingSearchResults.html)
- **Apple Music:** developer tokens, song artwork/ISRC/preview metadata and ISRC lookup are documented. Several catalog entries can represent one ISRC; storefront and recording variant still matter. [Developer tokens](https://developer.apple.com/documentation/applemusicapi/generating-developer-tokens), [song attributes](https://developer.apple.com/documentation/applemusicapi/songs/attributes-data.dictionary), [ISRC lookup](https://developer.apple.com/documentation/applemusicapi/get-multiple-catalog-songs-by-isrc)
- **MusicBrainz/CAA:** public read metadata, meaningful User-Agent and at most one MusicBrainz request/second per application. Covers may be missing. Use enrichment caching rather than calling it per keystroke. [MusicBrainz API](https://musicbrainz.org/doc/MusicBrainz_API), [Cover Art Archive](https://musicbrainz.org/doc/Cover_Art_Archive/API)
- **YouTube:** current documentation describes a separate default allowance of 100 Search queries/day. Embedded playback has start/end controls, but is a video player rather than a decoded audio buffer; visible media can reveal the answer. It would need a different playback/UI design. [Quota documentation](https://developers.google.com/youtube/v3/getting-started), [Search](https://developers.google.com/youtube/v3/docs/search/list), [IFrame player](https://developers.google.com/youtube/iframe_api_reference)
- **Jamendo:** a client ID enables independent-music search/audio results. This could populate a different demo repertoire, not satisfy requested mainstream artists automatically. [Track API](https://developer.jamendo.com/v3.0/tracks), [authentication](https://developer.jamendo.com/v3.0/authentication)
- **Musicfetch:** offers cross-platform metadata/link resolution behind a paid API. Its extra cost and dependency are hard to justify before testing existing Apple/Deezer lookup. No personal listening-history bridge was established. [Provider product and plans](https://musicfetch.io/)
- **AcoustID:** identifies fingerprints using an application key, at up to three requests/second. Useful only if users supply audio that needs identification. [Web service](https://acoustid.org/webservice)

### Live read-only sample: 2026-10-02

The main agent independently repeated these public GETs after the research agent's probe. No login, player history, full song download or provider configuration was used. Only the first 256 bytes of each available preview were read.

| Public request | Result | What it establishes |
|---|---|---|
| [Deezer search, Stronger](https://api.deezer.com/search?q=Kanye%20West%20Stronger&limit=1) | HTTP 200; Stronger; ISRC `USUM70741299`; preview present; preview Range request HTTP 206 / `audio/mpeg` | One search result currently serves audio bytes |
| [Deezer lookup, same ISRC](https://api.deezer.com/track/isrc:USUM70741299) | HTTP 200; Stronger (instrumental); same ISRC; no preview | Direct ISRC lookup did not return the same playable variant |
| [iTunes ES search, Stronger](https://itunes.apple.com/search?term=Kanye%20West%20Stronger&media=music&entity=song&country=ES&limit=1) | HTTP 200; Stronger; preview present; no ISRC field; preview Range request HTTP 206 / `audio/x-m4p` | One Apple search result currently serves audio bytes |

These are delivery samples, not audible browser playback, full-catalog coverage, regional availability guarantees or tested integration with the game. No fresh Spotify, ListenBrainz, Last.fm, stats.fm or Apple user account was authorized during this research. Personal-data recommendations remain unvalidated until their PoCs.

## Proposed path and validation checklist

Accepted scope for this checkpoint: **one Spotify development app, at most five approved accounts including the host**, with Spotify PKCE top/recent imports and Apple developer catalog search/previews. Apple searches do not require five separate Apple logins; request-rate limits, cache/budgets and HTTP 429 still apply. The application implementation is prepared; callback registration, allowlist verification and five actual account imports remain live QA gates.

Two Spotify clients are a future, unimplemented experiment, not the current admission model. Prepared export import remains a potential history-preserving extension. ListenBrainz, stats.fm and Last.fm remain alternatives requiring their own fresh-account evidence and admission decisions. A populated, curated Demo catalog remains a separate deterministic presentation milestone.

The alternatives' ranking is engineering judgment for this assignment. The accepted current implementation does not imply approval or implementation of new provider accounts, multiple Spotify apps, exports or a Normal-mode fallback.

- [ ] Check the existing Spotify app's actual allowlist and mode.
- [ ] Verify the exact application callback and run five accounts through one configured Spotify app, including host admission, search and the full loop.
- [ ] Future only: test two configured clients with different approved accounts; confirm imports merge and wrong-client errors are explicit.
- [ ] Measure unique valid songs per player, complete artist credits and preview coverage; preserve aggregate counts rather than personal histories in reports.
- [ ] If needed, test one new and one established intermediary account; measure time to a usable dataset, authentication and privacy behavior.
- [ ] Match recognizable sample songs and difficult variants: collaborations, remasters, live tracks, instrumental versions and duplicate album releases.
- [ ] Verify sufficient originals, independent decoys and three replacement candidates per planned slot where available; preserve the existing skip rule.
- [ ] Run a real 3–5-browser Normal game through setup, guesses, private reveal and final rankings; independently check supported-device audible playback. The broader 3–10-player capacity applies to Demo, not one Spotify app.

### Proposed implementation boundaries

Personal provider adapters return normalized songs plus source/rank/listen evidence. An admission/import coordinator verifies the selected provider account and atomically attaches the validated result to the room; network calls stay outside SQLite write transactions. A clip resolver enriches recordings without changing their personal listener ownership. Rooms freezes the validated pool, Game uses its existing selector and timing, and catalog search stays independent. No provider request belongs in the answer deadline or scoring path.

Familiarity is computed from declared evidence: Spotify affinity, recorded scrobbles or user-supplied history are distinct inputs. Mixed-provider absence means “not observed in the imported dataset,” not proof that someone never heard the song. Any expansion beyond verified provider sign-in needs a documented admission and familiarity decision before implementation.
