-- Preparing an upcoming round must not change the current scored attempt.
CREATE TABLE game_round_preparations (
    game_id TEXT PRIMARY KEY NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    id TEXT UNIQUE NOT NULL,
    round_number INTEGER NOT NULL CHECK (round_number BETWEEN 1 AND 15),
    attempt INTEGER NOT NULL CHECK (attempt BETWEEN 1 AND 4),
    song_key TEXT NOT NULL,
    difficulty TEXT NOT NULL CHECK (difficulty IN ('easy', 'medium', 'hard', 'decoy')),
    picked_player_id TEXT,
    readiness_generation INTEGER NOT NULL CHECK (readiness_generation >= 1),
    acknowledgements_json TEXT NOT NULL DEFAULT '{}' CHECK (
        json_valid(acknowledgements_json) AND json_type(acknowledgements_json) = 'object'
    ),
    FOREIGN KEY (game_id, picked_player_id) REFERENCES game_players(game_id, player_id),
    CHECK ((difficulty = 'decoy' AND picked_player_id IS NULL)
        OR (difficulty != 'decoy' AND picked_player_id IS NOT NULL))
);
