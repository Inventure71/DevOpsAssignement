"""FastAPI composition root: dependency wiring, lifecycle and static delivery."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api.rate_limits import AdmissionLimits
from backend.api.routes import create_router
from backend.api.music import create_music_router
from backend.api.security import check_origin
from backend.application.coordinator import Coordinator
from backend.application.music_admission import MusicAdmissionHandler
from backend.catalog.search import SongSearch
from backend.catalog.store import CatalogStore
from backend.core.config import Config
from backend.core.errors import DomainError
from backend.core.paths import DEMO_ASSETS_DIR, FRONTEND_DIR
from backend.music.admissions import MusicAdmissions
from backend.music.apple import AppleCatalog
from backend.music.importer import MusicImporter
from backend.music.previews import PreviewResolver
from backend.music.spotify import SpotifyClient

logger = logging.getLogger(__name__)


def error_response(exc):
    retry = exc.details.get('retry_after_seconds')
    headers = {'Retry-After': str(retry)} if exc.status == 429 and isinstance(retry, int) and retry > 0 else None
    return JSONResponse(
        {'error': {
            'code': exc.code,
            'message': exc.message,
            'details': exc.details,
            'retryable': exc.status in (429, 503),
        }},
        status_code=exc.status,
        headers=headers,
    )


def create_app(config=None, clock=None, game=None, background=True, song_search=None,
               spotify_client=None, apple_catalog=None, music_importer=None):
    config = config or Config.from_env()
    kwargs = {'game': game}
    if clock:
        kwargs['clock'] = clock
    coordinator = Coordinator(config, **kwargs)
    spotify = spotify_client or SpotifyClient(config.spotify_client_id, config.spotify_client_secret,
                                             config.spotify_redirect_uri)
    apple = apple_catalog or AppleCatalog(config.apple_team_id, config.apple_key_id,
                                         config.apple_private_key_path, config.apple_storefront)
    catalog_store = CatalogStore(config.data_dir / 'catalog.sqlite3')
    song_search = song_search or (SongSearch(apple.search, calls_per_minute=60,
                                           provider_scope='apple:' + getattr(apple, 'storefront', config.apple_storefront))
                                  if apple.configured else SongSearch(provider_scope='itunes:us'))
    if song_search.store is None:
        song_search.store = catalog_store
    importer = music_importer or MusicImporter(spotify, PreviewResolver(apple=apple, store=catalog_store),
                                               decoy_provider=apple.decoys)

    admissions = MusicAdmissions(spotify, importer, MusicAdmissionHandler(coordinator),
                                 enabled=bool(spotify.configured and apple.configured))

    @asynccontextmanager
    async def lifespan(application):
        await asyncio.to_thread(catalog_store.initialize, seed=True)
        await asyncio.to_thread(coordinator.initialize)
        application.state.ready = True

        async def runtime():
            iteration = 0
            while True:
                await asyncio.sleep(1)
                try:
                    await asyncio.to_thread(coordinator.tick)
                    iteration += 1
                    if iteration % 60 == 0:
                        await asyncio.to_thread(coordinator.cleanup)
                except Exception:
                    application.state.ready = False
                    logger.exception('Runtime transition failed')
                    raise

        task = asyncio.create_task(runtime()) if background else None
        try:
            yield
        finally:
            application.state.ready = False
            admissions.close()
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            # Live games are intentionally reconciled on the next startup.

    application = FastAPI(title="Who's On Repeat", lifespan=lifespan)
    application.state.coordinator = coordinator
    application.state.song_search = song_search
    application.state.catalog_store = catalog_store
    application.state.music_admissions = admissions
    application.state.ready = False

    @application.middleware('http')
    async def boundary(request: Request, call_next):
        try:
            check_origin(request)
        except DomainError as exc:
            return error_response(exc)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Cache-Control'] = 'no-store' if request.url.path.startswith('/api/') else 'no-cache'
        return response

    @application.exception_handler(DomainError)
    async def domain_error(request, exc):
        return error_response(exc)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error_response(DomainError(
            'invalid_request',
            'Check the request fields.',
            422,
            {'fields': [list(item['loc']) for item in exc.errors()]},
        ))

    @application.get('/health/live')
    def live():
        return {'status': 'live'}

    @application.get('/health/ready')
    def ready():
        if not application.state.ready:
            return JSONResponse({'status': 'not_ready'}, status_code=503)
        with coordinator.db.read() as conn:
            conn.execute('SELECT id FROM rooms LIMIT 1').fetchone()
        return {'status': 'ready'}

    @application.get('/', include_in_schema=False)
    def frontend():
        return FileResponse(FRONTEND_DIR / 'index.html')

    @application.get('/ui-lab', include_in_schema=False)
    def ui_lab():
        return FileResponse(FRONTEND_DIR / 'lab.html')

    limits = AdmissionLimits(
        int(os.environ.get('ROOM_CREATE_LIMIT', '10')),
        int(os.environ.get('ROOM_JOIN_LIMIT', '30')),
    )
    application.include_router(create_router(coordinator, limits, song_search))
    application.include_router(create_music_router(coordinator, admissions, limits, search_provider=song_search.provider_name))
    application.mount('/static/demo', StaticFiles(directory=DEMO_ASSETS_DIR), name='demo-assets')
    application.mount('/ui', StaticFiles(directory=FRONTEND_DIR), name='frontend')
    return application


app = create_app()
