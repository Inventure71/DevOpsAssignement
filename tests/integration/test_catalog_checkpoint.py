"""Exercise the actual bundled checkpoint, independently of large test pools."""

import json

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core.config import Config
from backend.core.paths import DEMO_ASSETS_DIR, FRONTEND_DIR
from backend.storage.database import Database
from backend.rooms.demo import CATALOG_PATH, seed_demo
from backend.rooms.service import RoomsService
from tests.support.catalog import write_large_catalog


def test_four_song_app_boots_serves_assets_and_preserves_start_requirement(tmp_path):
    app = create_app(Config(tmp_path), clock=lambda: 1000, background=False)
    with TestClient(app) as host, TestClient(app) as ada, TestClient(app) as grace:
        assert host.get('/health/ready').status_code == 200
        response = host.post('/api/rooms', json={'nickname': 'Host', 'mode': 'demo'})
        assert response.status_code == 201
        prefix = '/api/rooms/' + response.json()['room_id']
        for client, nickname in ((ada, 'Ada'), (grace, 'Grace')):
            assert client.post(prefix + '/join', json={'nickname': nickname}).status_code == 201
        state = host.get(prefix + '/state').json()
        assert [p['song_count'] for p in state['players']] == [4, 4, 4]
        assert state['game'] is None
        with app.state.coordinator.db.read() as conn:
            entries = list(conn.execute('SELECT * FROM demo_catalog ORDER BY id'))
            assert len(entries) == 4
            assert all(entry['title'].startswith('Fake Song ') for entry in entries)
            assert all(entry['pool_kind'] == 'personal' for entry in entries)
            for entry in entries:
                clip = host.get(entry['preview_url'])
                assert clip.status_code == 200 and len(clip.content) > 1000
                if entry['artwork_url']:
                    assert host.get(entry['artwork_url']).status_code == 200
        lease = host.post(prefix + '/audio-controller', json={'tab_id': 'host'}).json()['lease_id']
        started = host.post(prefix + '/start', json={
            'request_id': 'small-catalog', 'room_revision': state['room']['revision'], 'lease_id': lease})
        assert started.status_code == 400
        assert started.json()['error']['code'] == 'insufficient_songs'
        assert host.get(prefix + '/state').json()['room']['state'] == 'lobby'
        with app.state.coordinator.db.read() as conn:
            assert conn.execute('SELECT COUNT(*) FROM games').fetchone()[0] == 0


def test_reseed_removes_retired_catalog_but_preserves_room_copies_and_snapshot(tmp_path):
    db = Database(tmp_path / 'state.sqlite3')
    db.initialize()
    rooms = RoomsService()
    with db.transaction() as conn:
        seed_demo(conn, write_large_catalog(tmp_path / 'large.json'))
        old = rooms.create(conn, 'Old Host', 'coral', 'demo', 1000)
        frozen = rooms.snapshot(conn, old['room']['id'])
        old_ids = {s['song_key'] for s in frozen['songs'] if s['listeners']}
        seed_demo(conn, CATALOG_PATH)
        seed_demo(conn, CATALOG_PATH)
        assert conn.execute('SELECT COUNT(*) FROM demo_catalog').fetchone()[0] == 4
        assert {row[0] for row in conn.execute('SELECT id FROM songs WHERE room_id=?',
                                            (old['room']['id'],))} == old_ids
        assert len(frozen['songs']) == 60  # 36 room songs + 24 frozen decoys.
        new = rooms.create(conn, 'New Host', 'coral', 'demo', 1000)
        assert rooms.lobby(conn, new['room']['id'], 1000)['players'][0]['song_count'] == 4
        assert len(rooms.snapshot(conn, new['room']['id'])['songs']) == 4
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('entries', [[], [{'id': 'invalid'}]])
def test_invalid_catalog_keeps_previously_seeded_entries(tmp_path, entries):
    db = Database(tmp_path / 'state.sqlite3')
    db.initialize()
    invalid = tmp_path / 'invalid.json'
    invalid.write_text(json.dumps(entries))
    with db.transaction() as conn:
        seed_demo(conn, CATALOG_PATH)
        with pytest.raises(ValueError):
            seed_demo(conn, invalid)
        assert conn.execute('SELECT COUNT(*) FROM demo_catalog').fetchone()[0] == 4


def test_bundled_catalog_has_exactly_four_clips_and_no_retired_covers():
    entries = json.loads(CATALOG_PATH.read_text())
    assert len(entries) == 4
    paths = {DEMO_ASSETS_DIR / entry['preview_url'].removeprefix('/static/demo/') for entry in entries}
    assert paths == set((DEMO_ASSETS_DIR / 'clips').glob('*.mp3'))
    covers = {DEMO_ASSETS_DIR / entry['artwork_url'].removeprefix('/static/demo/')
              for entry in entries if entry['artwork_url']}
    assert covers == set((DEMO_ASSETS_DIR / 'covers').glob('*.svg'))


def test_app_resources_work_when_started_outside_checkout(tmp_path, monkeypatch):
    data_dir = (tmp_path / 'runtime').resolve()
    monkeypatch.chdir(tmp_path)
    app = create_app(Config(data_dir), clock=lambda: 1000, background=False)
    with TestClient(app) as client:
        assert client.get('/health/ready').status_code == 200
        assert client.get('/').status_code == 200
        assert client.get('/docs').status_code == 200
        schema = client.get('/openapi.json')
        assert schema.status_code == 200
        assert '/api/rooms' in schema.json()['paths']
        assert client.get('/static/js/app.js').status_code == 404
        assert client.get('/static/demo/%2e%2e/demo_catalog.json').status_code == 404
        # Native module URLs must work on the API origin without a bundler,
        # regardless of cwd, with a MIME type browsers permit for module imports.
        for module in FRONTEND_DIR.rglob('*.mjs'):
            response = client.get('/ui/' + module.relative_to(FRONTEND_DIR).as_posix())
            assert response.status_code == 200
            assert response.headers['content-type'].split(';')[0] in {
                'text/javascript', 'application/javascript',
            }
            assert response.content == module.read_bytes()
        with app.state.coordinator.db.read() as conn:
            # Startup must find and apply the real migration and catalog files.
            assert conn.execute('PRAGMA user_version').fetchone()[0] == 3
            songs = list(conn.execute('SELECT preview_url, artwork_url FROM demo_catalog'))
            assert len(songs) == 4
        for song in songs:
            assert client.get(song['preview_url']).status_code == 200
            if song['artwork_url']:
                assert client.get(song['artwork_url']).status_code == 200
    assert (data_dir / 'whos_on_repeat.sqlite3').is_file()
