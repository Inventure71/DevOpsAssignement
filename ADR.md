# Architecture Decision Records

## 1. Backend framework: Python + FastAPI
Date: 2026-09-25
Status: Decided
Context: The app is a single-process web server that serves pages, exposes a small JSON API for the game, and makes outbound calls to Apple Music/Spotify while importing players' songs. I need a Python framework I can explain line by line.
Decision: Use FastAPI (served by uvicorn), with SQLite accessed through the standard `sqlite3` module.
Alternatives considered: Flask is simpler, but it is synchronous, so the slow outbound music-API calls would block a worker while waiting. Django brings an ORM, admin and auth system that this app doesn't need (no accounts, one small schema), which adds weight with no benefit.
Consequences: Async endpoints and `httpx` handle the external API calls without blocking, and Pydantic models validate request bodies. The cost is that I have to understand async/await and FastAPI's dependency style.

## 2. Separate Rooms and Game inside one application
Date: 2026-09-29
Status: Decided
Context: The assignment needs two distinct backend domains that both use SQLite and can be separated later. The PoC showed that importing personal songs and finding audio previews are separate jobs: Spotify supplied the tester's songs while Apple supplied catalog data and previews.
Decision: Rooms owns room membership, player identification, imported/manual songs and familiarity; Game owns games, rounds, guesses, scoring and rankings. At game start, the application obtains an immutable room snapshot through `rooms.service.get_room_snapshot(room_id)` and passes it to Game; separate history and preview interfaces hide external providers, all within one FastAPI process and one SQLite file.
Alternatives considered: A single music/game service would mix imports, membership and scoring, making changes harder to test. Two deployed services would add network and deployment work and violate Assignment 1's single-process constraint.
Consequences: Each domain has its own service, persistence code and business-logic tests; Game never reads Rooms tables directly or calls a history provider. The snapshot duplicates the game-relevant facts to keep scoring stable, and a later service split still needs transaction and failure-handling design.
