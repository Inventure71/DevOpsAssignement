"""Real HTTP/SQLite integration: identity, command ordering and phase secrecy."""
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core.config import Config
from tests.support.catalog import write_large_catalog


class Clock:
    def __init__(self):
        self.value = 1_000_000
    def __call__(self):
        return self.value


@pytest.fixture
def session(tmp_path, monkeypatch):
    clock = Clock()
    monkeypatch.setattr("backend.rooms.demo.CATALOG_PATH", write_large_catalog(tmp_path / "test_catalog.json"))
    app = create_app(Config(tmp_path), clock=clock, background=False)
    with TestClient(app) as host:
        guests = [TestClient(app), TestClient(app)]
        room = host.post('/api/rooms', json={'nickname': 'Host', 'character_id': 'vinyl', 'mode': 'demo'}).json()
        prefix = '/api/rooms/' + room['room_id']
        for name, client in zip(('Ada', 'Grace'), guests):
            assert client.post(prefix + '/join', json={'nickname': name, 'character_id': 'moon'}).status_code == 201
        lease = host.post(prefix + '/audio-controller', json={'tab_id': 'host'}).json()['lease_id']
        yield app.state.coordinator, clock, host, guests, room, prefix, lease
        for guest in guests:
            guest.close()


def start(session):
    c, clock, host, guests, room, prefix, lease = session
    state = host.get(prefix + '/state').json()
    payload = {'request_id': str(uuid4()), 'room_revision': state['room']['revision'], 'lease_id': lease}
    response = host.post(prefix + '/start', json=payload)
    assert response.status_code == 200, response.text
    gid = response.json()['game_id']
    manifest = host.get(prefix + f'/games/{gid}/audio', headers={'X-Audio-Lease': lease}).json()
    for candidate in manifest['candidates']:
        response = host.post(prefix + f'/games/{gid}/preload-check', json={'request_id': str(uuid4()),
            'lease_id': lease, 'candidate_id': candidate['candidate_id'], 'ok': True})
        assert response.status_code == 200, response.text
    clock.value += 5000
    c.tick()
    current = host.get(prefix + '/state').json()['game']['round']
    for client in [host, *guests]:
        response = client.post(prefix + f'/games/{gid}/rounds/{current["id"]}/ready',
            json={'readiness_generation': current['readiness_generation'], 'lease_id': lease if client is host else None})
        assert response.status_code == 200, response.text
    return gid, current, payload


def test_cookie_scope_hidden_state_and_host_authority(session):
    c, clock, host, guests, room, prefix, lease = session
    cookie = next(iter(host.cookies.jar))
    assert cookie.path == prefix
    assert cookie._rest['HttpOnly'] is None
    state = guests[0].get(prefix + '/state').json()
    assert 'songs' not in state and 'songs' not in state['room']
    assert all('session_token_hash' not in p for p in state['players'])
    assert guests[0].patch(prefix + '/settings', json={'round_count': 5}).status_code == 403
    assert guests[0].post(prefix + '/audio-controller', json={'tab_id': 'evil'}).status_code == 403
    other = host.post('/api/rooms', json={'nickname': 'Elsewhere', 'mode': 'demo'}).json()
    assert host.get(prefix + '/state').json()['me']['nickname'] == 'Host'
    assert host.get('/api/rooms/' + other['room_id'] + '/state').json()['me']['nickname'] == 'Elsewhere'
    assert guests[0].get('/api/rooms/' + other['room_id'] + '/state').status_code == 401


def test_origin_validation_and_normal_unavailable(session):
    c, clock, host, guests, room, prefix, lease = session
    assert host.post(prefix + '/heartbeat', json={}, headers={'Origin': 'https://evil.example'}).status_code == 403
    assert host.post(prefix + '/heartbeat', content='{}', headers={'Content-Type':'text/plain'}).status_code == 415
    assert host.post('/api/rooms', json={'nickname':'Normal','mode':'normal'}).status_code == 503
    assert host.post(prefix + '/heartbeat', json={}, headers={'Origin':'http://testserver'}).status_code == 200


def test_answer_race_closes_once_and_keeps_guesses_hidden(session):
    c, clock, host, guests, room, prefix, lease = session
    gid, attempt, payload = start(session)
    assert host.post(prefix + '/start', json=payload).json() == {'game_id': gid}
    assert TestClient(host.app).post(prefix + '/join', json={'nickname':'Late'}).status_code == 409
    public = guests[0].get(prefix + '/state').json()
    assert 'audio_candidate_id' not in public['game']['round']
    assert public['game']['round']['reveal'] is None
    with c.db.read() as conn:
        clock.value = c.game.repo.current(conn, gid)['starts_at_ms']
    c.tick()
    path = prefix + f'/games/{gid}/rounds/{attempt["id"]}/answers'
    assert host.post(path, json={'song_option':0,'who_player_ids':[]}).status_code == 200
    seen = guests[0].get(prefix + '/state').json()['game']['round']
    assert len(seen['submitted_player_ids']) == 1
    assert seen['my_answer'] is None and seen['reveal'] is None
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda client: client.post(path,json={'song_option':1,'who_player_ids':[]}), guests))
    assert all(r.status_code == 200 for r in responses)
    state = host.get(prefix + '/state').json()
    assert state['game']['phase'] == 'reveal'
    assert len(state['game']['round']['reveal']['answers']) == 3
    assert host.post(path,json={'song_option':0,'who_player_ids':[]}).status_code == 200
    assert host.post(path,json={'song_option':2,'who_player_ids':[]}).status_code == 409
    assert host.post(prefix + f'/games/{gid}/rounds/{attempt["id"]}/audio-failure',json={
        'request_id':str(uuid4()),'readiness_generation':1,'lease_id':lease}).status_code == 409
    with c.db.read() as conn:
        assert len(c.game.repo.attempts(conn,gid)) == 1
        assert c.game.repo.current(conn,gid)['status'] == 'revealed'


def test_exact_deadline_commits_closure_even_when_answer_rejected(session):
    c, clock, host, guests, room, prefix, lease = session
    gid, attempt, _ = start(session)
    with c.db.read() as conn:
        deadline = c.game.repo.current(conn,gid)['deadline_at_ms']
    clock.value = deadline
    response = guests[0].post(prefix + f'/games/{gid}/rounds/{attempt["id"]}/answers',json={'song_option':0,'who_player_ids':[]})
    assert response.status_code == 409
    with c.db.read() as conn:
        assert c.game.repo.current(conn,gid)['status'] == 'revealed'
        assert all(a['status']=='missing' and a['points']==0 for a in c.game.repo.answers(conn,attempt['id']))


def test_host_expiry_cannot_be_revived_by_late_heartbeat(session):
    c, clock, host, guests, room, prefix, lease = session
    gid, _, _ = start(session)
    clock.value = 1_060_000
    assert host.post(prefix + '/heartbeat',json={}).status_code == 200
    state = host.get(prefix + '/state').json()
    assert state['game']['status'] == 'aborted'
    assert state['game']['end_reason'] == 'host_timeout'
    assert state['room']['state'] == 'lobby'


def test_lease_takeover_without_game_and_settings_after_restart(session):
    c, clock, host, guests, room, prefix, lease = session
    takeover = host.post(prefix + '/audio-controller',json={'tab_id':'new-tab','takeover':True})
    assert takeover.status_code == 200
    assert host.get(prefix + '/games/missing/audio',headers={'X-Audio-Lease':lease}).status_code == 409
    new_lease = takeover.json()['lease_id']
    old = host.get(prefix + '/state').json()
    started = host.post(prefix + '/start',json={'request_id':'restart','room_revision':old['room']['revision'],'lease_id':new_lease})
    gid = started.json()['game_id']
    c.initialize()
    state = host.get(prefix + '/state').json()
    assert state['game']['status'] == 'aborted'
    assert state['game']['end_reason'] == 'server_restart'
    assert set(state['settings']) == {'round_count','answer_seconds','difficulty','decoys_enabled'}
    assert host.patch(prefix + '/settings',json={'difficulty':'hard'}).status_code == 200
    assert host.patch(prefix + '/settings',json={'round_count':5}).status_code == 200
    assert host.get(prefix + '/state').json()['settings']['difficulty'] == 'hard'
    assert host.get('/api/room-codes/' + room['code'] + '/history').json()['games'][0]['id'] == gid
