"""The first schema of Ophir Mangas.

Frozen: a later change to the schema is a new migration, never an edit here.
"""

NAME = "baseline"

TABLES = """
CREATE TABLE users (
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL,
  password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user', created_at TEXT NOT NULL,
  email TEXT NOT NULL DEFAULT '', oauth_provider TEXT NOT NULL DEFAULT '', oauth_subject TEXT NOT NULL DEFAULT '',
  -- The master's account id when the app takes its sign-in from another Ophir app (shared_auth.py).
  auth_subject TEXT NOT NULL DEFAULT ''
);
-- Only rows linked to an identity of the SSO provider.
CREATE UNIQUE INDEX idx_users_oauth_identity ON users(oauth_provider,oauth_subject) WHERE oauth_subject != '';
CREATE UNIQUE INDEX idx_users_auth_subject ON users(auth_subject) WHERE auth_subject != '';

-- Failed password sign-ins, so POST /login can turn away guessing (auth.py).
CREATE TABLE login_failures (
  ip TEXT NOT NULL, username TEXT NOT NULL, failed_at TEXT NOT NULL
);
CREATE INDEX idx_login_failures_ip ON login_failures(ip, failed_at);
CREATE INDEX idx_login_failures_username ON login_failures(username, failed_at);

CREATE TABLE user_settings (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, key TEXT NOT NULL, value TEXT NOT NULL,
  PRIMARY KEY(user_id, key)
);
CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);

-- The catalogue, shared by every account: series -> editions -> volumes (docs/adr/0001).
-- A series is the work, whoever publishes it in whatever language.
CREATE TABLE series (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  original_title TEXT NOT NULL DEFAULT '',
  alt_titles TEXT NOT NULL DEFAULT '',
  authors TEXT NOT NULL DEFAULT '',
  genres TEXT NOT NULL DEFAULT '',
  demographic TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT '',
  original_volumes INTEGER,
  start_year INTEGER,
  description TEXT NOT NULL DEFAULT '',
  source_url TEXT NOT NULL DEFAULT '',
  image_url TEXT NOT NULL DEFAULT '',
  image_key TEXT NOT NULL DEFAULT '',
  anilist_id INTEGER,
  attributes TEXT NOT NULL DEFAULT '{}',
  created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_series_anilist ON series(anilist_id) WHERE anilist_id IS NOT NULL;

-- One publication of a series: one publisher, one language, one format, its own numbering.
-- title is what is printed on it when that differs from the series' title.
CREATE TABLE editions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  series_id INTEGER NOT NULL REFERENCES series(id),
  title TEXT NOT NULL DEFAULT '',
  label TEXT NOT NULL DEFAULT '',
  publisher TEXT NOT NULL DEFAULT '',
  language TEXT NOT NULL DEFAULT 'de',
  format TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT '',
  volume_count INTEGER,
  list_price REAL,
  currency TEXT NOT NULL DEFAULT 'EUR',
  description TEXT NOT NULL DEFAULT '',
  source_url TEXT NOT NULL DEFAULT '',
  created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_editions_series ON editions(series_id);

-- One book of an edition. number is NULL for a special volume (fanbook); a variant (Limited
-- Edition) is a row of its own with the same number as the standard volume.
CREATE TABLE volumes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  edition_id INTEGER NOT NULL REFERENCES editions(id),
  number REAL,
  title TEXT NOT NULL DEFAULT '',
  variant TEXT NOT NULL DEFAULT '',
  isbn TEXT NOT NULL DEFAULT '',
  release_date TEXT NOT NULL DEFAULT '',
  list_price REAL,
  currency TEXT NOT NULL DEFAULT 'EUR',
  pages INTEGER,
  description TEXT NOT NULL DEFAULT '',
  source_url TEXT NOT NULL DEFAULT '',
  image_url TEXT NOT NULL DEFAULT '',
  image_key TEXT NOT NULL DEFAULT '',
  attributes TEXT NOT NULL DEFAULT '{}',
  created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_volumes_edition ON volumes(edition_id, number);
CREATE INDEX idx_volumes_isbn ON volumes(isbn);
CREATE INDEX idx_volumes_release ON volumes(release_date);

-- Market values: one row per value someone entered; the newest is the current one.
CREATE TABLE price_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  volume_id INTEGER NOT NULL REFERENCES volumes(id) ON DELETE CASCADE,
  amount REAL NOT NULL, currency TEXT NOT NULL DEFAULT 'EUR',
  source TEXT NOT NULL DEFAULT 'manual', note TEXT NOT NULL DEFAULT '',
  user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  observed_at TEXT NOT NULL
);
CREATE INDEX idx_prices_volume ON price_observations(volume_id, observed_at DESC, id DESC);

CREATE TABLE preorders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  volume_id INTEGER NOT NULL REFERENCES volumes(id),
  status TEXT NOT NULL DEFAULT 'ordered' CHECK(status IN ('ordered','paid','shipped','delivered','cancelled')),
  shop TEXT NOT NULL DEFAULT '',
  order_number TEXT NOT NULL DEFAULT '',
  ordered_at TEXT NOT NULL DEFAULT '',
  quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity > 0),
  price REAL,
  shipping REAL,
  paid REAL NOT NULL DEFAULT 0,
  expected_release TEXT NOT NULL DEFAULT '',
  tracking TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  delivered_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_preorders_user ON preorders(user_id, status);
CREATE INDEX idx_preorders_volume ON preorders(volume_id);
-- What happened to a preorder: status changes, payments and moved release dates.
CREATE TABLE preorder_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  preorder_id INTEGER NOT NULL REFERENCES preorders(id) ON DELETE CASCADE,
  kind TEXT NOT NULL, old_value TEXT NOT NULL DEFAULT '', new_value TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX idx_preorder_events ON preorder_events(preorder_id, id);

-- Copies: one row per group of copies of a volume with the same condition and purchase.
CREATE TABLE collection_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  volume_id INTEGER NOT NULL REFERENCES volumes(id),
  quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity > 0),
  condition TEXT NOT NULL DEFAULT 'new' CHECK(condition IN ('new','very_good','reading_marks','damaged')),
  first_printing INTEGER NOT NULL DEFAULT 0,
  extras TEXT NOT NULL DEFAULT '',
  purchase_price REAL,
  purchased_at TEXT NOT NULL DEFAULT '',
  shop TEXT NOT NULL DEFAULT '',
  location TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  preorder_id INTEGER REFERENCES preorders(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_collection_user ON collection_entries(user_id, volume_id);
CREATE INDEX idx_collection_volume ON collection_entries(volume_id);
CREATE INDEX idx_collection_preorder ON collection_entries(preorder_id) WHERE preorder_id IS NOT NULL;

-- Read marks: an account has read a volume, owned or not.
CREATE TABLE volume_reads (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  volume_id INTEGER NOT NULL REFERENCES volumes(id),
  read_at TEXT NOT NULL,
  PRIMARY KEY(user_id, volume_id)
);
CREATE INDEX idx_volume_reads_volume ON volume_reads(volume_id);

-- Where an account stands with a series (the story, whichever edition it reads).
CREATE TABLE series_reading (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  series_id INTEGER NOT NULL REFERENCES series(id),
  status TEXT NOT NULL CHECK(status IN ('planned','reading','paused','dropped','finished')),
  updated_at TEXT NOT NULL,
  PRIMARY KEY(user_id, series_id)
);
CREATE INDEX idx_series_reading_series ON series_reading(series_id);

-- Editions an account says it collects ("Sammle ich"); only ever set by hand.
CREATE TABLE collected_editions (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  edition_id INTEGER NOT NULL REFERENCES editions(id),
  created_at TEXT NOT NULL,
  PRIMARY KEY(user_id, edition_id)
);
CREATE INDEX idx_collected_editions_edition ON collected_editions(edition_id);

CREATE TABLE watchlists (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL, is_default INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
  UNIQUE(user_id, name)
);
-- An entry wishes for one volume or a whole edition.
CREATE TABLE watchlist_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  list_id INTEGER NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
  volume_id INTEGER REFERENCES volumes(id),
  edition_id INTEGER REFERENCES editions(id),
  target_price REAL, note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
  CHECK((volume_id IS NULL) != (edition_id IS NULL)),
  UNIQUE(list_id, volume_id),
  UNIQUE(list_id, edition_id)
);
CREATE INDEX idx_watchlist_entries_volume ON watchlist_entries(volume_id) WHERE volume_id IS NOT NULL;
CREATE INDEX idx_watchlist_entries_edition ON watchlist_entries(edition_id) WHERE edition_id IS NOT NULL;

-- Restores of a JSON backup, so the latest can be taken back.
CREATE TABLE import_operations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL, changes TEXT NOT NULL, undone_at TEXT
);
"""


def apply(connection, context):
    context.run_script(TABLES)
