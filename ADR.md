# Architecture Decision Records

## 1. Backend framework: Python + FastAPI
Date: 2026-09-25
Status: Decided
Context: The app is a single-process web server that serves pages, exposes a small JSON API for the game, and makes outbound calls to Apple Music/Spotify while importing players' songs. I need a Python framework I can explain line by line.
Decision: Use FastAPI (served by uvicorn), with SQLite accessed through the standard `sqlite3` module.
Alternatives considered: Flask is simpler, but it is synchronous, so the slow outbound music-API calls would block a worker while waiting. Django brings an ORM, admin and auth system that this app doesn't need (no accounts, one small schema), which adds weight with no benefit.
Consequences: Async endpoints and `httpx` handle the external API calls without blocking, and Pydantic models validate request bodies. The cost is that I have to understand async/await and FastAPI's dependency style.
