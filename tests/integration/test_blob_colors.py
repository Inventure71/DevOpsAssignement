"""Blob color admission, frozen roster presentation and populated v2 upgrades."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core.config import Config
from backend.storage.database import Database
from tests.integration.test_game import Match
from tests.support.catalog import write_large_catalog


LEGACY_COLORS = {
    'vinyl': 'coral', 'bolt': 'periwinkle', 'moon': 'lavender', 'sun': 'lemon',
    'ghost': 'lilac', 'flower': 'sage', 'wave': 'sky', 'star': 'rose',
}


def records(conn):
    tables = [row['name'] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return {table: [dict(row) for row in conn.execute('SELECT * FROM ' + table + ' ORDER BY rowid')] for table in tables}


@pytest.mark.parametrize('legacy,color', LEGACY_COLORS.items())
def test_v2_upgrade_maps_live_and_frozen_colors_preserving_all_other_data(tmp_path, legacy, color):
    match = Match(tmp_path / 'source')
    match.preload()
    match.answering()
    selected, listeners = match.correct()
    match.submit(match.host, selected, listeners, match.now + 1000)
    match.close()
    with match.db.transaction() as conn:
        match.game.finish(conn, match.game_id, match.now + 100, 'host_ended')
        match.rooms.set_state(conn, match.room_id, 'lobby')
    path = tmp_path / 'v2.sqlite3'
    with match.db.read() as source, sqlite3.connect(path) as old:
        # Migration 3 changes data only: the source's table layout is exactly v2.
        source.backup(old)
        old.execute('PRAGMA user_version=2')
        old.execute('UPDATE players SET character_id=? WHERE id=?', (legacy, match.host))
        old.execute('UPDATE game_players SET character_id=? WHERE player_id=?', (legacy, match.host))
    old_db = Database(path)
    with old_db.read() as conn:
        before = records(conn)
        before_board = match.game.repo.leaderboard(conn, match.game_id)
        assert before_board[0]['score'] > 0
    expected = before
    for table in ('players', 'game_players'):
        for record in expected[table]:
            record['character_id'] = LEGACY_COLORS.get(record['character_id'], record['character_id'])
    for record in before_board:
        record['character_id'] = LEGACY_COLORS.get(record['character_id'], record['character_id'])
    old_db.initialize()
    old_db.initialize()
    with old_db.read() as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 3
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
        assert records(conn) == expected  # Memberships, credentials, answers, points and receipts survive.
        assert match.rooms.authenticate(conn, match.room_id, match.token, match.now)['character_id'] == color
        assert match.game.repo.leaderboard(conn, match.game_id) == before_board
        assert match.game.repo.history(conn, match.room_id)[0]['leaderboard'] == before_board


def test_color_api_defaults_new_presets_rejects_old_ids_and_freezes_roster(tmp_path, monkeypatch):
    monkeypatch.setattr('backend.rooms.demo.CATALOG_PATH', write_large_catalog(tmp_path / 'catalog.json'))
    app = create_app(Config(tmp_path), clock=lambda: 1000, background=False)
    with TestClient(app) as host, TestClient(app) as guest_one, TestClient(app) as guest_two:
        room = host.post('/api/rooms', json={'nickname': 'Host', 'mode': 'demo'}).json()
        prefix = '/api/rooms/' + room['room_id']
        assert host.get(prefix + '/state').json()['me']['character_id'] == 'coral'
        for legacy in LEGACY_COLORS:
            response = host.patch(prefix + '/player', json={'nickname': 'Host', 'character_id': legacy})
            assert response.status_code == 400 and response.json()['error']['code'] == 'invalid_character'
        for color in LEGACY_COLORS.values():
            response = host.patch(prefix + '/player', json={'nickname': 'Host', 'character_id': color})
            assert response.status_code == 200 and response.json()['character_id'] == color
        for client, name, color in [(guest_one, 'Ada', 'sky'), (guest_two, 'Grace', 'sage')]:
            assert client.post(prefix + '/join', json={'nickname': name, 'character_id': color}).status_code == 201
        lease = host.post(prefix + '/audio-controller', json={'tab_id': 'host'}).json()['lease_id']
        state = host.get(prefix + '/state').json()
        response = host.post(prefix + '/start', json={'request_id': 'colors', 'room_revision': state['room']['revision'],
                                                     'lease_id': lease})
        assert response.status_code == 200, response.text
        game_id = response.json()['game_id']
        with app.state.coordinator.db.read() as conn:
            roster = app.state.coordinator.game.repo.roster(conn, game_id)
            assert {player['character_id'] for player in roster} == {'rose', 'sky', 'sage'}
        assert host.patch(prefix + '/player', json={'nickname': 'Host', 'character_id': 'coral'}).status_code == 409
        # Even later live presentation changes do not rewrite the game's copied color.
        with app.state.coordinator.db.transaction() as conn:
            conn.execute("UPDATE players SET character_id='coral' WHERE id=?", (room['player_id'],))
        with app.state.coordinator.db.read() as conn:
            assert next(player for player in app.state.coordinator.game.repo.roster(conn, game_id)
                        if player['player_id'] == room['player_id'])['character_id'] == 'rose'
