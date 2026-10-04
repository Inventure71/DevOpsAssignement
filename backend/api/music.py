"""HTTP boundary for pre-membership music authorization and admission receipts."""

from urllib.parse import urlsplit

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse

from backend.api.cookies import issue_cookie
from backend.api.invitations import is_local_only
from backend.api.schemas import MusicAdmission
from backend.core.errors import DomainError
from backend.music.admissions import LIFETIME_SECONDS

COOKIE = "repeat_music_admission"
COOKIE_PATH = "/api/music/spotify"


def create_music_router(
    coordinator, admissions, limits, *, search_provider, room_commands
):
    router = APIRouter(prefix=COOKIE_PATH)
    c = coordinator
    callback = urlsplit(c.config.spotify_redirect_uri)
    application_url = f"{callback.scheme}://{callback.netloc}/"

    def requires_shared_url(request):
        return is_local_only(callback.hostname) and not is_local_only(
            request.url.hostname
        )

    @router.get("/config")
    def config(request: Request):
        return {
            "enabled": admissions.enabled,
            "maximum_players": 5,
            "playtest": c.config.playtest,
            "minimum_players": c.rooms.minimum_players,
            "application_url": application_url,
            "search_provider": search_provider,
            "requires_shared_url": requires_shared_url(request),
        }

    @router.post("/admissions")
    def begin(payload: MusicAdmission, request: Request, response: Response):
        c.launch_mode.require("normal")
        limits.check(
            "join" if payload.room_id else "create", request.client.host, c.clock()
        )
        if callback.path != COOKIE_PATH + "/callback":
            raise DomainError(
                "music_callback_misconfigured",
                "The configured Spotify callback must end in /api/music/spotify/callback.",
                503,
            )
        if requires_shared_url(request):
            raise DomainError(
                "music_shared_url_required",
                "Spotify is configured for the server computer only. The host must finish network setup before other devices can sign in.",
                503,
            )
        if str(request.base_url).rstrip("/") != application_url.rstrip("/"):
            raise DomainError(
                "music_origin_mismatch",
                "Open the configured game address before Spotify sign-in.",
                409,
                {"application_url": application_url},
            )
        room_commands.check_music_admission(payload.model_dump())
        credential, authorization_url = admissions.begin(
            payload.model_dump(), request.cookies.get(COOKIE)
        )
        response.set_cookie(
            COOKIE,
            credential,
            max_age=LIFETIME_SECONDS,
            path=COOKIE_PATH,
            httponly=True,
            secure=c.config.cookie_secure,
            samesite="lax",
        )
        return {"authorization_url": authorization_url}

    @router.get("/callback")
    def callback_route(
        request: Request,
        state: str = Query(default="", max_length=128),
        code: str | None = Query(default=None, max_length=2048),
        error: str | None = Query(default=None, max_length=128),
    ):
        try:
            admissions.callback(request.cookies.get(COOKIE), state, code, error)
        except DomainError:
            # Never echo provider errors or codes into the destination URL.
            return RedirectResponse("/?spotify=error", status_code=303)
        return RedirectResponse("/?spotify=processing", status_code=303)

    @router.get("/status")
    def status(request: Request, response: Response):
        result, admission = admissions.status(request.cookies.get(COOKIE))
        response.set_cookie(
            COOKIE,
            request.cookies[COOKIE],
            max_age=LIFETIME_SECONDS,
            path=COOKIE_PATH,
            httponly=True,
            secure=c.config.cookie_secure,
            samesite="lax",
        )
        if admission:
            issue_cookie(response, c.config, admission, c.clock())
            result["admission"] = {
                "room_id": admission["room"]["id"],
                "code": admission["room"]["code"],
                "player_id": admission["player"]["id"],
            }
        return result

    @router.post("/cancel")
    def cancel(request: Request, response: Response):
        admissions.cancel(request.cookies.get(COOKIE))
        response.delete_cookie(
            COOKIE,
            path=COOKIE_PATH,
            httponly=True,
            secure=c.config.cookie_secure,
            samesite="lax",
        )
        return {"cancelled": True}

    return router
