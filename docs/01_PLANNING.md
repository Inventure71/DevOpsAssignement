# 01 — Planning

## Goal

**Who's On Repeat** is a party game where friends guess songs and each other's music taste.

## Product reasoning

The initial Apple Music idea evolved after the provider PoC. Real uses Spotify listening data and Apple catalog/previews; Demo assigns simulated libraries. Difficulty estimates familiarity from provider rank and recency. Apple personal listening, synchronized device audio and mashups are deferred.

## Scope

The first version includes rooms, characters, hidden automatic music imports, classic rounds, decoys, scoring, rankings and 30-day room history. Players answer on their own browsers while the host device plays the clip. Start begins an automatic round loop; the host handles settings and recovery.

Demo uses the installed 100-song pack without provider credentials. Real requires authorization and at least ten playable songs per player. Detailed limits and timings belong to [requirements](02_REQUIREMENTS.md) and [game rules](03_GAME_RULES.md).

## Stakeholders

| Who | Needs |
|---|---|
| Players | Quick browser joining, private guesses and fair scoring |
| Host, also a player | Settings, shared audio, Start/End and recovery |
| Operator | Simple setup, persistent data and protected credentials |
| Music providers | Authorized access and compliance with their terms |

## Scale and feasibility

Target 3–10 Demo players or 3–5 approved Real accounts per room, across roughly 20 rooms. At 500 ms polling, full occupancy implies about 400 state reads per second. This is a design target; the measured read probe is recorded in [implementation status](08_IMPLEMENTATION_STATUS.md).

Apple catalog access and Spotify-to-Apple preview resolution worked in the PoC. Demo installs approximately 98 MiB once, then works offline. Real needs operator credentials and approved accounts; independent live-account and phone checks remain in the [playtest checklist](16_DEVICE_PLAYTEST.md).

## Risks

| Risk | Response |
|---|---|
| Personal provider access unavailable | Keep Demo reproducible and validate Real with intended testers |
| Missing or failed preview | Use checked reserves and the bounded replacement/skip policy |
| Browser readiness or autoplay failure | Activate host audio at Start; use automatic check-ins and host recovery |
| Work exceeds the deadline | Prioritize the core game and cut stretch features |

## SMART goals and outcomes

Original deadlines are preserved. Outcomes were recorded on Oct 4.

| Goal | Deadline (2026) | Outcome |
|---|---|---|
| G1: Commit planning, rules, API design and five ADRs | Sep 30, revised from Sep 29 | Design committed Sep 27–30; ADR-4/5 followed on Oct 1 |
| G2: Three humans finish a ten-round key-free Demo with host audio | Oct 1 | Browser-session games and actual-pack HTTP matches passed; three-human speaker check pending |
| G3: Reach 70% unit coverage of Rooms/Game core rules | Oct 2 | Met; current scope and result are in [README](../README.md#verify), with a 90% project gate |
| G4: Three Real players import ten songs each, with 80% playable candidates, and finish a game | Oct 3 | Import implemented; independent-account validation pending |
| G5: Fresh-source setup, 12 meaningful commits over six days, five ADRs over three dates | Oct 4, 23:59 | Startup checked; local history spans eight dates and ADR introductions four. Publication and author review are tracked in the [submission checklist](17_ASSIGNMENT_REVIEW.md) |

## SDLC model

Iterative and incremental: requirements → provider PoC → domain/schema design → Demo → browser UI → provider integration → playtest feedback and cleanup. The PoC reduced provider uncertainty; feedback changed scoring, privacy, invitations and audio recovery.

Provider and visual work consumed more time than planned, and documentation caught up late. The goals above record that effect on the deadlines. [Implementation status](08_IMPLEMENTATION_STATUS.md) keeps the main checkpoints.
