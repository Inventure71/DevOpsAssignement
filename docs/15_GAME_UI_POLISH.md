> Historical checkpoint/research document. Current architecture, complete offline Demo and storage/setup are described in [README](../README.md), [architecture](05_ARCHITECTURE.md) and [implementation status](08_IMPLEMENTATION_STATUS.md). Four-song references below describe the earlier development seed.

# Game UI polish

The blob characters, existing layouts, room identity, invite links, scoring, host sound ownership, and game transitions stay intact. Preparation describes what a player should do instead of exposing provider workers, candidate totals, or clip checks. Playtest mode remains visible and uses the server's minimum player count.

## Search and selection

- Typing, focusing, and state polling never issue a song search. Search or Enter requests results; ↑/↓ then Enter selects a result. Escape dismisses results.
- Editing or Clear drops a previous selection and cancels pending work. Polls retain unfinished queries. Existing results can reopen without refetching.
- Results live only in the current round component. There is no browser catalog cache or cross-room/game reuse of signed tokens.
- Empty, busy, connection failure, and selected-recording failure states provide a useful next step. Errors do not surface raw provider diagnostic messages.
- An unfinished query cannot be submitted as a guess. A blank song guess remains valid; submitting an empty listener selection continues to mean Nobody.

The optimized API contract is additive:

1. `GET /api/rooms/{room}/song-search?q={query}&local=true` returns the existing `songs` array. A bulk-only result may include `resolve_required: true`.
2. Choosing that result calls `POST /api/rooms/{room}/song-selection` with `{ "token": result.token }`. The response is a direct song object containing `title`, `artist`, `artwork_url`, and its usable, room-scoped `token`.
3. The component says “Checking song…” while resolving. It emits `song-select` only after resolution succeeds. Provider-backed rows select immediately.
4. Editing, clearing, disabling, Escape, unmount, and round transitions abort and invalidate pending work. Late replies cannot select or unlock a newer guess. Failed selection keeps results and allows retrying the same row.
5. A genuine ambiguity response may be HTTP 409 with `error.details.alternatives`: up to 20 already-resolved, current-room song results. Valid alternatives replace the list with “Choose the song you mean.” No choice is selected automatically, and choosing one needs no extra lookup. Malformed, oversized, stale, aborted, or disabled responses are ignored.

`SongSearch.search` and `SongSearch.resolve` are narrow injected adapters. The application owns room paths and transport; the component owns UI lifecycle. It never computes scores, stores credentials, or infers recording identity.

## Preparation and recovery

Lobby eligibility checks players, songs and connection state. Clicking Start game activates the host's audio in the gesture stack and obtains a speaker lease before posting the start command. Failed activation leaves the host in the lobby to retry with the same button. Active rounds expose Resume audio only when recovery is needed; another tab's audio lease requires an explicit recovery/takeover action.

`frontend/game/preparation.mjs` translates import and round preparation states into product copy. Screens use that model; backend diagnostics remain available in state/logs. Insufficient playable history still explains the real requirement of at least ten songs and suggests another account or the demo.

Guests wait for their host; hosts are told to keep the audio screen open. Missing players remain named during check-in, and timeout recovery retains the existing host-only retry/continue commands. Audio preload recovery still retries in place, with a concise automatic-retry notice. Invite failures explain the shared address without exposing environment-variable names. Toasts have an explicit dark background and white text.

## Validation

- `node --test tests/frontend/*.test.mjs`: 99 tests pass, including eleven search lifecycle/selection tests and three preparation-state tests.
- `node --check` passes for app, search, and round modules; `git diff --check` passes.
- Isolated provider-free backend on port 8011 uses a temporary data directory. T3 preview verified actual DOM Enter/arrow/Enter selection, no request while typing, resolved-token delivery, and cancellation of a late selection reply.
- Desktop 1280×800 and mobile 375×667 layout checked. Mobile input is 16 px; Search and Clear targets are at least 44 px; no horizontal overflow.
- Browser import screen hides supplied diagnostic counts and presents the busy state. This branch's browser checks use isolated UI fixtures; combined real backend catalog selection, multi-device gameplay, OAuth, and audio acceptance belong to integration QA after combining both branches.

No provider credentials, real player database, or live game server were changed.
