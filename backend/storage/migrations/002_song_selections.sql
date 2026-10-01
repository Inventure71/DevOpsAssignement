CREATE TABLE rounds_new (
    id TEXT PRIMARY KEY NOT NULL,
    game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    round_number INTEGER NOT NULL CHECK (round_number BETWEEN 1 AND 15),
    attempt INTEGER NOT NULL DEFAULT 1 CHECK (attempt BETWEEN 1 AND 4),
    status TEXT NOT NULL CHECK (status IN ('ready', 'playing', 'revealed', 'void')),
    song_key TEXT NOT NULL,
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

CREATE TABLE answers_new (
    game_id TEXT NOT NULL,
    round_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('submitted', 'missing')),
    song_guess_json TEXT NOT NULL DEFAULT 'null' CHECK (json_valid(song_guess_json) AND json_type(song_guess_json) IN ('object','null')),
    who_mode TEXT NOT NULL CHECK (who_mode IN ('blank', 'nobody', 'players')),
    who_player_ids_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(who_player_ids_json) AND json_type(who_player_ids_json) = 'array'),
    received_at_ms INTEGER,
    points INTEGER CHECK (points >= 0),
    PRIMARY KEY (round_id, player_id),
    FOREIGN KEY (game_id, round_id) REFERENCES rounds_new(game_id, id) ON DELETE CASCADE,
    FOREIGN KEY (game_id, player_id) REFERENCES game_players(game_id, player_id) ON DELETE CASCADE,
    CHECK ((who_mode = 'players' AND json_array_length(who_player_ids_json) > 0) OR (who_mode != 'players' AND json_array_length(who_player_ids_json) = 0)),
    CHECK ((status = 'submitted' AND received_at_ms IS NOT NULL AND who_mode IN ('nobody', 'players')) OR (status = 'missing' AND received_at_ms IS NULL AND json_type(song_guess_json) = 'null' AND who_mode = 'blank' AND points IS NOT NULL AND points = 0))
);

INSERT INTO rounds_new SELECT id,game_id,round_number,attempt,status,song_key,difficulty,picked_player_id,starts_at_ms,deadline_at_ms,readiness_generation,readiness_deadline_at_ms,ready_player_ids_json,excluded_player_ids_json,revealed_at_ms,void_reason FROM rounds;
INSERT INTO answers_new (game_id,round_id,player_id,status,song_guess_json,who_mode,who_player_ids_json,received_at_ms,points)
SELECT a.game_id,a.round_id,a.player_id,a.status,
       COALESCE((SELECT s.value FROM json_each(g.songs_snapshot_json) s
                 WHERE json_extract(s.value,'$.song_key') = json_extract(r.options_json,'$[' || a.song_option || ']')), 'null'),
       a.who_mode,a.who_player_ids_json,a.received_at_ms,a.points
FROM answers a JOIN rounds r ON r.id=a.round_id JOIN games g ON g.id=a.game_id;
DROP TABLE answers;
DROP TABLE rounds;
ALTER TABLE rounds_new RENAME TO rounds;
ALTER TABLE answers_new RENAME TO answers;
CREATE UNIQUE INDEX one_active_round ON rounds(game_id) WHERE status IN ('ready','playing');
