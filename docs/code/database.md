# Database and application core

`config.py`, `web.py`, `schema.py`, `migrations/` and the entry point `app.py`: where state lives, the one Flask app every module registers routes on, the per-request database connection with its guards, and bringing the database to the current schema at start-up. Taken over from Ophir Figures with names changed.

## Public interface

### app.py

- `gunicorn app:app` in the container (2 workers, 4 threads, port 8080); `python app.py` starts Flask's debug server on 0.0.0.0:8080. It re-exports `ophir_mangas.app` and calls `web.require_secret_key`: imported (gunicorn, `python -c "import app"` in docker-entrypoint.sh) it exits without a `SECRET_KEY`, run as the debug server it only logs a warning. The tests and the demo server (tests/frontend/serve.py) import `ophir_mangas` directly and are not checked.
- Importing `ophir_mangas` (or any submodule) imports every route module and calls `schema.init_database()`.

### config.py

Imports nothing from the package.

- `ROOT` - repository root; `DB_PATH` - env `DATABASE_PATH`, default `<ROOT>/ophir-mangas.db`; `DATA_DIR` - its directory; `IMAGE_DIR` (`volume-images/`) and `THUMB_DIR` (`volume-thumbnails/`) next to it.
- `OAUTH_CONFIG_PATH`, `OAUTH_PROVIDER_KEY = "generic"`, `OAUTH_CONFIG_DEFAULTS` (see auth.md); `AUTH_MODE`, `AUTH_PATH`, `AUTH_HOME` (shared-auth.md); `APP_NAME`; `CURRENCY = "EUR"` (every amount a user enters).
- `now_iso()` (UTC, whole seconds, ISO 8601 with offset: the format of every `*_at` column), `today_iso()`, `jload(value, default)`, `slug(text)`.

### web.py

- `app` - the single Flask app (`OphirMangas`, `root_path=ROOT`). `db()` - one connection per app context: `sqlite3.Row`, `PRAGMA foreign_keys = ON`, `busy_timeout` 10 s, SQL function `search_score`. Nothing auto-commits.
- `login_required`, `admin_required`, `user_id()` - a stale session is cleared; `/api/...` gets 401/403 JSON.
- `asset_url(filename)` (Jinja global) - static URL with `?v=<12 hex of the content hash>`; such a URL is cached for a year. Text files and JSON/HTML answers are gzipped.
- Hooks: `reject_cross_site_writes` (403 for a write whose `Sec-Fetch-Site` is not `same-origin`/`none`, or whose `Origin` is another host), `compress_answer`, `IntegrityError` -> 400 JSON on `/api/...`.
- Settings: `SECRET_KEY` from env, empty or missing falls back to the public `DEVELOPMENT_SECRET_KEY`; `require_secret_key(debug=False)` raises `SystemExit` with a German message while that fallback is in use; `TRUST_PROXY_HEADERS` in (`1`, `true`, `yes`) wraps the app in `behind_proxy`, `ProxyFix(x_for=1, x_proto=1, x_host=1, x_prefix=1)`: `X-Forwarded-Prefix` (a proxy serving the app under a path it strips, e.g. `/mangas`) becomes the script root that `url_for` and the templates' `<html data-root>` carry; `SESSION_COOKIE_SAMESITE = "Lax"`; the session cookie is `ophir_mangas_session`, signed by `SessionCookies` with the salt `ophir-mangas-session` instead of Flask's default (see auth.md).
- `GET /health` (no auth) - `{"status", "database", "schema_version", "schema_expected"}`.

### schema.py

- `init_database()` - WAL mode, `migrations.migrate()`, then under `BEGIN IMMEDIATE`: `seed_database()` (the account `admin`/`admin` on an empty database, nothing else) and `ensure_user_lists()`.
- `ensure_user_lists(connection, user_id=None)` - gives every account (or one) its default wishlist `Wunschliste` if it has none. Called after an account is created (admin, SSO auto-provisioning, shared sign-in, restore).

### migrations/

- `MIGRATIONS` - the ordered list, so far only `m0001_baseline` (every table below). `migrate(connection, path)` applies each missing one in its own transaction and records it in `schema_migrations`; safe with several processes starting together; refuses a database with a version it does not know; copies an existing database first (`<db>.before-migration-NNNN`, two kept). `status(connection)` - (version, expected).

## Tables (m0001)

| Table | Holds | Notes |
| --- | --- | --- |
| `users`, `user_settings`, `app_settings` | accounts, per-account JSON settings, app-wide settings (`oauth_config`) | `(oauth_provider, oauth_subject)` unique when linked; `auth_subject` (unique where not empty): the master's account id in slave mode |
| `login_failures` | failed password sign-ins: `ip`, `username`, `failed_at` | indexes per address and per username ([auth.md](auth.md)) |
| `series` | the works: titles, `authors`, `genres` (comma lists), `demographic`, `status`, `original_volumes`, `start_year`, `anilist_id`, picture | `created_by` SET NULL when the account goes |
| `editions` | a series' publications: `title` (printed, if it differs), `label` (Perfect Edition), `publisher`, `language` (ISO 639-1), `format`, `status`, `volume_count`, `list_price` + `currency` | `series_id` NOT NULL; no cascade: deleting is done in code ([catalog.md](catalog.md)) |
| `volumes` | an edition's books: `number` (REAL, NULL = special volume), `title`, `variant`, `isbn`, `release_date` (ISO, may be partial), `list_price` + `currency`, `pages`, cover | indexes `(edition_id, number)`, `isbn`, `release_date` |
| `price_observations` | market values per volume, newest = current | CASCADE with the volume |
| `collection_entries` | copies: quantity, `condition` (`new`/`very_good`/`reading_marks`/`damaged`), `first_printing`, `extras`, purchase data, location, notes, `preorder_id` | CASCADE with the user; `preorder_id` SET NULL |
| `volume_reads` | read marks `(user_id, volume_id, read_at)` | primary key per account and volume |
| `series_reading` | reading status per account and series (`planned`/`reading`/`paused`/`dropped`/`finished`) | CHECK on the status |
| `collected_editions` | "Sammle ich" per account and edition | set by hand only |
| `watchlists`, `watchlist_entries` | wishlists (one `is_default` per account); an entry has `volume_id` or `edition_id` (CHECK: exactly one), `target_price`, `note` | unique per list and volume, per list and edition |
| `preorders`, `preorder_events` | preorders of a volume (status CHECK), their history | CASCADE with the user / the preorder |
| `import_operations` | restores with the ids they added, for undo | CASCADE with the user |

Deleting an account therefore needs no code beyond `DELETE FROM users`.

## Dependencies

- `ophir_mangas.search` - `score` registered as `search_score`
- Flask, orjson, werkzeug (password hashes, ProxyFix)

## Decisions and assumptions

- One baseline with every table, including what Figures added in later migrations (login throttle, `auth_subject`): there is no older Ophir Mangas database to upgrade. From the first release on, a schema change is a new migration.
- Every user-entered amount is in EUR; a list price keeps the currency it was published in (yen for a Japanese edition) and counts towards the collection's value only in euros.
