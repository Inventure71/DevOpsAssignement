# Implementation status

## Current implementation

- Rooms and Game run in one FastAPI process and SQLite database; the native-module frontend is served by the backend.
- Demo uses the pinned 100-song pack: 80 personal recordings, 20 decoys and 36 assigned songs per player. The launcher installs music before starting; server readiness works with Demo disabled when media is absent.
- Spotify and Demo share the source/import/admission pipeline. Real connects before membership; cancellation, session delivery and admission-specific acknowledgement are handled explicitly. Apple provides public catalog/previews; personal Apple listening is deferred.
- Start freezes game facts and prepares the sequence. Next-round loading starts during reveal and continues through the leaderboard, so fresh preparation can enter the next countdown directly.
- Signed catalog answers support recognized release editions; media and listener ownership retain strict recording identity. Private answers, scoring, retained void attempts and history are implemented.
- The UI includes characters, lobby, guesses, reveal and rankings. Start activates host audio; explicit room URLs restore sessions while plain entry URLs open Create/Join.

## Automated verification

Latest public-source run on Oct 4 (private acquisition tooling excluded):

| Check | Result |
|---|---|
| Core unit tests | 323 passed |
| SQLite/HTTP tests | 245 passed |
| Frontend tests | 214 passed |
| Core unit line coverage | 94.79% across six modules |
| Per-domain coverage | Rooms 94.38%; Game 94.94% |

Public Python total: **568**. The local checkout also has 15 Git-ignored acquisition-tool tests; they are not part of the reproducible public count.

Command: `bash tools/verify.sh`. Scope and test ownership are in [README](../README.md#verify) and [testing strategy](18_TESTING_STRATEGY.md).

## Runtime checks

Fresh public-source startup reached readiness in 0.459 s without media and 0.445 s with the pack. Isolated ten- and fifteen-round HTTP/SQLite games passed with actual pack files and separate cookie jars.

Browser checks covered staged Real connection, retained drafts, two Demo sessions, actual clip loading and two reveals. Inspected 375 px and desktop screens had no horizontal overflow. The generated LAN invitation returned HTTP 200 from the host.

An independent Oct 4 submission review reported fresh dependency installation and music download, 0.48 s bare startup, actual-pack ten- and fifteen-round HTTP games, and a five-round browser Demo with host/guest identities using the LAN invitation. These checks establish operation and progression, not physical audibility or three-human/live-account acceptance.

## Capacity probe

```bash
python -m tools.load_demo
```

The historical ASGI probe used 20 games, ten players each, 400 state requests and 20 workers with a fixed clock. All requests succeeded: 463.7 requests/s, median 40.6 ms, p95 75.5 ms. It measured state reads; network transport and concurrent game writes require separate load checks.

## Main checkpoints

| Date | Milestone |
|---|---|
| Sep 29 | Provider PoC, `83e5d13` |
| Sep 30–Oct 1 | Domain/schema design and combined Demo, `bcdcd3d`; backend PR #1 merged into `integration` |
| Oct 2–3 | Browser redesign, provider integration and catalog matching; combined checkpoint `12e6b89` |
| Oct 4 | Single pinned Demo pack and launch cleanup, `528952a` |
| Oct 4 | Bare-startup contract, `d99c90c`, included in `1a8c1ce` |
| Oct 4 | Source adapters, admission race fix, next-round preparation and release-edition guesses |

## Remaining checks

- Known Real onboarding limitation: an old status response can overwrite a newer receipt cookie when connections overlap.
- Independent Real accounts and a complete live-provider game.
- A second physical LAN device joining and playing, with audible host playback and phone refresh/background recovery.
- Full readiness-to-start latency, deployment load and persistent-storage backup/restore.
- Author review of the [report](../output/pdf/assignment-report.pdf), SDLC account, AI explanations and publication evidence in the [submission checklist](17_ASSIGNMENT_REVIEW.md).
