-- Naad Katha Studio database (Cloudflare D1 / SQLite)
-- A "channel" is the top-level unit, so more channels can be added later.

CREATE TABLE IF NOT EXISTS channels (
  id            TEXT PRIMARY KEY,          -- e.g. 'naad-katha'
  name          TEXT NOT NULL,
  timezone      TEXT NOT NULL DEFAULT 'Asia/Kolkata',
  post_time     TEXT NOT NULL DEFAULT '18:00',
  last_sync_at  TEXT
);

CREATE TABLE IF NOT EXISTS members (
  channel_id  TEXT NOT NULL,
  email       TEXT NOT NULL,                -- lower-case
  name        TEXT,
  role        TEXT NOT NULL CHECK (role IN ('owner','manager','editor','viewer')),
  added_by    TEXT,
  added_at    TEXT NOT NULL,
  PRIMARY KEY (channel_id, email)
);

CREATE TABLE IF NOT EXISTS posts (
  id           TEXT PRIMARY KEY,            -- channel_id + ':' + folder
  channel_id   TEXT NOT NULL,
  folder       TEXT NOT NULL,               -- <slug>_<DDMMYY>
  slug         TEXT NOT NULL,
  post_date    TEXT,                        -- YYYY-MM-DD, NULL when parked
  title        TEXT,
  hook         TEXT,
  description  TEXT,
  settings     TEXT,
  structure    TEXT,                        -- script / structure section, markdown
  beats_json   TEXT,                        -- [{cap:[...], img}] simplified
  first_line   TEXT,                        -- first line of upload-text.md
  video_key    TEXT,
  video_sha    TEXT,
  video_bytes  INTEGER,
  cover_key    TEXT,
  folder_mtime TEXT,
  updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS posts_channel_date ON posts(channel_id, post_date);

-- One row per post: the latest approval decision made in the app and
-- whether the sync job has written it into upload-text.md yet.
CREATE TABLE IF NOT EXISTS approvals (
  post_id      TEXT PRIMARY KEY,
  state        TEXT NOT NULL CHECK (state IN ('approved','unapproved')),
  by_email     TEXT NOT NULL,
  by_name      TEXT,
  role         TEXT NOT NULL,
  at           TEXT NOT NULL,
  video_sha    TEXT,
  write_state  TEXT NOT NULL DEFAULT 'pending' CHECK (write_state IN ('pending','written','failed')),
  write_msg    TEXT,
  written_at   TEXT
);

CREATE TABLE IF NOT EXISTS notes (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id   TEXT NOT NULL,
  email     TEXT NOT NULL,
  name      TEXT,
  text      TEXT NOT NULL,
  at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  channel_id  TEXT NOT NULL,
  post_id     TEXT,
  email       TEXT,
  kind        TEXT NOT NULL,
  detail      TEXT,
  at          TEXT NOT NULL
);
