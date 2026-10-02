"""HTTP boundary for pre-membership music authorization and admission receipts."""
from urllib.parse import urlsplit

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse

from backend.api.cookies import issue_cookie
from backend.api.schemas import MusicAdmission
from backend.core.errors import DomainError
from backend.music.admissions import LIFETIME_SECONDS

COOKIE = 'repeat_music_admission'
COOKIE_PATH = '/api/music/spotify'


def create_music_router(coordinator, admissions, limits, *, search_provider):
    router = APIRouter(prefix=COOKIE_PATH)
    c = coordinator
    callback = urlsplit(c.config.spotify_redirect_uri)
    application_url = f'{callback.scheme}://{callback.netloc}/'

    @router.get('/config')
    def config():
        return {'enabled': admissions.enabled, 'maximum_players': 5,
                'application_url': application_url, 'search_provider': search_provider}

    @router.post('/admissions')
    def begin(payload: MusicAdmission, request: Request, response: Response):
        limits.check('join' if payload.room_id else 'create', request.client.host, c.clock())
        if callback.path != COOKIE_PATH + '/callback':
            raise DomainError('music_callback_misconfigured', 'The configured Spotify callback must end in /api/music/spotify/callback.', 503)
        if str(request.base_url).rstrip('/') != application_url.rstrip('/'):
            raise DomainError('music_origin_mismatch', 'Open the configured game address before Spotify sign-in.', 409,
                              {'application_url': application_url})
        with c.db.read() as conn:
            room = c.rooms.check_admission(conn, payload.nickname, payload.character_id, c.clock(), room_id=payload.room_id)
            if room and room['mode'] != 'normal':
                raise DomainError('invalid_music_room', 'Demo rooms do not require Spotify sign-in.', 409)
        credential, authorization_url = admissions.begin(payload.model_dump(), request.cookies.get(COOKIE))
        response.set_cookie(COOKIE, credential, max_age=LIFETIME_SECONDS, path=COOKIE_PATH,
                            httponly=True, secure=c.config.cookie_secure, samesite='lax')
        return {'authorization_url': authorization_url}

    @router.get('/callback')
    def callback_route(request: Request, state: str = Query(default='', max_length=128),
                       code: str | None = Query(default=None, max_length=2048),
                       error: str | None = Query(default=None, max_length=128)):
        try:
            admissions.callback(request.cookies.get(COOKIE), state, code, error)
        except DomainError:
            # Never echo provider errors or codes into the destination URL.
            return RedirectResponse('/?spotify=error', status_code=303)
        return RedirectResponse('/?spotify=processing', status_code=303)

    @router.get('/status')
    def status(request: Request, response: Response):
        result, admission = admissions.status(request.cookies.get(COOKIE))
        response.set_cookie(COOKIE, request.cookies[COOKIE], max_age=LIFETIME_SECONDS, path=COOKIE_PATH,
                            httponly=True, secure=c.config.cookie_secure, samesite='lax')
        if admission:
            issue_cookie(response, c.config, admission, c.clock())
            result['admission'] = {'room_id': admission['room']['id'], 'code': admission['room']['code'],
                                   'player_id': admission['player']['id']}
        return result

    @router.post('/cancel')
    def cancel(request: Request, response: Response):
        admissions.cancel(request.cookies.get(COOKIE))
        response.delete_cookie(COOKIE, path=COOKIE_PATH, httponly=True,
                               secure=c.config.cookie_secure, samesite='lax')
        return {'cancelled': True}

    return router
