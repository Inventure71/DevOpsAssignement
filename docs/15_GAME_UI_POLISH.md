# Game UI polish

## Search and selection

Search or Enter requests results. ↑/↓ and Enter select a result; Escape dismisses the list. Editing or Clear cancels pending work and drops the selection. Polling retains unfinished queries, and resolved results can reopen without another request. Results and signed tokens belong to the current room and round.

A typed query requires selection or clearing before submission. A blank song guess permits a listener-only answer; an empty submitted listener selection means Nobody. Busy, empty and failed states offer a next step through product copy.

The room search API supports deferred recording resolution:

1. `GET /api/rooms/{room}/song-search?q={query}&local=true` returns `songs`. A metadata result may include `resolve_required: true`.
2. Selecting it calls `POST /api/rooms/{room}/song-selection` with `{ "token": result.token }`. The response contains the resolved song's `title`, `artist`, `artwork_url` and usable room-scoped `token`.
3. The component shows “Checking song…” and emits `song-select` after success. Already-resolved results select immediately.
4. Editing, clearing, disabling, Escape and unmount abort pending work. Generation checks discard late responses. A failed selection keeps the list and permits retry.
5. HTTP 409 may supply up to 20 resolved songs in `error.details.alternatives`. Valid alternatives show “Choose the song you mean”; choosing one needs no additional lookup. Invalid alternatives retain the retry state.

The application injects `SongSearch.search` and `SongSearch.resolve` adapters. The component owns query, selection and request lifecycle.

## Preparation and recovery

Lobby eligibility checks players, songs and connection state. Start game resumes host audio in the click handler and obtains a speaker lease before posting. Failed activation leaves the lobby available for retry. Resume audio recovers suspended playback; another tab's lease requires explicit takeover.

`game/preparation.mjs` translates preparation state into player guidance. Insufficient listening history explains the ten playable-song requirement and suggests another account or Demo. Hosts keep the audio screen open; guests wait for the host. Check-in names missing players and exposes retry/continue to the host after timeout.

During reveal and leaderboard, visible clients renew upcoming readiness; hosts require decoded audio and their speaker lease. Current-round check-in remains available when preparation expires. Invitations use the server's shared address, with copy/share recovery when browser APIs fail.

## Validation

Run `node --test tests/frontend/*.test.mjs`. Behavioral tests cover explicit searches, resolution and ambiguity, stale-response cancellation, accepted-answer locking, preparation guidance and audio recovery. Browser checks cover keyboard/focus behavior, 44 px Search/Clear targets, narrow layouts and overflow. Use the [device playtest](16_DEVICE_PLAYTEST.md) for admission and actual host playback.
