"""Map validated HTTP commands to application and domain services."""

from fastapi import APIRouter, Request, Response

from backend.api.cookies import cookie_name, issue_cookie
from backend.api.invitations import InviteLinks
from backend.api.schemas import (
    Answer,
    Command,
    Continue,
    Controller,
    Create,
    Failure,
    Identity,
    Preload,
    Ready,
    Recovery,
    Settings,
    SongSelection,
    Start,
    UpcomingReady,
)


def create_router(coordinator, limits, room_commands, game_commands):
    router = APIRouter(prefix="/api")
    c = coordinator
    invitations = InviteLinks(c.config.public_url, c.config.port)

    rooms, games = room_commands, game_commands

    def credential(request, room_id):
        return request.cookies.get(cookie_name(room_id))

    @router.post("/rooms", status_code=201)
    def create(payload: Create, request: Request, response: Response):
        limits.check("create", request.client.host, c.clock())
        result = rooms.create(payload.model_dump())
        issue_cookie(response, c.config, result, c.clock())
        return rooms.admission_result(result)

    @router.get("/room-codes/{code}")
    def resolve(code: str):
        return rooms.resolve(code)

    @router.get("/room-codes/{code}/history")
    def history(code: str):
        return rooms.history(code)

    @router.post("/rooms/{room_id}/join", status_code=201)
    def join(room_id: str, payload: Identity, request: Request, response: Response):
        limits.check("join", request.client.host, c.clock())
        result, admission = rooms.join(
            room_id, credential(request, room_id), payload.model_dump()
        )
        if admission:
            issue_cookie(response, c.config, admission, c.clock())
        return result

    @router.get("/rooms/{room_id}/state")
    def state(room_id: str, request: Request, response: Response):
        result = rooms.state(room_id, credential(request, room_id))
        result["room"]["invite_url"] = invitations.for_room(
            str(request.base_url), result["room"]["code"]
        )
        # Renew cookie only up to the existing server-side retention anchor.
        token = request.cookies.get(cookie_name(room_id))
        response.set_cookie(
            cookie_name(room_id),
            token,
            max_age=max(0, (result["room"]["expires_at_ms"] - c.clock()) // 1000),
            path="/api/rooms/" + room_id,
            httponly=True,
            secure=c.config.cookie_secure,
            samesite="lax",
        )
        return result

    @router.get("/rooms/{room_id}/song-search")
    def song_search_results(
        room_id: str, q: str, request: Request, local: bool = False
    ):
        return rooms.search_songs(
            room_id, credential(request, room_id), q, local_first=local
        )

    @router.post("/rooms/{room_id}/song-selection")
    def resolve_song_selection(room_id: str, payload: SongSelection, request: Request):
        return rooms.resolve_selection(
            room_id, credential(request, room_id), payload.token
        )

    @router.post("/rooms/{room_id}/heartbeat")
    def heartbeat(room_id: str, request: Request):
        return rooms.heartbeat(room_id, credential(request, room_id))

    @router.patch("/rooms/{room_id}/player")
    def player(room_id: str, payload: Identity, request: Request):
        return rooms.update_player(
            room_id, credential(request, room_id), payload.model_dump()
        )

    @router.patch("/rooms/{room_id}/settings")
    def settings(room_id: str, payload: Settings, request: Request):
        return rooms.settings(
            room_id,
            credential(request, room_id),
            payload.model_dump(exclude_unset=True),
        )

    @router.post("/rooms/{room_id}/start")
    def start(room_id: str, payload: Start, request: Request):
        return games.start(room_id, credential(request, room_id), payload.model_dump())

    @router.post("/rooms/{room_id}/audio-controller")
    def audio_controller(room_id: str, payload: Controller, request: Request):
        return games.claim_audio(
            room_id, credential(request, room_id), payload.model_dump()
        )

    @router.get("/rooms/{room_id}/games/{game_id}/audio")
    def audio(room_id: str, game_id: str, request: Request):
        return games.audio(
            room_id,
            credential(request, room_id),
            game_id,
            request.headers.get("X-Audio-Lease"),
        )

    @router.post("/rooms/{room_id}/games/{game_id}/preload-check")
    def preload(room_id: str, game_id: str, payload: Preload, request: Request):
        return games.preload(
            room_id, credential(request, room_id), game_id, payload.model_dump()
        )

    @router.post("/rooms/{room_id}/games/{game_id}/end")
    def end(room_id: str, game_id: str, payload: Command, request: Request):
        return games.end(
            room_id, credential(request, room_id), game_id, payload.model_dump()
        )

    @router.post("/rooms/{room_id}/games/{game_id}/preparations/{preparation_id}/ready")
    def prepare_upcoming(
        room_id: str,
        game_id: str,
        preparation_id: str,
        payload: UpcomingReady,
        request: Request,
    ):
        return games.prepare_upcoming(
            room_id,
            credential(request, room_id),
            game_id,
            preparation_id,
            payload.model_dump(),
        )

    @router.post("/rooms/{room_id}/games/{game_id}/rounds/{round_id}/ready")
    def ready(
        room_id: str, game_id: str, round_id: str, payload: Ready, request: Request
    ):
        return games.ready(
            room_id,
            credential(request, room_id),
            game_id,
            round_id,
            payload.model_dump(),
        )

    @router.post("/rooms/{room_id}/games/{game_id}/rounds/{round_id}/answers")
    def answer(
        room_id: str, game_id: str, round_id: str, payload: Answer, request: Request
    ):
        return games.answer(
            room_id,
            credential(request, room_id),
            game_id,
            round_id,
            payload.model_dump(),
        )

    @router.post("/rooms/{room_id}/games/{game_id}/rounds/{round_id}/retry")
    def retry(
        room_id: str, game_id: str, round_id: str, payload: Recovery, request: Request
    ):
        return games.recover(
            room_id,
            credential(request, room_id),
            game_id,
            round_id,
            payload.model_dump(),
            "retry",
        )

    @router.post("/rooms/{room_id}/games/{game_id}/rounds/{round_id}/continue")
    def proceed(
        room_id: str, game_id: str, round_id: str, payload: Continue, request: Request
    ):
        return games.recover(
            room_id,
            credential(request, room_id),
            game_id,
            round_id,
            payload.model_dump(),
            "continue",
        )

    @router.post("/rooms/{room_id}/games/{game_id}/rounds/{round_id}/audio-failure")
    def failure(
        room_id: str, game_id: str, round_id: str, payload: Failure, request: Request
    ):
        return games.audio_failure(
            room_id,
            credential(request, room_id),
            game_id,
            round_id,
            payload.model_dump(),
        )

    @router.post("/rooms/{room_id}/leave")
    def leave(room_id: str, payload: Command, request: Request):
        return rooms.leave(room_id, credential(request, room_id), payload.model_dump())

    return router
