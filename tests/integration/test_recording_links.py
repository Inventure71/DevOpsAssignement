"""Actual Apple adapter renews media by durable verified IDs across imports."""

import json

import pytest

from backend.catalog import links
from backend.catalog.store import CatalogStore
from backend.core.errors import DomainError
from backend.music.http import ProviderHttpError
from backend.music.previews import PreviewResolver
from tests.unit.test_apple_provider import catalog_song, client, spotify_song


def store_at(tmp_path):
    store = CatalogStore(tmp_path / 'catalog.sqlite3')
    store.initialize()
    return store


def resolver(apple, store, now):
    return PreviewResolver(apple, store=store, provider_scope='apple:es',
                           clock=lambda: now[0], monotonic=lambda: now[0])


def row(identifier='123', **attributes):
    return catalog_song(**attributes) | {'id': identifier}


def targets(store, source):
    return {song['song_key'] for song in store.links.find('apple:es', 'recording', source)}


def test_preview_expiry_after_years_uses_saved_id_and_records_each_source(tmp_path):
    store, now = store_at(tmp_path), [100.0]
    apple, transport = client([
        {'data': [row(previews=[{'url': 'https://audio-ssl.itunes.apple.com/old.m4a?exp=110'}])]},
        {'data': [row(previews=[{'url': 'https://audio-ssl.itunes.apple.com/new.m4a'}])]},
    ])
    source = spotify_song() | {'source_evidence': ['private-first-player']}
    assert resolver(apple, store, now).resolve(source)['preview_url'].endswith('exp=110')
    second = source | {'song_key': 'spotify:track:another-release', 'familiarity': 'easy',
                       'source_evidence': ['private-second-player']}
    # A cache hit must also retain the second Spotify ID's explicit mapping.
    assert resolver(apple, store, now).resolve(second)['familiarity'] == 'easy'
    assert targets(store, source) == targets(store, second) == {'apple:track:123', 'isrc:USUM70741277'}
    now[0] += 10 * 365 * 86400
    restarted = CatalogStore(store.path)
    restarted.initialize()
    result = resolver(apple, restarted, now).resolve(second)
    assert result['preview_url'].endswith('new.m4a')
    assert result['source_evidence'] == ['private-second-player']
    assert result['artists'][0]['aliases'] == ['apple:artist:kanye']
    assert len(transport.calls) == 2
    assert 'ids=123' in transport.calls[1][1]
    assert 'filter' not in transport.calls[1][1] and '/search?' not in transport.calls[1][1]
    apple_target = next(value for value in restarted.links.find('apple:es', 'recording', source)
                        if value['song_key'] == 'apple:track:123')
    assert targets(restarted, apple_target) >= {source['song_key'], second['song_key'], 'isrc:USUM70741277'}
    assert restarted.links.find('apple:es', 'guess', source) == []
    with restarted.connect() as conn:
        serialized = json.dumps([dict(value) for value in conn.execute('SELECT * FROM verified_links')])
        assert 'private-' not in serialized and 'familiarity' not in serialized
        assert 'preview_url' not in serialized
        assert conn.execute("SELECT COUNT(*) FROM catalog_songs WHERE song_key LIKE 'spotify:%'").fetchone()[0] == 0


def test_verified_identity_survives_missing_media_without_repeat_matching(tmp_path):
    store, now = store_at(tmp_path), [100.0]
    absent = row(previews=[])
    apple, transport = client([
        {'data': [absent]}, {'results': {'songs': {'data': [absent]}}},
        {'data': [absent]},
        {'data': [row()]},
    ])
    source = spotify_song()
    assert resolver(apple, store, now).resolve(source) is None
    assert 'apple:track:123' in targets(store, source)
    now[0] += 61
    assert resolver(apple, store, now).resolve(source) is None
    assert len(transport.calls) == 3 and 'ids=123' in transport.calls[-1][1]
    assert 'apple:track:123' in targets(store, source)
    now[0] += 61
    assert resolver(apple, store, now).resolve(source) is not None
    assert len(transport.calls) == 4 and 'ids=123' in transport.calls[-1][1]


@pytest.mark.parametrize('missing', [{'data': []}, ProviderHttpError(404)])
def test_unavailable_id_keeps_verified_link_and_can_discover_replacement(tmp_path, missing):
    store, now = store_at(tmp_path), [100.0]
    apple, transport = client([{'data': [row()]}, missing, {'data': [row('456')]}])
    source = spotify_song()
    assert resolver(apple, store, now).resolve(source)
    now[0] += 1201
    assert resolver(apple, store, now).resolve(source)
    assert targets(store, source) >= {'apple:track:123', 'apple:track:456'}
    assert 'ids=123' in transport.calls[1][1]


def test_proven_wrong_recording_rejects_only_bad_link_before_rematching(tmp_path):
    store, now = store_at(tmp_path), [100.0]
    apple, transport = client([{'data': [row()]}, {'data': [row(title='Stronger (Live)')]},
                               {'data': [row('456')]}])
    source = spotify_song()
    assert resolver(apple, store, now).resolve(source)
    now[0] += 1201
    assert resolver(apple, store, now).resolve(source)
    assert targets(store, source) == {'apple:track:456', 'isrc:USUM70741277'}
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM verified_links WHERE source_key='apple:track:123' OR target_key='apple:track:123'").fetchone()[0] == 0


def test_transient_provider_error_does_not_invalidate_identity(tmp_path):
    store, now = store_at(tmp_path), [100.0]
    apple, transport = client([{'data': [row()]}, ProviderHttpError(500), {'data': [row()]}])
    source = spotify_song()
    assert resolver(apple, store, now).resolve(source)
    now[0] += 1201
    with pytest.raises(DomainError):
        resolver(apple, store, now).resolve(source)
    assert 'apple:track:123' in targets(store, source)
    now[0] += 11
    assert resolver(apple, store, now).resolve(source)
    assert len(transport.calls) == 3 and 'ids=123' in transport.calls[-1][1]


def test_changed_matching_rules_require_new_verification_even_with_warm_url(tmp_path, monkeypatch):
    store, now = store_at(tmp_path), [100.0]
    apple, transport = client([{'data': [row()]}, {'data': [row()]}])
    source = spotify_song()
    assert resolver(apple, store, now).resolve(source)
    monkeypatch.setattr(links, 'MATCH_RULE_VERSION', links.MATCH_RULE_VERSION + 1)
    assert resolver(apple, store, now).resolve(source)
    assert len(transport.calls) == 2
    assert 'filter%5Bisrc%5D' in transport.calls[-1][1]


def test_incompatible_cached_metadata_is_refreshed_by_known_identity(tmp_path):
    store, now = store_at(tmp_path), [100.0]
    apple, transport = client([{'data': [row()]}, {'data': [row()]}])
    source = spotify_song()
    assert resolver(apple, store, now).resolve(source)
    with store.connect() as conn:
        key, serialized = conn.execute('SELECT cache_key,result_json FROM preview_references').fetchone()
        media = json.loads(serialized)
        media['catalog_song']['title'] = 'Stronger (Instrumental)'
        conn.execute('UPDATE preview_references SET result_json=? WHERE cache_key=?', (json.dumps(media), key))
    assert resolver(apple, store, now).resolve(source)
    assert len(transport.calls) == 2 and 'ids=123' in transport.calls[-1][1]
