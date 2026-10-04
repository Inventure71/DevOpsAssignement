# 12 — Music provider options

Research snapshot: **2026-10-02**. The selected implementation uses Spotify for personal listening evidence, Apple for public catalog/previews and a local Demo pack for simulated play. Setup is in [Spotify implementation](13_SPOTIFY_IMPLEMENTATION.md); the earlier live experiment is in [PoC results](04_POC.md).

## Personal music inputs

| Option | Assessment at the research date |
| --- | --- |
| One Spotify development app | Immediate fit for up to five approved accounts, including the host. The allowance is shared across rooms. [Quota modes](https://developer.spotify.com/documentation/web-api/concepts/quota-modes) |
| Multiple Spotify apps | July 2026 raised the developer app limit to 25; owned apps share request quotas. Two separately approved groups were a possible class experiment requiring client-bound OAuth routing and live validation. [July changes](https://developer.spotify.com/documentation/web-api/references/changes/july-2026) |
| Extended or grandfathered Spotify access | Existing extra approvals can help; extended eligibility required an established organization and substantial usage. [Migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide) |
| Spotify history export | Real recorded history, with export delay, file parsing and user-supplied ownership evidence. [Export contents](https://support.spotify.com/in-en/article/understanding-your-data/) |
| ListenBrainz | Stored listens and Spotify connection; fresh-account availability, synchronization delay and ownership authorization need a trial. [Add data](https://listenbrainz.org/add-data/), [connection flow](https://listenbrainz.readthedocs.io/en/latest/users/connect-music-services.html) |
| Last.fm | Scrobbles provide tracks and play counts. Existing users have useful history; new users must build it. Supported authorization can verify ownership. [Top tracks](https://www.last.fm/api/show/user.getTopTracks), [authorization](https://www.last.fm/api/webauth) |
| stats.fm | Official SDK exposes top/recent/statistical data; account privacy, available history and supported ownership login need verification. [SDK](https://github.com/statsfm/statsfm.js) |
| Apple Music | Supported personal API for authorized subscribers; our PoC account lacked the subscription prerequisite. [MusicKit](https://developer.apple.com/musickit/) |
| Other services | Deezer onboarding, TIDAL history access and Amazon's beta access remained unresolved. YouTube Takeout offers exports; SoundCloud likes/playlists represent preferences. These would require separate adapters and evidence rules. |
| Manual lists / Demo | Self-declared or simulated familiarity. Demo is implemented as an explicit mode; file/manual inputs remain proposals. |

Spotify top tracks reflect calculated affinity; recent tracks provide recent events. Preserve their source/rank evidence when estimating familiarity. Public metadata, a host's authorization or an API wrapper cannot supply another player's private listening data. [Top tracks](https://developer.spotify.com/documentation/web-api/reference/get-users-top-artists-and-tracks), [recent tracks](https://developer.spotify.com/documentation/web-api/reference/get-recently-played)

Unofficial session APIs and marketplace scrapers add credential handling and maintenance costs. Public scrapers commonly supply metadata only; no turnkey personal-history replacement was verified in this research. [SpotAPI](https://github.com/Aran404/SpotAPI), [example public scraper](https://apify.com/sourabhbgp/spotify-scraper)

## Public catalog and audio

| Source | Role and tradeoff |
| --- | --- |
| Apple Music catalog | Selected source for ISRC matching, structured credits, chart decoys and preview references; requires developer signing credentials. [Catalog API](https://developer.apple.com/documentation/applemusicapi) |
| Public iTunes / Deezer | Candidate supplemental search/previews; recording variants and credit completeness need checking. These remain historical research/PoC paths. |
| MusicBrainz / Cover Art Archive | Public recording identities, artist credits and artwork references; MusicBrainz CC0 metadata supplies the local search index. [Metadata source](https://musicbrainz.org/doc/Canonical_MusicBrainz_data), [Cover Art Archive](https://musicbrainz.org/doc/Cover_Art_Archive/API) |
| Spotify Search | Public metadata with authorization/quota costs; the application uses Spotify for personal input instead. |
| YouTube / Jamendo / Musicfetch / AcoustID | Respectively video playback, independent repertoire, paid cross-platform matching and audio-fingerprint identification. Each addresses a different requirement from the selected preview flow. |

### Live samples — 2026-10-02

Public probes sampled the first 256 bytes of available previews:

| Request | Result |
| --- | --- |
| [Deezer Stronger search](https://api.deezer.com/search?q=Kanye%20West%20Stronger&limit=1) | HTTP 200; ISRC `USUM70741299`; preview HTTP 206, `audio/mpeg` |
| [Deezer lookup by that ISRC](https://api.deezer.com/track/isrc:USUM70741299) | Instrumental version; no preview |
| [iTunes ES Stronger search](https://itunes.apple.com/search?term=Kanye%20West%20Stronger&media=music&entity=song&country=ES&limit=1) | HTTP 200; preview HTTP 206, `audio/x-m4p`; no ISRC field |

The differing Deezer version made strict recording validation necessary even for ISRC matches. Delivery probes establish bytes served; browser decoding and audible playback remain separate checks.

## Decision and next evidence

Keep the implemented Spotify/Apple split. Before adding another source, verify supported authorization, fresh-account song availability and provenance/familiarity mapping. Multiple Spotify clients and exports remain unimplemented alternatives. Validate the actual Spotify allowlist, imported song counts, difficult recording variants and a complete physical-device game; current contracts and test ownership are in [architecture](05_ARCHITECTURE.md), [API/runtime](07_API_AND_RUNTIME.md) and [testing](18_TESTING_STRATEGY.md).
