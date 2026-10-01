"""Map validated HTTP commands to application and domain services."""
from fastapi import APIRouter, Request, Response
from backend.catalog.search import SongSearch

from backend.api.cookies import cookie_name, issue_cookie
from backend.api.schemas import (
    Answer, Command, Continue, Controller, Create, Failure, Identity,
    Preload, Ready, Recovery, Settings, Start,
)
from backend.core.errors import DomainError


def create_router(coordinator, limits, song_search=None):
    router = APIRouter(prefix='/api')
    c = coordinator
    search = song_search or SongSearch()

    def run(request, room_id, operation, write=True):
        return c.execute(room_id, request.cookies.get(cookie_name(room_id)), operation, write)

    def admission_result(result):
        return {'room_id': result['room']['id'], 'code': result['room']['code'], 'player_id': result['player']['id']}

    @router.post('/rooms', status_code=201)
    def create(payload: Create, request: Request, response: Response):
        limits.check('create', request.client.host, c.clock())
        result = c.admission(lambda conn, now: c.rooms.create(conn, payload.nickname, payload.character_id, payload.mode, now))
        issue_cookie(response, c.config, result, c.clock())
        return admission_result(result)

    @router.get('/room-codes/{code}')
    def resolve(code: str):
        with c.db.read() as conn:
            return c.rooms.resolve_code(conn, code, c.clock())

    @router.get('/room-codes/{code}/history')
    def history(code: str):
        with c.db.read() as conn:
            room = c.rooms.resolve_code(conn, code, c.clock())
            return {'games': c.game.repo.history(conn, room['room_id'])}

    @router.post('/rooms/{room_id}/join', status_code=201)
    def join(room_id: str, payload: Identity, request: Request, response: Response):
        limits.check('join', request.client.host, c.clock())
        token = request.cookies.get(cookie_name(room_id))
        if token:
            try:
                player = run(request, room_id, lambda conn, actor, now: {'player_id': actor['id']}, False)
                with c.db.read() as conn:
                    room = c.rooms.room(conn, room_id, c.clock())
                return {'room_id': room_id, 'code': room['code'], **player}
            except DomainError as exc:
                if exc.code != 'unauthorized':
                    raise
        with c.room_lock(room_id):
            result = c.admission(lambda conn, now: c.rooms.join(conn, room_id, payload.nickname, payload.character_id, now))
        issue_cookie(response, c.config, result, c.clock())
        return admission_result(result)

    @router.get('/rooms/{room_id}/state')
    def state(room_id: str, request: Request, response: Response):
        result = run(request, room_id, lambda conn, player, now: c.state(conn, room_id, player, now), False)
        # Renew cookie only up to the existing server-side retention anchor.
        token = request.cookies.get(cookie_name(room_id))
        response.set_cookie(cookie_name(room_id), token,
            max_age=max(0, (result['room']['expires_at_ms'] - c.clock()) // 1000),
            path='/api/rooms/' + room_id, httponly=True, secure=c.config.cookie_secure, samesite='lax')
        return result

    @router.get('/rooms/{room_id}/song-search')
    def song_search_results(room_id: str, q: str, request: Request):
        run(request, room_id, lambda conn, player, now: None, False)
        # Authenticate before searching. Provider I/O never holds the room lock.
        with c.db.read() as conn:
            return search.search(conn, room_id, q, c.clock())

    @router.post('/rooms/{room_id}/heartbeat')
    def heartbeat(room_id: str, request: Request):
        def operation(conn, player, now):
            c.rooms.heartbeat(conn, room_id, player['id'], now)
            return {'accepted': True, 'server_now_ms': now}
        return run(request, room_id, operation)

    @router.patch('/rooms/{room_id}/player')
    def player(room_id: str, payload: Identity, request: Request):
        def operation(conn, actor, now):
            updated = c.rooms.update_player(conn, room_id, actor['id'], payload.nickname, payload.character_id, now)
            return {k: updated[k] for k in ('id', 'nickname', 'character_id')}
        return run(request, room_id, operation)

    @router.patch('/rooms/{room_id}/settings')
    def settings(room_id: str, payload: Settings, request: Request):
        return run(request, room_id, lambda conn, player, now: c.change_settings(conn, room_id, player, payload.model_dump(exclude_unset=True), now))

    @router.post('/rooms/{room_id}/start')
    def start(room_id: str, payload: Start, request: Request):
        return run(request, room_id, lambda conn, player, now: c.start(conn, room_id, player, payload.model_dump(), now))

    @router.post('/rooms/{room_id}/audio-controller')
    def audio_controller(room_id: str, payload: Controller, request: Request):
        return run(request, room_id, lambda conn, player, now: c.claim_audio(conn, room_id, player, payload.model_dump(), now))

    @router.get('/rooms/{room_id}/games/{game_id}/audio')
    def audio(room_id: str, game_id: str, request: Request):
        return run(request, room_id, lambda conn, player, now: c.audio(conn, room_id, game_id, player, request.headers.get('X-Audio-Lease'), now), False)

    @router.post('/rooms/{room_id}/games/{game_id}/preload-check')
    def preload(room_id: str, game_id: str, payload: Preload, request: Request):
        def operation(conn, player, now):
            c.validate_game_room(conn, room_id, game_id)
            c.require_audio(room_id, player, payload.lease_id, now)
            return c.game.preload(conn, game_id, player['id'], payload.model_dump(), now)
        return run(request, room_id, operation)

    @router.post('/rooms/{room_id}/games/{game_id}/end')
    def end(room_id: str, game_id: str, payload: Command, request: Request):
        def operation(conn, player, now):
            c.validate_game_room(conn, room_id, game_id)
            return c.game.end(conn, game_id, player['id'], payload.model_dump(), now)
        return run(request, room_id, operation)

    @router.post('/rooms/{room_id}/games/{game_id}/rounds/{round_id}/ready')
    def ready(room_id: str, game_id: str, round_id: str, payload: Ready, request: Request):
        def operation(conn, player, now):
            c.validate_game_room(conn, room_id, game_id)
            if player['is_host']:
                c.require_audio(room_id, player, payload.lease_id, now)
            return c.game.ready(conn, game_id, round_id, player['id'], payload.readiness_generation, now, c.rooms.host_presence(conn, room_id, now)['connected'])
        return run(request, room_id, operation)

    @router.post('/rooms/{room_id}/games/{game_id}/rounds/{round_id}/answers')
    def answer(room_id: str, game_id: str, round_id: str, payload: Answer, request: Request):
        def operation(conn, player, now):
            c.validate_game_room(conn, room_id, game_id)
            values = {'song_guess': None, 'who_player_ids': payload.who_player_ids}
            if payload.song_guess_token is not None:
                values['song_guess'], values['_token_expires_ms'] = search.tokens.decode(payload.song_guess_token, room_id)
            return c.game.answer(conn, game_id, round_id, player['id'], values, now)
        return run(request, room_id, operation)

    def recover(room_id, game_id, round_id, payload, request, kind):
        def operation(conn, player, now):
            c.validate_game_room(conn, room_id, game_id)
            return c.game.readiness_command(conn, game_id, round_id, player['id'], kind, payload.model_dump(), now)
        return run(request, room_id, operation)

    @router.post('/rooms/{room_id}/games/{game_id}/rounds/{round_id}/retry')
    def retry(room_id: str, game_id: str, round_id: str, payload: Recovery, request: Request):
        return recover(room_id, game_id, round_id, payload, request, 'retry')

    @router.post('/rooms/{room_id}/games/{game_id}/rounds/{round_id}/continue')
    def proceed(room_id: str, game_id: str, round_id: str, payload: Continue, request: Request):
        return recover(room_id, game_id, round_id, payload, request, 'continue')

    @router.post('/rooms/{room_id}/games/{game_id}/rounds/{round_id}/audio-failure')
    def failure(room_id: str, game_id: str, round_id: str, payload: Failure, request: Request):
        def operation(conn, player, now):
            c.validate_game_room(conn, room_id, game_id)
            c.require_audio(room_id, player, payload.lease_id, now)
            return c.game.audio_failure(conn, game_id, round_id, player['id'], payload.model_dump(), now)
        return run(request, room_id, operation)

    @router.post('/rooms/{room_id}/leave')
    def leave(room_id: str, payload: Command, request: Request):
        return run(request, room_id, lambda conn, player, now: c.leave(conn, room_id, player, payload.model_dump(), now))

    return router
