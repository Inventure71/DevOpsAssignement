"""Media cache restarts, storefront/version boundaries and independent ownership."""

import pytest

from backend.catalog.store import CatalogStore
from backend.core.errors import DomainError
from backend.music.previews import PreviewResolver
from tests.unit.test_music_previews import FakeCatalog, PREVIEW_URL, song


def test_preview_reference_restart_expiry_and_player_evidence(tmp_path):
    store = CatalogStore(tmp_path / 'catalog.sqlite3')
    store.initialize()
    now, calls = [100.0], []
    catalog = FakeCatalog(lambda entry: calls.append(entry) or entry | {'preview_url': PREVIEW_URL,
        'artists': [entry['artists'][0] | {'aliases': ['apple:artist:kanye']}]})
    first = PreviewResolver(catalog, store=store, clock=lambda: now[0], monotonic=lambda: now[0])
    assert first.resolve(song())['preview_url'] == PREVIEW_URL
    second = PreviewResolver(catalog, store=store, clock=lambda: now[0], monotonic=lambda: now[0])
    result = second.resolve(song(song_key='spotify:track:another-release', familiarity='hard', source_evidence=['recent']))
    assert result['familiarity'] == 'hard' and result['source_evidence'] == ['recent']
    assert result['artists'][0]['aliases'] == ['apple:artist:kanye']
    assert len(calls) == 1
    with store.connect() as conn:
        serialized = conn.execute('SELECT result_json FROM preview_references').fetchone()[0]
    assert 'recent' not in serialized and 'familiarity' not in serialized and 'spotify:track:' not in serialized
    now[0] += 1190
    assert second.resolve(song()) is not None
    now[0] += 11
    assert second.resolve(song()) is not None
    assert len(calls) == 2  # repeated durable hits never extend original URL expiry


@pytest.mark.parametrize('change', [
    {'title': 'Stronger (Live)'}, {'title': 'Stronger (Remastered)'},
    {'artists': [{'artist_key': 'spotify:artist:cover', 'name': 'Cover Band'}]},
    {'isrc': 'ANOTHER_RECORDING'},
])
def test_preview_cache_keeps_recording_versions_artists_and_isrc_separate(tmp_path, change):
    store = CatalogStore(tmp_path / 'catalog.sqlite3')
    store.initialize()
    calls = []
    catalog = FakeCatalog(lambda entry: calls.append(entry) or entry | {'preview_url': PREVIEW_URL})
    PreviewResolver(catalog, store=store).resolve(song())
    PreviewResolver(catalog, store=store).resolve(song(**change))
    assert len(calls) == 2


def test_preview_cache_provider_storefront_isolation(tmp_path):
    store = CatalogStore(tmp_path / 'catalog.sqlite3')
    store.initialize()
    calls = []
    catalog = FakeCatalog(lambda entry: calls.append(entry) or entry | {'preview_url': PREVIEW_URL})
    for scope in ('apple:es', 'apple:us', 'other:es'):
        PreviewResolver(catalog, store=store, provider_scope=scope).resolve(song())
    assert len(calls) == 3


@pytest.mark.parametrize('failure, ttl', [(None, 60), ('error', 10)])
def test_negative_or_provider_error_persists_briefly_and_recovers(tmp_path, failure, ttl):
    store = CatalogStore(tmp_path / 'catalog.sqlite3')
    store.initialize()
    now, calls = [100.0], []
    def fetch(entry):
        calls.append(entry)
        if now[0] <= 100 + ttl:
            if failure:
                raise DomainError('preview_provider_unavailable', 'Offline', 503)
            return None
        return entry | {'preview_url': PREVIEW_URL}
    catalog = FakeCatalog(fetch)
    for _ in range(2):
        resolver = PreviewResolver(catalog, store=store, clock=lambda: now[0])
        if failure:
            with pytest.raises(DomainError, match='Offline'):
                resolver.resolve(song())
        else:
            assert resolver.resolve(song()) is None
    assert len(calls) == 1
    now[0] += ttl + 1
    assert PreviewResolver(catalog, store=store, clock=lambda: now[0]).resolve(song())['preview_url'] == PREVIEW_URL
    assert len(calls) == 2


def test_bad_provider_url_is_not_reused_and_unexpected_crash_does_not_cache_missing(tmp_path):
    store = CatalogStore(tmp_path / 'catalog.sqlite3')
    store.initialize()
    resolver = PreviewResolver(FakeCatalog(lambda entry: entry | {'preview_url': 'https://127.0.0.1/private'}), store=store)
    assert resolver.resolve(song()) is None
    def crash(entry):
        raise RuntimeError('Unexpected provider bug')
    resolver = PreviewResolver(FakeCatalog(crash), store=store)
    with pytest.raises(RuntimeError):
        resolver.resolve(song(isrc='DIFFERENT'))
    with store.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM preview_references').fetchone()[0] == 1


def test_explicit_signed_url_expiry_bounds_durable_cache_without_extending_on_restart(tmp_path):
    store = CatalogStore(tmp_path / 'catalog.sqlite3')
    store.initialize()
    now, calls = [100.0], []
    def fetch(entry):
        calls.append(entry)
        return entry | {'preview_url': PREVIEW_URL + '?Expires=' + str(now[0] + 10)}
    catalog = FakeCatalog(fetch)
    first = PreviewResolver(catalog, store=store, clock=lambda: now[0], monotonic=lambda: now[0])
    assert first.resolve(song())['preview_url'].endswith('110.0')
    now[0] = 108
    second = PreviewResolver(catalog, store=store, clock=lambda: now[0], monotonic=lambda: now[0])
    assert second.resolve(song())['preview_url'].endswith('110.0')
    assert len(calls) == 1
    now[0] = 111
    assert second.resolve(song())['preview_url'].endswith('121')
    assert len(calls) == 2
    with store.connect() as conn:
        assert conn.execute('SELECT expires_at FROM preview_references').fetchone()[0] == 121


def test_already_expired_signed_url_is_never_cached_as_playable(tmp_path):
    store = CatalogStore(tmp_path / 'catalog.sqlite3')
    store.initialize()
    resolver = PreviewResolver(FakeCatalog(lambda entry: entry | {'preview_url': PREVIEW_URL + '?exp=99'}),
                               store=store, clock=lambda: 100)
    assert resolver.resolve(song()) is None
    with store.connect() as conn:
        assert conn.execute('SELECT result_json FROM preview_references').fetchone()[0] == 'null'


def test_additional_credit_does_not_reuse_another_recordings_artist_aliases(tmp_path):
    store = CatalogStore(tmp_path / 'catalog.sqlite3')
    store.initialize()
    calls = []
    catalog = FakeCatalog(lambda entry: calls.append(entry) or entry | {'preview_url': PREVIEW_URL})
    PreviewResolver(catalog, store=store).resolve(song())
    PreviewResolver(catalog, store=store).resolve(song(artists=[*song()['artists'], {'artist_key': 'spotify:artist:guest', 'name': 'Guest'}]))
    assert len(calls) == 2
