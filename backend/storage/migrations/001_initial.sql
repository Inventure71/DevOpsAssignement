PRAGMA foreign_keys = ON;

CREATE TABLE rooms (
    id TEXT PRIMARY KEY NOT NULL,
    code TEXT NOT NULL UNIQUE CHECK (length(code) = 6),
    mode TEXT NOT NULL CHECK (mode IN ('normal', 'demo')),
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    state TEXT NOT NULL DEFAULT 'lobby' CHECK (state IN ('lobby', 'playing')),
    created_at_ms INTEGER NOT NULL,
    last_completed_at_ms INTEGER CHECK (last_completed_at_ms >= created_at_ms)
);

CREATE TABLE players (
    id TEXT PRIMARY KEY NOT NULL,
    room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    nickname TEXT NOT NULL,
    nickname_key TEXT NOT NULL,
    character_id TEXT NOT NULL,
    music_status TEXT NOT NULL CHECK (music_status IN ('authorized', 'ready', 'failed', 'demo')),
    music_provider TEXT,
    session_token_hash TEXT NOT NULL UNIQUE,
    is_host INTEGER NOT NULL CHECK (is_host IN (0, 1)),
    joined_at_ms INTEGER NOT NULL,
    last_seen_at_ms INTEGER NOT NULL,
    CHECK ((music_status = 'demo' AND music_provider IS NULL) OR (music_status != 'demo' AND music_provider IS NOT NULL)),
    UNIQUE (room_id, id),
    UNIQUE (room_id, nickname_key)
);
CREATE UNIQUE INDEX one_room_host ON players(room_id) WHERE is_host = 1;

CREATE TABLE songs (
    id TEXT PRIMARY KEY NOT NULL,
    room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    identity_key TEXT NOT NULL,
    isrc TEXT,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    artists_json TEXT NOT NULL CHECK (json_valid(artists_json) AND json_type(artists_json) = 'array' AND json_array_length(artists_json) >= 1),
    preview_url TEXT,
    artwork_url TEXT,
    UNIQUE (room_id, id),
    UNIQUE (room_id, identity_key)
);

CREATE TABLE demo_catalog (
    id TEXT PRIMARY KEY NOT NULL,
    pool_kind TEXT NOT NULL CHECK (pool_kind IN ('personal', 'decoy')),
    isrc TEXT,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    artists_json TEXT NOT NULL CHECK (json_valid(artists_json) AND json_type(artists_json) = 'array' AND json_array_length(artists_json) >= 1),
    preview_url TEXT NOT NULL,
    artwork_url TEXT
);

CREATE TABLE player_songs (
    room_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    song_id TEXT NOT NULL,
    familiarity TEXT NOT NULL CHECK (familiarity IN ('easy', 'medium', 'hard')),
    PRIMARY KEY (player_id, song_id),
    FOREIGN KEY (room_id, player_id) REFERENCES players(room_id, id) ON DELETE CASCADE,
    FOREIGN KEY (room_id, song_id) REFERENCES songs(room_id, id) ON DELETE CASCADE
);

CREATE TABLE games (
    id TEXT PRIMARY KEY NOT NULL,
    room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE RESTRICT,
    room_revision INTEGER NOT NULL CHECK (room_revision >= 0),
    start_request_id TEXT NOT NULL,
    state_version INTEGER NOT NULL DEFAULT 0 CHECK (state_version >= 0),
    status TEXT NOT NULL CHECK (status IN ('preparing', 'playing', 'completed', 'aborted')),
    phase TEXT NOT NULL CHECK (phase IN ('setup', 'ready', 'countdown', 'answering', 'reveal', 'leaderboard', 'finished')),
    settings_json TEXT NOT NULL CHECK (json_valid(settings_json) AND json_type(settings_json) = 'object'),
    songs_snapshot_json TEXT NOT NULL CHECK (json_valid(songs_snapshot_json) AND json_type(songs_snapshot_json) = 'array'),
    round_plan_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(round_plan_json) AND json_type(round_plan_json) = 'array'),
    started_at_ms INTEGER NOT NULL,
    prepared_at_ms INTEGER CHECK (prepared_at_ms >= started_at_ms),
    phase_ends_at_ms INTEGER,
    end_reason TEXT,
    ended_at_ms INTEGER CHECK (ended_at_ms >= started_at_ms),
    UNIQUE (room_id, start_request_id),
    CHECK ((status IN ('preparing', 'playing') AND ended_at_ms IS NULL AND end_reason IS NULL AND phase != 'finished')
        OR (status IN ('completed', 'aborted') AND ended_at_ms IS NOT NULL AND end_reason IS NOT NULL AND phase = 'finished' AND phase_ends_at_ms IS NULL)),
    CHECK (status != 'preparing' OR phase IN ('setup', 'ready')),
    CHECK (status != 'playing' OR phase IN ('ready', 'countdown', 'answering', 'reveal', 'leaderboard')),
    CHECK (status NOT IN ('playing', 'completed') OR prepared_at_ms IS NOT NULL),
    CHECK (phase NOT IN ('setup', 'countdown', 'reveal', 'leaderboard') OR phase_ends_at_ms IS NOT NULL),
    CHECK (phase_ends_at_ms IS NULL OR phase_ends_at_ms >= started_at_ms)
);
CREATE INDEX games_by_room ON games(room_id);
CREATE UNIQUE INDEX one_active_game ON games(room_id) WHERE status IN ('preparing', 'playing');

CREATE TABLE game_players (
    game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    player_id TEXT NOT NULL,
    nickname TEXT NOT NULL,
    character_id TEXT NOT NULL,
    is_host INTEGER NOT NULL CHECK (is_host IN (0, 1)),
    final_score INTEGER CHECK (final_score >= 0),
    final_rank INTEGER CHECK (final_rank >= 1),
    PRIMARY KEY (game_id, player_id),
    CHECK ((final_score IS NULL) = (final_rank IS NULL))
);
CREATE UNIQUE INDEX one_game_host ON game_players(game_id) WHERE is_host = 1;

CREATE TABLE rounds (
    id TEXT PRIMARY KEY NOT NULL,
    game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    round_number INTEGER NOT NULL CHECK (round_number BETWEEN 1 AND 15),
    attempt INTEGER NOT NULL DEFAULT 1 CHECK (attempt BETWEEN 1 AND 4),
    status TEXT NOT NULL CHECK (status IN ('ready', 'playing', 'revealed', 'void')),
    song_key TEXT NOT NULL,
    options_json TEXT NOT NULL CHECK (json_valid(options_json) AND json_type(options_json) = 'array' AND json_array_length(options_json) = 4),
    difficulty TEXT NOT NULL CHECK (difficulty IN ('easy', 'medium', 'hard', 'decoy')),
    picked_player_id TEXT,
    starts_at_ms INTEGER,
    deadline_at_ms INTEGER,
    readiness_generation INTEGER NOT NULL DEFAULT 1 CHECK (readiness_generation >= 1),
    readiness_deadline_at_ms INTEGER NOT NULL,
    ready_player_ids_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(ready_player_ids_json) AND json_type(ready_player_ids_json) = 'array'),
    excluded_player_ids_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(excluded_player_ids_json) AND json_type(excluded_player_ids_json) = 'array'),
    revealed_at_ms INTEGER,
    void_reason TEXT,
    UNIQUE (game_id, id),
    UNIQUE (game_id, round_number, attempt),
    UNIQUE (game_id, song_key),
    FOREIGN KEY (game_id, picked_player_id) REFERENCES game_players(game_id, player_id),
    CHECK ((difficulty = 'decoy' AND picked_player_id IS NULL) OR (difficulty != 'decoy' AND picked_player_id IS NOT NULL)),
    CHECK ((starts_at_ms IS NULL AND deadline_at_ms IS NULL) OR (starts_at_ms IS NOT NULL AND deadline_at_ms IS NOT NULL AND deadline_at_ms > starts_at_ms)),
    CHECK (status NOT IN ('playing', 'revealed') OR starts_at_ms IS NOT NULL),
    CHECK ((status = 'revealed' AND revealed_at_ms IS NOT NULL AND revealed_at_ms >= starts_at_ms) OR (status != 'revealed' AND revealed_at_ms IS NULL)),
    CHECK ((status = 'void' AND void_reason IS NOT NULL) OR (status != 'void' AND void_reason IS NULL))
);
CREATE UNIQUE INDEX one_active_round ON rounds(game_id) WHERE status IN ('ready', 'playing');

CREATE TABLE answers (
    game_id TEXT NOT NULL,
    round_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('submitted', 'missing')),
    song_option INTEGER CHECK (song_option BETWEEN 0 AND 3),
    who_mode TEXT NOT NULL CHECK (who_mode IN ('blank', 'nobody', 'players')),
    who_player_ids_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(who_player_ids_json) AND json_type(who_player_ids_json) = 'array'),
    received_at_ms INTEGER,
    points INTEGER CHECK (points >= 0),
    PRIMARY KEY (round_id, player_id),
    FOREIGN KEY (game_id, round_id) REFERENCES rounds(game_id, id) ON DELETE CASCADE,
    FOREIGN KEY (game_id, player_id) REFERENCES game_players(game_id, player_id) ON DELETE CASCADE,
    CHECK ((who_mode = 'players' AND json_array_length(who_player_ids_json) > 0) OR (who_mode != 'players' AND json_array_length(who_player_ids_json) = 0)),
    CHECK ((status = 'submitted' AND received_at_ms IS NOT NULL AND who_mode IN ('nobody', 'players')) OR (status = 'missing' AND received_at_ms IS NULL AND song_option IS NULL AND who_mode = 'blank' AND points IS NOT NULL AND points = 0))
);

CREATE TABLE game_commands (
    game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    request_id TEXT NOT NULL,
    actor_player_id TEXT NOT NULL,
    command_type TEXT NOT NULL CHECK (command_type IN ('start', 'end', 'preload_check', 'retry', 'continue', 'audio_failure', 'leave')),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json) AND json_type(payload_json) = 'object'),
    result_json TEXT NOT NULL CHECK (json_valid(result_json) AND json_type(result_json) = 'object'),
    accepted_at_ms INTEGER NOT NULL,
    PRIMARY KEY (game_id, request_id),
    FOREIGN KEY (game_id, actor_player_id) REFERENCES game_players(game_id, player_id)
);
