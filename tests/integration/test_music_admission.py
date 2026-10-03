"""Normal-mode HTTP admission and five-player games over real SQLite services."""

import base64
import hashlib
import json
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core.config import Config
from backend.core.errors import DomainError


MUSIC = "/api/music/spotify"


class Clock:
    def __init__(self):
        self.value = 1_000_000

    def __call__(self):
        return self.value


def song(identifier, *, familiarity="easy", shared=False):
    return {"song_key": "spotify:track:" + identifier, "isrc": identifier.upper(),
            "title": "Catalog track " + identifier, "artist": "Test Artist",
            "artists": [{"artist_key": "spotify:artist:test", "name": "Test Artist"},
                        {"artist_key": "apple:artist:test", "name": "Test Artist"}],
            "preview_url": "https://audio.example/" + identifier + ".mp3",
            "artwork_url": "https://art.example/" + identifier + ".jpg",
            "familiarity": familiarity,
            "source_evidence": [{"source": "short_term" if shared else "long_term", "rank": 1}]}


class FakeSpotify:
    configured = True
    search_configured = False

    def __init__(self):
        self.authorizations = []
        self.exchanges = []

    def authorization_url(self, state, challenge):
        self.authorizations.append((state, challenge))
        return "https://accounts.spotify.example/authorize?" + urlencode({"state": state, "code_challenge": challenge})

    def exchange_code(self, code, verifier):
        self.exchanges.append((code, verifier))
        return "user-access:" + code

    def profile(self, token):
        return token.removeprefix("user-access:")


class FakeApple:
    configured = True

    def __init__(self):
        self.catalog = {}
        self.queries = []

    def register(self, songs):
        for value in songs:
            self.catalog[value["title"].casefold()] = value

    def search(self, query):
        self.queries.append(query)
        found = self.catalog.get(query.casefold())
        if not found:
            return []
        # Apple provides public metadata only, never the room's listener mapping.
        return [{"song_key": "apple:track:" + found["isrc"], "title": found["title"],
                 "artist": found["artist"], "artwork_url": found["artwork_url"],
                 "artists": [{"artist_key": "apple:artist:test", "name": "Test Artist"}]}]

    def decoys(self):
        return [song("decoy" + str(index)) for index in range(30)]


class FakeImporter:
    def __init__(self, spotify, apple):
        self.spotify, self.apple = spotify, apple
        self.failures = {}
        self.counts = {}
        self.imports = []
        self.block_accounts = set()
        self.blocked_count = 0
        self.blocked = threading.Event()
        self.release = threading.Event()
        self.lock = threading.Lock()

    def import_account(self, token, include_decoys=False):
        account = self.spotify.profile(token)
        if account in self.block_accounts:
            with self.lock:
                self.blocked_count += 1
                if self.blocked_count == len(self.block_accounts):
                    self.blocked.set()
            assert self.release.wait(5), "Import test barrier timed out"
        if account in self.failures:
            raise self.failures[account]
        count = self.counts.get(account, 60)
        songs = [song("shared" + str(index), shared=True) if index < 5 else
                 song(account + str(index), familiarity=("easy", "medium", "hard")[index % 3])
                 for index in range(count)]
        decoys = self.apple.decoys() if include_decoys else []
        self.apple.register([*songs, *decoys])
        self.imports.append((account, include_decoys))
        return {"account_id": account, "songs": songs, "decoys": decoys,
                "candidate_count": count, "unavailable_count": 0}


@pytest.fixture
def normal_session(tmp_path, request):
    clock, spotify, apple = Clock(), FakeSpotify(), FakeApple()
    importer = FakeImporter(spotify, apple)
    config = Config(tmp_path, spotify_redirect_uri="http://testserver/api/music/spotify/callback",
                    playtest=getattr(request, 'param', False))
    app = create_app(config, clock=clock, background=False, spotify_client=spotify,
                     apple_catalog=apple, music_importer=importer)
    clients = []
    with TestClient(app) as host:
        def new_client():
            client = TestClient(app)
            clients.append(client)
            return client
        yield {"app": app, "clock": clock, "spotify": spotify, "apple": apple,
               "importer": importer, "host": host, "new_client": new_client, "config": config}
        importer.release.set()
        for client in clients:
            client.close()


def begin(client, nickname, room_id=None):
    response = client.post(MUSIC + "/admissions", json={"nickname": nickname,
                          "character_id": "coral", "room_id": room_id})
    assert response.status_code == 200, response.text
    return parse_qs(urlsplit(response.json()["authorization_url"]).query)["state"][0]


def finish(client, state, account):
    response = client.get(MUSIC + "/callback", params={"state": state, "code": account}, follow_redirects=False)
    assert response.status_code == 303, response.text
    assert response.headers["location"] == "/?spotify=processing"
    return await_status(client)


def await_status(client):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(MUSIC + "/status")
        assert response.status_code == 200, response.text
        result = response.json()
        if result["status"] in ("complete", "failed"):
            return result
        time.sleep(0.005)
    pytest.fail("Background admission did not settle")


def admit(client, nickname, account, room_id=None):
    result = finish(client, begin(client, nickname, room_id), account)
    assert result["status"] == "complete", result
    return result["admission"]


def five_players(session):
    host = session["host"]
    room = admit(host, "Host", "host-account")
    clients, players = [host], [room["player_id"]]
    for number in range(1, 5):
        guest = session["new_client"]()
        joined = admit(guest, "Guest " + str(number), "account" + str(number), room["room_id"])
        clients.append(guest)
        players.append(joined["player_id"])
    return room, clients, players


def prepare_game(session, room, round_count=5):
    host, clock = session["host"], session["clock"]
    prefix = "/api/rooms/" + room["room_id"]
    response = host.patch(prefix + "/settings", json={"round_count": round_count})
    assert response.status_code == 200, response.text
    lease = host.post(prefix + "/audio-controller", json={"tab_id": "host-tab"}).json()["lease_id"]
    revision = host.get(prefix + "/state").json()["room"]["revision"]
    response = host.post(prefix + "/start", json={"request_id": str(uuid4()),
                         "room_revision": revision, "lease_id": lease})
    assert response.status_code == 200, response.text
    game_id = response.json()["game_id"]
    manifest = host.get(prefix + f"/games/{game_id}/audio", headers={"X-Audio-Lease": lease}).json()
    assert len(manifest["candidates"]) == round_count * 4
    for candidate in manifest["candidates"]:
        response = host.post(prefix + f"/games/{game_id}/preload-check", json={
            "request_id": str(uuid4()), "lease_id": lease, "candidate_id": candidate["candidate_id"],
            "ok": True, "waveform": [0.1, 0.3, 0.8, 0.4, 0.2, 0.6, 0.9, 0.5]})
        assert response.status_code == 200, response.text
    clock.value += 5000
    session["app"].state.coordinator.tick()
    return prefix, game_id, lease


def start_round(session, clients, prefix, game_id, lease):
    host, clock = session["host"], session["clock"]
    assert host.post(prefix + "/heartbeat", json={}).status_code == 200
    renewed = host.post(prefix + "/audio-controller", json={"tab_id": "host-tab"}).json()
    assert renewed["lease_id"] == lease
    current = host.get(prefix + "/state").json()["game"]["round"]
    for index, client in enumerate(clients):
        response = client.post(prefix + f'/games/{game_id}/rounds/{current["id"]}/ready', json={
            "readiness_generation": current["readiness_generation"], "lease_id": lease if index == 0 else None})
        assert response.status_code == 200, response.text
    state = host.get(prefix + "/state").json()
    assert state["game"]["phase"] == "countdown"
    clock.value = state["game"]["round"]["starts_at_ms"]
    session["app"].state.coordinator.tick()
    state = host.get(prefix + "/state").json()
    assert state["game"]["phase"] == "answering"
    assert len(state["game"]["round"]["waveform"]) == 8
    with session["app"].state.coordinator.db.read() as conn:
        frozen = json.loads(session["app"].state.coordinator.game.repo.game(conn, game_id)["songs_snapshot_json"])
        current_song = next(value for value in frozen if value["song_key"] == state["game"]["round"]["audio_candidate_id"])
    return state["game"]["round"], current_song


def search_token(client, prefix, title):
    response = client.get(prefix + "/song-search", params={"q": title})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["source"] == "apple"
    assert len(result["songs"]) == 1
    assert set(result["songs"][0]) == {"title", "artist", "artwork_url", "token"}
    return result["songs"][0]["token"]


@pytest.mark.parametrize('callback, origin, requires_shared', [
    ('http://127.0.0.1:8000/api/music/spotify/callback', 'http://192.168.1.80:8000', True),
    ('http://127.0.0.1:8000/api/music/spotify/callback', 'http://127.0.0.1:8000', False),
    ('http://127.0.0.1:8000/api/music/spotify/callback', 'http://localhost:8000', False),
    ('http://[::1]:8000/api/music/spotify/callback', 'http://192.168.1.80:8000', True),
    ('https://game.example/api/music/spotify/callback', 'http://192.168.1.80:8000', False),
])
def test_music_config_explains_lan_sign_in_capability(tmp_path, callback, origin, requires_shared):
    spotify, apple = FakeSpotify(), FakeApple()
    app = create_app(Config(tmp_path, spotify_redirect_uri=callback), background=False,
                     spotify_client=spotify, apple_catalog=apple, music_importer=FakeImporter(spotify, apple))
    with TestClient(app, base_url=origin) as client:
        config = client.get(MUSIC + '/config').json()
        assert config['enabled'] is True
        assert config['requires_shared_url'] is requires_shared
        if requires_shared:
            response = client.post(MUSIC + '/admissions', json={'nickname': 'LAN User', 'character_id': 'coral'})
            assert response.status_code == 503
            assert response.json()['error']['code'] == 'music_shared_url_required'
            assert not spotify.authorizations
            assert 'set-cookie' not in response.headers


def test_pkce_receipt_cookie_wrong_state_cross_browser_and_replay(normal_session):
    session, host = normal_session, normal_session["host"]
    state = begin(host, "Host")
    cookie = next(cookie for cookie in host.cookies.jar if cookie.name == "repeat_music_admission")
    assert cookie.path == MUSIC and cookie._rest["HttpOnly"] is None
    assert cookie._rest["SameSite"] == "lax"
    for browser, supplied_state in ((host, "wrong-state"), (session["new_client"](), state)):
        response = browser.get(MUSIC + "/callback", params={"state": supplied_state, "code": "host-account"}, follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"] == "/?spotify=error"
    assert session["spotify"].exchanges == []
    with session["app"].state.coordinator.db.read() as conn:
        assert conn.execute("SELECT count(*) FROM players").fetchone()[0] == 0
    completed = finish(host, state, "host-account")
    assert completed["status"] == "complete"
    code, verifier = session["spotify"].exchanges[0]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    assert code == "host-account" and challenge == session["spotify"].authorizations[0][1]
    room = completed["admission"]
    prefix = "/api/rooms/" + room["room_id"]
    assert host.get(prefix + "/state").json()["me"]["id"] == room["player_id"]
    assert host.get(MUSIC + "/status").json()["admission"] == room
    replay = host.get(MUSIC + "/callback", params={"state": state, "code": "host-account"}, follow_redirects=False)
    assert replay.headers["location"] == "/?spotify=error"
    assert len(session["spotify"].exchanges) == 1


@pytest.mark.parametrize("failure", ["denied", "allowlist", "minimum"])
def test_failed_imports_never_create_half_a_room_or_player(normal_session, failure):
    session, host = normal_session, normal_session["host"]
    state = begin(host, "Host")
    if failure == "denied":
        response = host.get(MUSIC + "/callback", params={"state": state, "error": "access_denied"}, follow_redirects=False)
        assert response.status_code == 303
        result = await_status(host)
        expected = "music_authorization_denied"
        assert session["spotify"].exchanges == []
    else:
        if failure == "allowlist":
            session["importer"].failures["host-account"] = DomainError("spotify_account_not_allowed", "Account is not approved.", 403)
            expected = "spotify_account_not_allowed"
        else:
            session["importer"].counts["host-account"] = 9
            expected = "music_import_insufficient"
        result = finish(host, state, "host-account")
    assert result["status"] == "failed" and result["error"]["code"] == expected
    assert "admission" not in result
    with session["app"].state.coordinator.db.read() as conn:
        for table in ("rooms", "players", "songs", "player_songs"):
            assert conn.execute("SELECT count(*) FROM " + table).fetchone()[0] == 0


def test_normal_admission_preserves_real_overlap_and_prevents_duplicate_accounts(normal_session):
    session, host = normal_session, normal_session["host"]
    room = admit(host, "Host", "same-account")
    prefix = "/api/rooms/" + room["room_id"]
    other = session["new_client"]()
    assert other.post(prefix + "/join", json={"nickname": "Unsigned"}).json()["error"]["code"] == "music_sign_in_required"
    duplicate = finish(other, begin(other, "Duplicate", room["room_id"]), "same-account")
    assert duplicate["status"] == "failed" and duplicate["error"]["code"] == "music_account_taken"
    peer = admit(other, "Peer", "peer-account", room["room_id"])
    state = host.get(prefix + "/state").json()
    assert len(state["players"]) == 2
    assert all(player["song_count"] == 60 and player["music_status"] == "ready" for player in state["players"])
    assert "source_evidence" not in json.dumps(state) and "account_hash" not in json.dumps(state)
    with session["app"].state.coordinator.db.read() as conn:
        shared = conn.execute("SELECT id FROM songs WHERE room_id=? AND identity_key='isrc:SHARED0'", (room["room_id"],)).fetchall()
        assert len(shared) == 1
        owners = {row[0] for row in conn.execute("SELECT player_id FROM player_songs WHERE song_id=?", (shared[0]["id"],))}
        assert owners == {room["player_id"], peer["player_id"]}
        assert conn.execute("SELECT count(*) FROM players").fetchone()[0] == 2
    assert session["importer"].imports == [("same-account", True), ("same-account", False), ("peer-account", False)]


@pytest.mark.parametrize('normal_session', [False, True], indirect=True, ids=['standard', 'playtest'])
def test_concurrent_pending_imports_cannot_exceed_five_players(normal_session):
    session, host = normal_session, normal_session["host"]
    room = admit(host, "Host", "host-account")
    for number in range(1, 4):
        admit(session["new_client"](), "Guest " + str(number), "account" + str(number), room["room_id"])
    racers = [session["new_client"](), session["new_client"]()]
    states = [begin(browser, "Racer " + str(index), room["room_id"]) for index, browser in enumerate(racers)]
    session["importer"].block_accounts = {"racer0", "racer1"}
    for index, browser in enumerate(racers):
        response = browser.get(MUSIC + "/callback", params={"state": states[index], "code": "racer" + str(index)}, follow_redirects=False)
        assert response.status_code == 303
    assert session["importer"].blocked.wait(2)
    session["importer"].release.set()
    results = [await_status(browser) for browser in racers]
    assert sorted(result["status"] for result in results) == ["complete", "failed"]
    assert next(result for result in results if result["status"] == "failed")["error"]["code"] == "room_full"
    state = host.get("/api/rooms/" + room["room_id"] + "/state").json()
    assert len(state["players"]) == state["room"]["maximum_players"] == 5
    rejected = session["new_client"]().post(MUSIC + "/admissions", json={"nickname": "Sixth", "room_id": room["room_id"]})
    assert rejected.status_code == 409 and rejected.json()["error"]["code"] == "room_full"
    with session["app"].state.coordinator.db.read() as conn:
        assert conn.execute("SELECT count(*) FROM players WHERE room_id=?", (room["room_id"],)).fetchone()[0] == 5
        assert conn.execute("SELECT count(*) FROM player_songs WHERE room_id=?", (room["room_id"],)).fetchone()[0] == 300


@pytest.mark.parametrize('round_count', [5, 10, 15])
@pytest.mark.parametrize('normal_session', [False, True], indirect=True, ids=['five-distinct-accounts', 'two-shared-account'])
def test_normal_game_completes_all_round_settings_private_results_and_rematch(normal_session, round_count):
    session = normal_session
    if session['config'].playtest:
        room = admit(session['host'], 'Host', 'same-account')
        peer = session['new_client']()
        joined = admit(peer, 'Peer', 'same-account', room['room_id'])
        clients = [session['host'], peer]
        player_ids = [room['player_id'], joined['player_id']]
        assert len(set(player_ids)) == 2
        state = clients[0].get('/api/rooms/' + room['room_id'] + '/state').json()
        assert state['room']['minimum_players'] == 2 and state['room']['playtest'] is True
        assert all(player['song_count'] == 60 for player in state['players'])
        c = session['app'].state.coordinator
        with c.db.read() as conn:
            snapshot = c.rooms.snapshot(conn, room['room_id'])
            personal = [song for song in snapshot['songs'] if song['listeners']]
            assert len(personal) == 60
            assert all({owner['player_id'] for owner in song['listeners']} == set(player_ids) for song in personal)
    else:
        room, clients, player_ids = five_players(session)
    prefix, game_id, lease = prepare_game(session, room, round_count)
    totals = {player_id: 0 for player_id in player_ids}
    seen_candidates = set()
    for number in range(1, round_count + 1):
        current, frozen = start_round(session, clients, prefix, game_id, lease)
        assert current["round_number"] == number
        assert current["audio_candidate_id"] not in seen_candidates
        seen_candidates.add(current["audio_candidate_id"])
        listeners = [listener["player_id"] for listener in frozen["listeners"]]
        for index, client in enumerate(clients):
            token = search_token(client, prefix, frozen["title"])
            response = client.post(prefix + f'/games/{game_id}/rounds/{current["id"]}/answers',
                                   json={"song_guess_token": token, "who_player_ids": listeners if index == 0 else []})
            assert response.status_code == 200, response.text
            if index == 0:
                guest_round = clients[1].get(prefix + "/state").json()["game"]["round"]
                assert guest_round["my_answer"] is None and guest_round["reveal"] is None
                assert "audio_candidate_id" not in guest_round
                assert guest_round["submitted_player_ids"] == [player_ids[0]]
        for index, client in enumerate(clients):
            state = client.get(prefix + "/state").json()
            assert state["game"]["phase"] == "reveal"
            reveal = state["game"]["round"]["reveal"]
            assert set(reveal) == {"song", "listener_ids", "my_answer"}
            own = reveal["my_answer"]
            assert own["player_id"] == player_ids[index] and own["song_match"] == "correct"
            assert own["who_player_ids"] == (sorted(listeners) if index == 0 else [])
            assert reveal["song"]["title"] == frozen["title"]
            totals[player_ids[index]] += own["points"]
        phase_end = state["game"]["phase_ends_at_ms"]
        session["clock"].value = phase_end
        session["app"].state.coordinator.tick()
        leaderboard = clients[0].get(prefix + "/state").json()["game"]
        assert leaderboard["phase"] == "leaderboard"
        assert {row["player_id"]: row["score"] for row in leaderboard["leaderboard"]} == totals
        session["clock"].value = leaderboard["phase_ends_at_ms"]
        assert clients[0].post(prefix + "/heartbeat", json={}).status_code == 200
        assert clients[0].post(prefix + "/audio-controller", json={"tab_id": "host-tab"}).json()["lease_id"] == lease
        session["app"].state.coordinator.tick()
    final = clients[0].get(prefix + "/state").json()
    assert final["game"]["status"] == "completed" and final["room"]["state"] == "lobby"
    assert final["game"]["playable_rounds"] == round_count
    with session["app"].state.coordinator.db.read() as conn:
        assert len(session["app"].state.coordinator.game.repo.attempts(conn, game_id)) == round_count
        assert conn.execute("SELECT count(*) FROM answers WHERE game_id=?", (game_id,)).fetchone()[0] == round_count * len(clients)
    anonymous = session["new_client"]()
    history = anonymous.get("/api/room-codes/" + room["code"] + "/history").json()
    assert history["games"][0]["id"] == game_id
    assert "song_guess" not in json.dumps(history) and "who_player_ids" not in json.dumps(history)
    before = len(session["importer"].imports)
    response = clients[0].post(prefix + "/start", json={"request_id": "rematch",
                              "room_revision": final["room"]["revision"], "lease_id": lease})
    assert response.status_code == 200 and response.json()["game_id"] != game_id
    assert len(session["importer"].imports) == before


@pytest.mark.parametrize('normal_session,count', [(False, 2), (True, 1)], indirect=['normal_session'])
def test_start_rejects_rosters_below_the_configured_minimum(normal_session, count):
    session, host = normal_session, normal_session['host']
    room = admit(host, 'Host', 'host-account')
    prefix = '/api/rooms/' + room['room_id']
    if count == 2:
        admit(session['new_client'](), 'Peer', 'peer-account', room['room_id'])
    lease = host.post(prefix + '/audio-controller', json={'tab_id': 'host-tab'}).json()['lease_id']
    state = host.get(prefix + '/state').json()
    minimum = 2 if session['config'].playtest else 3
    assert state['room']['minimum_players'] == minimum
    response = host.post(prefix + '/start', json={'request_id': str(uuid4()),
                         'room_revision': state['room']['revision'], 'lease_id': lease})
    assert response.status_code == 400 and response.json()['error']['code'] == 'player_count'
    assert str(minimum) in response.json()['error']['message']
    with session['app'].state.coordinator.db.read() as conn:
        assert conn.execute('SELECT count(*) FROM games').fetchone()[0] == 0


def test_missing_answer_and_explicit_nobody_differ_at_deadline(normal_session):
    session = normal_session
    room, clients, player_ids = five_players(session)
    prefix, game_id, lease = prepare_game(session, room)
    current, frozen = start_round(session, clients, prefix, game_id, lease)
    token = search_token(clients[0], prefix, frozen["title"])
    response = clients[0].post(prefix + f'/games/{game_id}/rounds/{current["id"]}/answers',
                               json={"song_guess_token": token, "who_player_ids": []})
    assert response.status_code == 200
    session["clock"].value = current["deadline_at_ms"]
    session["app"].state.coordinator.tick()
    own = clients[0].get(prefix + "/state").json()["game"]["round"]["reveal"]["my_answer"]
    missing = clients[1].get(prefix + "/state").json()["game"]["round"]["reveal"]["my_answer"]
    assert own["status"] == "submitted" and own["who_player_ids"] == [] and own["song_match"] == "correct"
    assert missing["status"] == "missing" and missing["who_player_ids"] is None and missing["points"] == 0


def test_search_accepts_catalog_songs_outside_room_and_cross_provider_artist_partial_credit(normal_session):
    session = normal_session
    room, clients, player_ids = five_players(session)
    prefix = "/api/rooms/" + room["room_id"]
    response = clients[0].patch(prefix + "/settings", json={"difficulty": "easy", "decoys_enabled": False})
    assert response.status_code == 200
    prefix, game_id, lease = prepare_game(session, room)
    current, frozen = start_round(session, clients, prefix, game_id, lease)
    outside = song("not-in-any-player-history")
    session["apple"].register([outside])
    with session["app"].state.coordinator.db.read() as conn:
        assert conn.execute("SELECT count(*) FROM songs WHERE room_id=? AND identity_key=?",
                            (room["room_id"], "isrc:" + outside["isrc"])).fetchone()[0] == 0
    token = search_token(clients[0], prefix, outside["title"])
    # Provider changes after selection cannot alter the signed submitted facts.
    session["apple"].catalog[outside["title"].casefold()] = outside | {"title": "Changed provider title"}
    calls = len(session["apple"].queries)
    for index, client in enumerate(clients):
        response = client.post(prefix + f'/games/{game_id}/rounds/{current["id"]}/answers',
                               json={"song_guess_token": token if index == 0 else None, "who_player_ids": []})
        assert response.status_code == 200, response.text
    assert len(session["apple"].queries) == calls
    answer = clients[0].get(prefix + "/state").json()["game"]["round"]["reveal"]["my_answer"]
    assert answer["song_guess"]["title"] == outside["title"]
    assert answer["song_match"] == "artist" and answer["points"] == 50
    assert answer["player_id"] == player_ids[0]


def test_snapshot_artwork_and_metadata_survive_catalog_mutation_and_server_restart(normal_session):
    session = normal_session
    room, clients, player_ids = five_players(session)
    prefix, game_id, lease = prepare_game(session, room)
    current, frozen = start_round(session, clients, prefix, game_id, lease)
    token = search_token(clients[0], prefix, frozen["title"])
    with session["app"].state.coordinator.db.transaction() as conn:
        conn.execute("UPDATE songs SET title='Changed later',artwork_url=NULL WHERE room_id=?", (room["room_id"],))
    for index, client in enumerate(clients):
        response = client.post(prefix + f'/games/{game_id}/rounds/{current["id"]}/answers',
                               json={"song_guess_token": token if index == 0 else None, "who_player_ids": []})
        assert response.status_code == 200
    reveal = clients[0].get(prefix + "/state").json()["game"]["round"]["reveal"]
    assert reveal["song"]["title"] == frozen["title"] and reveal["song"]["artwork_url"] == frozen["artwork_url"]
    assert reveal["my_answer"]["song_match"] == "correct"
    restarted = create_app(session["config"], clock=session["clock"], background=False,
                           spotify_client=session["spotify"], apple_catalog=session["apple"],
                           music_importer=session["importer"])
    with TestClient(restarted) as browser:
        for index, original in enumerate(clients):
            browser.cookies.clear()
            browser.cookies.update(original.cookies)
            restored = browser.get(prefix + "/state").json()
            assert restored["me"]["id"] == player_ids[index]
            assert restored["game"]["status"] == "aborted" and restored["game"]["end_reason"] == "server_restart"
            assert restored["room"]["state"] == "lobby" and len(restored["players"]) == 5
            assert all(player["music_status"] == "ready" and player["song_count"] == 60 for player in restored["players"])
            assert browser.get(MUSIC + "/status").status_code == 401
        with restarted.state.coordinator.db.read() as conn:
            snapshot = json.loads(restarted.state.coordinator.game.repo.game(conn, game_id)["songs_snapshot_json"])
            assert any(value["title"] == frozen["title"] and value["artwork_url"] == frozen["artwork_url"] for value in snapshot)
