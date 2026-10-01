"""Game-owned persistence. No query crosses into Rooms tables."""
import json


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def row(value):
    return dict(value) if value is not None else None


class GameRepository:
    def game(self, conn, game_id):
        return row(conn.execute('SELECT * FROM games WHERE id = ?', (game_id,)).fetchone())

    def latest(self, conn, room_id):
        return row(conn.execute('SELECT * FROM games WHERE room_id = ? ORDER BY started_at_ms DESC, rowid DESC LIMIT 1', (room_id,)).fetchone())

    def active(self, conn):
        return [dict(r) for r in conn.execute("SELECT * FROM games WHERE status IN ('preparing','playing')")]

    def start_receipt(self, conn, room_id, request_id):
        return row(conn.execute('SELECT * FROM games WHERE room_id = ? AND start_request_id = ?', (room_id, request_id)).fetchone())

    def roster(self, conn, game_id):
        return [dict(r) for r in conn.execute('SELECT * FROM game_players WHERE game_id = ? ORDER BY rowid', (game_id,))]

    def attempts(self, conn, game_id):
        return [dict(r) for r in conn.execute('SELECT * FROM rounds WHERE game_id = ? ORDER BY round_number, attempt', (game_id,))]

    def current(self, conn, game_id):
        return row(conn.execute('SELECT * FROM rounds WHERE game_id = ? ORDER BY round_number DESC, attempt DESC LIMIT 1', (game_id,)).fetchone())

    def answers(self, conn, round_id):
        return [dict(r) for r in conn.execute('SELECT * FROM answers WHERE round_id = ?', (round_id,))]

    def receipt(self, conn, game_id, request_id):
        return row(conn.execute('SELECT * FROM game_commands WHERE game_id = ? AND request_id = ?', (game_id, request_id)).fetchone())

    def remember(self, conn, game_id, actor, kind, payload, result, now):
        conn.execute('INSERT INTO game_commands VALUES (?,?,?,?,?,?,?)',
                     (game_id, payload['request_id'], actor, kind, encode(payload), encode(result), now))

    def insert(self, conn, table, values):
        # Identifiers are internal constants, never request input.
        assert table in {'games', 'game_players', 'rounds', 'answers'}
        keys = ','.join(values)
        conn.execute(f'INSERT INTO {table} ({keys}) VALUES ({",".join("?" for _ in values)})', tuple(values.values()))

    def update_game(self, conn, game_id, **fields):
        self._update(conn, 'games', 'id', game_id, fields)
        conn.execute('UPDATE games SET state_version = state_version + 1 WHERE id = ?', (game_id,))

    def update_round(self, conn, round_id, **fields):
        self._update(conn, 'rounds', 'id', round_id, fields)

    def _update(self, conn, table, key, value, fields):
        conn.execute(f'UPDATE {table} SET {",".join(f"{k} = ?" for k in fields)} WHERE {key} = ?', (*fields.values(), value))

    def leaderboard(self, conn, game_id):
        values = [dict(r) for r in conn.execute('''
            SELECT p.player_id, p.nickname, p.character_id,
                   COALESCE(SUM(CASE WHEN r.status = 'revealed' THEN a.points ELSE 0 END),0) score
            FROM game_players p LEFT JOIN answers a ON a.game_id=p.game_id AND a.player_id=p.player_id
            LEFT JOIN rounds r ON r.game_id=a.game_id AND r.id=a.round_id
            WHERE p.game_id=? GROUP BY p.game_id,p.player_id,p.nickname,p.character_id
            ORDER BY score DESC,p.nickname,p.player_id''', (game_id,))]
        previous, rank = None, 0
        for position, item in enumerate(values, 1):
            if item['score'] != previous:
                rank = position
            item['rank'] = rank
            previous = item['score']
        return values

    def save_ranks(self, conn, game_id):
        for item in self.leaderboard(conn, game_id):
            conn.execute('UPDATE game_players SET final_score=?, final_rank=? WHERE game_id=? AND player_id=?',
                         (item['score'], item['rank'], game_id, item['player_id']))

    def history(self, conn, room_id):
        games = conn.execute("SELECT id,status,end_reason,ended_at_ms FROM games WHERE room_id=? AND status IN ('completed','aborted') ORDER BY ended_at_ms DESC LIMIT 50", (room_id,))
        return [{**dict(g), 'leaderboard': self.leaderboard(conn, g['id'])} for g in games]

    def delete_room_games(self, conn, room_id):
        conn.execute('DELETE FROM games WHERE room_id=?', (room_id,))
