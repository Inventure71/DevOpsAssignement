"""Phase-specific projections; never expose hidden guesses or listener maps."""
import json


def game_view(repo, conn, game, player_id, host=False):
    if game is None:
        return None
    settings = json.loads(game['settings_json'])
    plan = json.loads(game['round_plan_json'])
    result = {k: game[k] for k in ('id', 'status', 'phase', 'state_version', 'phase_ends_at_ms', 'end_reason')}
    skipped = {s['round_number'] for s in plan if s.get('skipped')}
    latest_attempts = {}
    for attempt in repo.attempts(conn, game['id']):
        latest_attempts[attempt['round_number']] = attempt
    for slot in plan:
        attempt = latest_attempts.get(slot['round_number'])
        if attempt and attempt['status'] == 'void' and attempt['void_reason'] != game['end_reason']:
            if not any(i >= attempt['attempt'] and slot['checks'].get(c['song_key']) is True for i, c in enumerate(slot['candidates'])):
                skipped.add(slot['round_number'])
    result.update(requested_rounds=settings['round_count'],
        playable_rounds=settings['round_count'] - len(skipped),
        leaderboard=repo.leaderboard(conn, game['id']), missing_player_ids=[], round=None,
        preparation={'checked': sum(len(s.get('checks', {})) for s in plan),
                     'total': sum(len(s['candidates']) for s in plan)})
    current = repo.current(conn, game['id'])
    if not current:
        return result
    roster = repo.roster(conn, game['id'])
    ready = json.loads(current['ready_player_ids_json'])
    excluded = json.loads(current['excluded_player_ids_json'])
    result['missing_player_ids'] = [p['player_id'] for p in roster if p['player_id'] not in ready and p['player_id'] not in excluded]
    songs = {s['song_key']: s for s in json.loads(game['songs_snapshot_json'])}
    options = json.loads(current['options_json'])
    answers = repo.answers(conn, current['id'])
    own = next((a for a in answers if a['player_id'] == player_id and a['status'] == 'submitted'), None)
    round_view = {k: current[k] for k in ('id', 'round_number', 'attempt', 'readiness_generation',
        'readiness_deadline_at_ms', 'starts_at_ms', 'deadline_at_ms')}
    round_view.update(options=[{'index': i, 'title': songs[k]['title'], 'artist': songs[k]['artist']} for i, k in enumerate(options)],
        submitted_player_ids=[a['player_id'] for a in answers if a['status'] == 'submitted'],
        ready_player_ids=ready, excluded_player_ids=excluded,
        my_answer=None if own is None else {'song_option': own['song_option'], 'who_player_ids': json.loads(own['who_player_ids_json'])},
        reveal=None)
    if host and current['status'] in ('ready', 'playing'):
        round_view['audio_candidate_id'] = current['song_key']
    if current['status'] == 'revealed':
        song = songs[current['song_key']]
        round_view['reveal'] = {'song': {k: song.get(k) for k in ('title', 'artist', 'artwork_url')},
            'correct_option': options.index(current['song_key']),
            'listener_ids': [l['player_id'] for l in song['listeners']],
            'answers': [{k: a[k] for k in ('player_id', 'status', 'song_option', 'points')} | {'who_player_ids': json.loads(a['who_player_ids_json'])} for a in answers]}
    result['round'] = round_view
    return result


def audio_manifest(game):
    songs = {s['song_key']: s for s in json.loads(game['songs_snapshot_json'])}
    plan = json.loads(game['round_plan_json'])
    return {'candidates': [{'candidate_id': c['song_key'], 'preview_url': songs[c['song_key']]['preview_url']}
        for slot in plan for c in slot['candidates']]}
