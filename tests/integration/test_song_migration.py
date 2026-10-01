"""Upgrade a populated real v1 database without losing history or guess evidence."""
import json
import sqlite3

from backend.core.paths import MIGRATIONS_DIR
from backend.storage.database import Database
from tests.integration.test_game import Match


def test_v1_choices_migrate_to_frozen_song_facts_and_keep_history(tmp_path):
    source_dir = tmp_path / 'source'
    match = Match(source_dir)
    match.preload()
    match.answering()
    selected, listeners = match.correct()
    match.submit(match.host, selected, listeners, match.now + 1000)
    match.close()
    with match.db.transaction() as source:
        match.game.finish(source, match.game_id, match.now + 100, 'host_ended')
    path = tmp_path / 'old.sqlite3'
    old = sqlite3.connect(path)
    old.execute('PRAGMA foreign_keys=ON')
    old.executescript((MIGRATIONS_DIR / '001_initial.sql').read_text() + '\nPRAGMA user_version=1;')
    tables = ['rooms', 'players', 'songs', 'demo_catalog', 'player_songs', 'games', 'game_players']
    with match.db.read() as source:
        for table in tables:
            for record in source.execute('SELECT * FROM ' + table):
                values = dict(record)
                if table in {'players', 'game_players'}:
                    values['character_id'] = {'coral': 'vinyl', 'lavender': 'moon'}[values['character_id']]
                old.execute('INSERT INTO ' + table + ' VALUES (' + ','.join('?' for _ in values) + ')', tuple(values.values()))
        frozen = json.loads(match.game.repo.game(source, match.game_id)['songs_snapshot_json'])
        rounds = match.game.repo.attempts(source, match.game_id)
        for record in rounds:
            options = [record['song_key']] + [song['song_key'] for song in frozen if song['song_key'] != record['song_key']][:3]
            values = dict(record) | {'options_json': json.dumps(options)}
            keys = ','.join(values)
            old.execute('INSERT INTO rounds (' + keys + ') VALUES (' + ','.join('?' for _ in values) + ')', tuple(values.values()))
            for answer in match.game.repo.answers(source, record['id']):
                guess = json.loads(answer.pop('song_guess_json'))
                answer['song_option'] = options.index(guess['song_key']) if guess else None
                old.execute('INSERT INTO answers (' + ','.join(answer) + ') VALUES (' + ','.join('?' for _ in answer) + ')', tuple(answer.values()))
        expected_board = match.game.repo.leaderboard(source, match.game_id)
    old.commit()
    old.close()
    migrated = Database(path)
    migrated.initialize()
    migrated.initialize()  # Repeated startup is safe.
    with migrated.read() as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 3
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
        assert 'options_json' not in {row['name'] for row in conn.execute('PRAGMA table_info(rounds)')}
        answers = match.game.repo.answers(conn, rounds[0]['id'])
        submitted = next(answer for answer in answers if answer['player_id'] == match.host)
        assert json.loads(submitted['song_guess_json']) == selected
        assert submitted['points'] > 0
        assert all(json.loads(answer['song_guess_json']) is None for answer in answers if answer['status'] == 'missing')
        assert match.game.repo.leaderboard(conn, match.game_id) == expected_board
        assert match.game.repo.history(conn, match.room_id)[0]['leaderboard'] == expected_board
