-- Keep the character_id API/storage field; its value now names a blob color.
-- Historical cosmetic identities change representation without changing scores.
UPDATE players SET character_id = CASE character_id
    WHEN 'vinyl' THEN 'coral'
    WHEN 'bolt' THEN 'periwinkle'
    WHEN 'moon' THEN 'lavender'
    WHEN 'sun' THEN 'lemon'
    WHEN 'ghost' THEN 'lilac'
    WHEN 'flower' THEN 'sage'
    WHEN 'wave' THEN 'sky'
    WHEN 'star' THEN 'rose'
    ELSE character_id END;

UPDATE game_players SET character_id = CASE character_id
    WHEN 'vinyl' THEN 'coral'
    WHEN 'bolt' THEN 'periwinkle'
    WHEN 'moon' THEN 'lavender'
    WHEN 'sun' THEN 'lemon'
    WHEN 'ghost' THEN 'lilac'
    WHEN 'flower' THEN 'sage'
    WHEN 'wave' THEN 'sky'
    WHEN 'star' THEN 'rose'
    ELSE character_id END;
