-- Keep verified account identity while explicitly exempting playtest admissions.
ALTER TABLE players ADD COLUMN shared_music_account INTEGER NOT NULL DEFAULT 0
    CHECK (shared_music_account IN (0, 1));
DROP INDEX distinct_room_music_accounts;
CREATE UNIQUE INDEX distinct_room_music_accounts
    ON players(room_id, music_provider, music_account_hash)
    WHERE music_account_hash IS NOT NULL AND shared_music_account = 0;
