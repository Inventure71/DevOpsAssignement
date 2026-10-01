"""Clock-driven game transitions; callers commit them atomically."""
import json

from backend.game.repository import encode
from backend.game.selection import skip_limit_exceeded


class PhaseMachine:
    def __init__(self, service):
        self.game = service
        self.repo = service.repo

    def advance(self, conn, game_id, now, host_connected=True):
        for _ in range(64):
            game = self.repo.game(conn, game_id)
            if game['status'] in ('completed', 'aborted'):
                return
            phase = game['phase']
            if phase == 'setup':
                if now < game['phase_ends_at_ms']:
                    return
                plan = json.loads(game['round_plan_json'])
                candidates = [c['song_key'] for s in plan for c in s['candidates']]
                checked = sum(len(s['checks']) for s in plan)
                if checked < len(candidates) and now < game['started_at_ms'] + self.game.setup_timeout_ms:
                    return
                if checked < len(candidates):
                    self.game.finish(conn, game_id, now, 'host_preparation_timeout')
                    return
                if not host_connected:
                    return
                for slot in plan:
                    for c in slot['candidates']:
                        slot['checks'].setdefault(c['song_key'], False)
                    slot['chosen_index'] = next((i for i, c in enumerate(slot['candidates']) if slot['checks'][c['song_key']]), None)
                    slot['skipped'] = slot['chosen_index'] is None
                self.repo.update_game(conn, game_id, prepared_at_ms=now, round_plan_json=encode(plan))
                if skip_limit_exceeded(sum(s['skipped'] for s in plan), json.loads(game['settings_json'])['round_count']):
                    self.game.finish(conn, game_id, now, 'too_many_skipped')
                    return
                self.game._next(conn, self.repo.game(conn, game_id), 0, now)
            elif phase == 'ready':
                attempt = self.repo.current(conn, game_id)
                if now >= attempt['readiness_deadline_at_ms']:
                    if game['status'] == 'preparing':
                        self.game.finish(conn, game_id, now, 'initial_readiness_timeout')
                    return
                if host_connected:
                    self.game._schedule(conn, game_id, now)
                if self.repo.game(conn, game_id)['phase'] == 'ready':
                    return
            elif phase == 'countdown':
                attempt = self.repo.current(conn, game_id)
                if now < attempt['starts_at_ms']:
                    return
                self.repo.update_round(conn, attempt['id'], status='playing')
                self.repo.update_game(conn, game_id, phase='answering', phase_ends_at_ms=attempt['deadline_at_ms'])
            elif phase == 'answering':
                attempt = self.repo.current(conn, game_id)
                if now < attempt['deadline_at_ms']:
                    return
                self.game._close(conn, game, attempt, attempt['deadline_at_ms'])
            elif phase == 'reveal':
                if now < game['phase_ends_at_ms']:
                    return
                self.repo.update_game(conn, game_id, phase='leaderboard', phase_ends_at_ms=game['phase_ends_at_ms'] + 5000)
            elif phase == 'leaderboard':
                if now < game['phase_ends_at_ms']:
                    return
                attempt = self.repo.current(conn, game_id)
                has_next = any(s['round_number'] > attempt['round_number'] and not s.get('skipped') for s in json.loads(game['round_plan_json']))
                if has_next and not host_connected:
                    return
                self.game._next(conn, game, attempt['round_number'], now)
            else:
                return
        raise RuntimeError('Game transition bound exceeded')
