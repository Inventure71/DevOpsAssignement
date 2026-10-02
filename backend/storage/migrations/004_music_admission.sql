ALTER TABLE players ADD COLUMN music_account_hash TEXT;
CREATE UNIQUE INDEX distinct_room_music_accounts
    ON players(room_id, music_provider, music_account_hash)
    WHERE music_account_hash IS NOT NULL;
ALTER TABLE songs ADD COLUMN pool_kind TEXT NOT NULL DEFAULT 'personal'
    CHECK (pool_kind IN ('personal', 'decoy'));
