"""Persist verified imports without exposing personal listening evidence in views."""
import json
import secrets
import hashlib

from backend.catalog.identity import normalized_words, recording_title
from backend.core.errors import DomainError


def identity(song):
    return 'isrc:' + song['isrc'] if song.get('isrc') else song['song_key']


def store(conn, room_id, player_id, songs, *, decoys=False):
    for song in songs:
        key = identity(song)
        existing = conn.execute('SELECT id,title,artists_json FROM songs WHERE room_id=? AND identity_key=?',
                                (room_id, key)).fetchone()
        if existing and not _compatible(existing, song):
            # Provider ISRC metadata can be mislabeled. Keep conflicting versions
            # separate rather than attaching one recording's owners to another.
            variant = recording_title(song['title']) + ':' + normalized_words(song['artists'][0]['name'])
            key += ':variant:' + hashlib.sha256(variant.encode()).hexdigest()[:16]
            existing = conn.execute('SELECT id,title,artists_json FROM songs WHERE room_id=? AND identity_key=?',
                                    (room_id, key)).fetchone()
        if existing:
            song_id = existing['id']
            artists = {a['artist_key']: a for a in json.loads(existing['artists_json'])}
            for credit in song['artists']:
                prior = artists.get(credit['artist_key'], {})
                aliases = list(dict.fromkeys([*prior.get('aliases', []), *credit.get('aliases', [])]))
                artists[credit['artist_key']] = {**credit, **({'aliases': aliases} if aliases else {})}
            conn.execute('''UPDATE songs SET artists_json=?,preview_url=COALESCE(preview_url,?),
                            artwork_url=COALESCE(artwork_url,?) WHERE id=?''',
                         (json.dumps(list(artists.values())), song.get('preview_url'), song.get('artwork_url'), song_id))
            if not decoys:
                conn.execute("UPDATE songs SET pool_kind='personal' WHERE id=?", (song_id,))
        else:
            song_id = secrets.token_hex(16)
            conn.execute('''INSERT INTO songs (id,room_id,identity_key,isrc,title,artist,artists_json,
                            preview_url,artwork_url,pool_kind) VALUES (?,?,?,?,?,?,?,?,?,?)''',
                         (song_id, room_id, key, song.get('isrc'), song['title'], song['artist'],
                          json.dumps(song['artists']), song.get('preview_url'), song.get('artwork_url'),
                          'decoy' if decoys else 'personal'))
        if not decoys:
            conn.execute('INSERT OR IGNORE INTO player_songs (room_id,player_id,song_id,familiarity) VALUES (?,?,?,?)',
                         (room_id, player_id, song_id, song['familiarity']))


def _compatible(existing, song):
    source_names = {normalized_words(credit['name']) for credit in song['artists']}
    stored_names = {normalized_words(credit['name']) for credit in json.loads(existing['artists_json'])}
    return recording_title(existing['title']) == recording_title(song['title']) and bool(source_names & stored_names)


def validate_import(imported):
    songs = imported.get('songs', [])
    if not imported.get('account_id') or len({identity(s) for s in songs}) < 10:
        raise DomainError('music_import_insufficient', 'At least ten playable songs are needed to join.', 409)
    for song in [*songs, *imported.get('decoys', [])]:
        if not song.get('preview_url') or not song.get('artists'):
            raise DomainError('invalid_music_import', 'The verified import is incomplete.', 503)
