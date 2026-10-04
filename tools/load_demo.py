"""Local ASGI state-read probe using the installed 100-song Demo pack, without audio playback."""

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from backend.app import create_app
from backend.core.config import Config
from backend.api.cookies import cookie_name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=400)
    parser.add_argument("--workers", type=int, default=20)
    args = parser.parse_args()
    current = [1_000_000]
    with TemporaryDirectory() as directory:
        # Probe state reads with the configured pack and isolated game data.
        application = create_app(
            Config(Path(directory)), clock=lambda: current[0], background=False
        )
        with TestClient(application) as client:
            c = application.state.coordinator
            identities = []
            for number in range(20):
                with c.db.transaction() as conn:
                    host = c.rooms.create(
                        conn, f"Host {number}", "coral", "demo", current[0]
                    )
                    room_id = host["room"]["id"]
                    players = [host] + [
                        c.rooms.join(
                            conn, room_id, f"Player {n}", "lavender", current[0]
                        )
                        for n in range(9)
                    ]
                    snapshot = c.rooms.snapshot(conn, room_id)
                    gid = c.game.start(
                        conn,
                        snapshot,
                        {"round_count": 10, "answer_seconds": 20},
                        host["player"]["id"],
                        {
                            "request_id": str(number),
                            "room_revision": snapshot["revision"],
                        },
                        current[0],
                    )["game_id"]
                    c.rooms.set_state(conn, room_id, "playing")
                    game = c.game.repo.game(conn, gid)
                    for slot in json.loads(game["round_plan_json"]):
                        for candidate in slot["candidates"]:
                            c.game.preload(
                                conn,
                                gid,
                                host["player"]["id"],
                                {
                                    "request_id": candidate["song_key"],
                                    "candidate_id": candidate["song_key"],
                                    "ok": True,
                                },
                                current[0],
                            )
                    c.game.advance(conn, gid, current[0] + 5000)
                    attempt = c.game.repo.current(conn, gid)
                    for player in players:
                        c.game.ready(
                            conn,
                            gid,
                            attempt["id"],
                            player["player"]["id"],
                            1,
                            current[0] + 5000,
                        )
                    c.game.advance(conn, gid, current[0] + 8000)
                    identities.extend((room_id, p["token"]) for p in players)
            current[0] += 8000
            with c.db.read() as conn:
                before = [
                    (g["id"], g["state_version"]) for g in c.game.repo.active(conn)
                ]

            def read(index):
                room_id, token = identities[index % len(identities)]
                began = time.perf_counter()
                response = client.get(
                    "/api/rooms/" + room_id + "/state",
                    headers={"Cookie": cookie_name(room_id) + "=" + token},
                )
                return response.status_code, (time.perf_counter() - began) * 1000

            began = time.perf_counter()
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                results = list(pool.map(read, range(args.requests)))
            elapsed = time.perf_counter() - began
            with c.db.read() as conn:
                after = [
                    (g["id"], g["state_version"]) for g in c.game.repo.active(conn)
                ]
            latencies = sorted(r[1] for r in results)
            print(
                json.dumps(
                    {
                        "rooms": 20,
                        "players_per_room": 10,
                        "requests": args.requests,
                        "workers": args.workers,
                        "successful": sum(r[0] == 200 for r in results),
                        "requests_per_second": round(args.requests / elapsed, 1),
                        "median_ms": round(statistics.median(latencies), 1),
                        "p95_ms": round(latencies[int(0.95 * (len(latencies) - 1))], 1),
                        "unchanged_game_versions": before == after,
                    },
                    indent=2,
                )
            )


if __name__ == "__main__":
    main()
