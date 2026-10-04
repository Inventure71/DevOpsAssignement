"""Provider-neutral admission HTTP; provider callbacks remain separate boundaries."""

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse

from backend.api.cookies import issue_cookie
from backend.api.schemas import MusicAcknowledgement, MusicAdmission
from backend.core.errors import DomainError
from backend.music.admissions import LIFETIME_SECONDS

COOKIE = "repeat_music_admission"
COOKIE_PATH = "/api/music"


def create_music_router(coordinator, admissions, limits, *, room_commands):
    router = APIRouter(prefix=COOKIE_PATH)
    c = coordinator

    def receipt_cookie(response, credential):
        response.set_cookie(
            COOKIE,
            credential,
            max_age=LIFETIME_SECONDS,
            path=COOKIE_PATH,
            httponly=True,
            secure=c.config.cookie_secure,
            samesite="lax",
        )

    def deliver(result, admission, request, response):
        if admission and not room_commands.music_session_valid(admission):
            # The browser may have left after a failed acknowledgement. An old
            # completed receipt must not restore a departed or expired identity.
            admissions.acknowledge(request.cookies.get(COOKIE), result["admission_id"])
            response.delete_cookie(
                COOKIE,
                path=COOKIE_PATH,
                httponly=True,
                secure=c.config.cookie_secure,
                samesite="lax",
            )
            return {"status": "cancelled"}
        if admission:
            issue_cookie(response, c.config, admission, c.clock())
            result["admission"] = room_commands.admission_result(admission)
        return result

    @router.get("/config")
    def config(request: Request):
        providers = admissions.configuration(str(request.base_url))
        # Show deferred Apple personal listening in provider choices.
        providers.setdefault(
            "apple",
            {
                "id": "apple",
                "label": "Apple Music",
                "enabled": False,
                "reason": "Coming later",
            },
        )
        return {"providers": providers}

    @router.post("/admissions")
    def begin(payload: MusicAdmission, request: Request, response: Response):
        c.launch_mode.require("normal")
        limits.check(
            "join" if payload.room_id else "create", request.client.host, c.clock()
        )
        admissions.require_provider(payload.provider)
        room_commands.check_music_admission(payload.model_dump())
        credential, action = admissions.begin(
            payload.model_dump(),
            request.cookies.get(COOKIE),
            origin=str(request.base_url),
        )
        receipt_cookie(response, credential)
        return {"authorization": action}

    @router.get("/spotify/callback")
    def spotify_callback(
        request: Request,
        state: str = Query(default="", max_length=128),
        code: str | None = Query(default=None, max_length=2048),
        error: str | None = Query(default=None, max_length=128),
    ):
        try:
            admissions.callback(
                request.cookies.get(COOKIE),
                "spotify",
                {"state": state, "code": code, "error": error},
            )
        except DomainError:
            # Never echo provider errors or credentials into the destination URL.
            return RedirectResponse("/?music=error", status_code=303)
        return RedirectResponse("/?music=processing", status_code=303)

    @router.get("/status")
    def status(request: Request, response: Response):
        result, admission = admissions.status(request.cookies.get(COOKIE))
        receipt_cookie(response, request.cookies[COOKIE])
        return deliver(result, admission, request, response)

    @router.post("/cancel")
    def cancel(request: Request, response: Response):
        result, admission = admissions.cancel(request.cookies.get(COOKIE))
        if admission:
            # Completion won the race: recover the actual room session rather
            # than discard its only credential and leave an invisible member.
            receipt_cookie(response, request.cookies[COOKIE])
        else:
            response.delete_cookie(
                COOKIE,
                path=COOKIE_PATH,
                httponly=True,
                secure=c.config.cookie_secure,
                samesite="lax",
            )
        return deliver(result, admission, request, response)

    @router.post("/acknowledge")
    def acknowledge(payload: MusicAcknowledgement, request: Request):
        acknowledged = admissions.acknowledge(
            request.cookies.get(COOKIE), payload.admission_id
        )
        # A delayed response must not clear a newer connection's shared cookie.
        # The next begin replaces the cookie whose retired receipt no longer exists.
        return {"acknowledged": acknowledged}

    return router
