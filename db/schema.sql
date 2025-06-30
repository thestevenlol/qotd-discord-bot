-- ==============================================================
--  project_schema.sql
-- ==============================================================

PRAGMA foreign_keys = ON;

--------------------------------------------------------------
-- 1.  Discord objects (channels & roles)
--------------------------------------------------------------
CREATE TABLE IF NOT EXISTS guild_channels (
    id           INTEGER PRIMARY KEY,          -- surrogate key
    guild_id     TEXT    NOT NULL,
    channel_id   TEXT    NOT NULL UNIQUE,      -- Discord snowflake
    name         TEXT
);

CREATE TABLE IF NOT EXISTS guild_roles (
    id        INTEGER PRIMARY KEY,
    guild_id  TEXT    NOT NULL,
    role_id   TEXT    NOT NULL UNIQUE,
    name      TEXT
);

--------------------------------------------------------------
-- 2.  Message schedules
--------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schedules (
    id            INTEGER PRIMARY KEY,
    channel_fk    INTEGER NOT NULL REFERENCES guild_channels(id) ON DELETE CASCADE,
    role_fk       INTEGER     REFERENCES guild_roles(id)   ON DELETE SET NULL,
    label         TEXT,                                -- friendly name (e.g. “Daily Quiz”)
    send_time     TEXT    NOT NULL,                    -- stored as ‘HH:MM’, 24-hour
    frequency     TEXT    NOT NULL CHECK (frequency IN ('daily','weekly','monthly','once')),
    weekday       INTEGER     CHECK (weekday BETWEEN 0 AND 6), -- Mon=0 … Sun=6; only for ‘weekly’
    next_run      DATETIME NOT NULL,                   -- pre-computed by your bot
    active        INTEGER NOT NULL DEFAULT 1           -- 1=enabled, 0=paused
);

CREATE INDEX idx_schedules_next ON schedules(next_run);

--------------------------------------------------------------
-- 3.  Question packs & cards
--------------------------------------------------------------
CREATE TABLE IF NOT EXISTS packs (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS cards (
    id        INTEGER PRIMARY KEY,
    pack_fk   INTEGER NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
    question  TEXT    NOT NULL,
    sort_order INTEGER,                               -- optional manual ordering
    UNIQUE (pack_fk, question)
);

--------------------------------------------------------------
-- 4.  Sent-history (guarantees no repeats until full cycle)
--------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sent_cards (
    id           INTEGER PRIMARY KEY,
    schedule_fk  INTEGER NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
    card_fk      INTEGER NOT NULL REFERENCES cards(id)     ON DELETE CASCADE,
    sent_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (schedule_fk, card_fk)
);

--------------------------------------------------------------
-- 5.  Community suggestions (staff moderation)
--------------------------------------------------------------
CREATE TABLE IF NOT EXISTS card_suggestions (
    id                INTEGER PRIMARY KEY,
    guild_id          TEXT        NOT NULL,
    suggester_id      TEXT        NOT NULL,               -- user snowflake
    suggested_text    TEXT        NOT NULL,
    target_pack_fk    INTEGER     REFERENCES packs(id)    ON DELETE SET NULL,
    status            TEXT        NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','accepted','rejected')),
    decided_by_id     TEXT,
    decided_at        DATETIME
);

--------------------------------------------------------------
-- 6.  Trigger: auto-promote accepted suggestions into cards
--------------------------------------------------------------
CREATE TRIGGER promote_suggestion
AFTER UPDATE OF status ON card_suggestions
WHEN NEW.status = 'accepted'
BEGIN
    INSERT OR IGNORE INTO cards (pack_fk, question)
    VALUES (NEW.target_pack_fk,
            NEW.suggested_text);
END;
