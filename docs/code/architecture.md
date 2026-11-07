# Architecture

Ophir Mangas is one Flask application with one SQLite database, served by gunicorn in a single container. There are no background jobs: everything happens inside requests. It was built from Ophir Figures' code base (commit bae481c), itself built from DeckLedger (Ophir Cards): the core (app, migrations, sign-in, shared sign-in, admin, pictures, look and feel, browser tests) is theirs; the domain -- series, editions and volumes instead of figures -- is new (GLOSSARY.md, docs/adr/0001).

## Processes

```
browser (templates/index.html + static/js, plain scripts)
   |  JSON under /api/, pictures under /images/, static files
   v
gunicorn app:app (2 workers x 4 threads, port 8080)
   |  ophir_mangas package: one Flask app, routes from every module
   |------> DNB, Google Books, Open Library, AniList (lookup.py, only on a user's request)
   |------> shop pages and pictures named by users' links (fetch.py)
   v
SQLite  <DATA>/ophir-mangas.db (WAL)  +  volume-images/  volume-thumbnails/
```

- `docker-entrypoint.sh` runs `python -c "import app"` first, so the migrations finish before gunicorn serves anything. Importing the package anywhere migrates and seeds the database (`schema.init_database`).
- Every connection uses `busy_timeout` 10 s; requests share the one writer of the WAL database.

## Package layout

`app.py` is only the entry point. `ophir_mangas/__init__.py` imports `config, web, schema` first, then the feature modules, then runs `schema.init_database()`.

| Area | Source | Doc |
| --- | --- | --- |
| Core: paths, the Flask app, request guards, schema and migrations | `app.py`, `config.py`, `web.py`, `schema.py`, `migrations/` | [database.md](database.md) |
| Catalogue: series, editions, volumes, list items, search, pictures, market values | `catalog.py`, `listing.py`, `series.py`, `editions.py`, `volumes.py`, `search.py`, `images.py`, `prices.py` | [catalog.md](catalog.md) |
| Filling in from an ISBN, AniList or a product page | `lookup.py`, `link_import.py`, `fetch.py`, scanner and bookmarklet in `static/js/` | [lookup.md](lookup.md) |
| Collection and wishlists | `collection.py`, `watchlists.py` | [collection.md](collection.md) |
| Reading, collecting, gaps and the release calendar | `reading.py`, `planning.py` | [reading.md](reading.md) |
| Preorders | `preorders.py` | [preorders.md](preorders.md) |
| Export, backup, restore | `backup.py` | [backup.md](backup.md) |
| Sign-in, SSO, own account, admin API | `auth.py`, `oauth_client.py` (repository root), `account.py`, `admin.py` | [auth.md](auth.md) |
| Shared sign-in of the Ophir apps on one host (master/slave) | `shared_auth.py`, `ophir_auth.py` (repository root) | [shared-auth.md](shared-auth.md) |
| Page shell, bootstrap, dashboard, public profile | `pages.py`, `public_profile.py`, `templates/` | [pages.md](pages.md) |
| Browser frontend and its tests | `templates/index.html`, `static/` | [frontend.md](frontend.md) |

## Request flow

- Every route module registers on the one `web.app`. `web.db()` gives one connection per request (`sqlite3.Row`, foreign keys on, the SQL function `search_score`); writing views commit themselves.
- `@login_required` re-reads the session's user on every request; `@admin_required` adds the admin role. `/api/...` answers 401/403 JSON, pages redirect.
- A `before_request` hook refuses cross-site writes (Fetch Metadata / `Origin`); it is the app's only CSRF protection.
- With `OPHIR_AUTH_MODE` `master` or `slave`, a second `before_request` hook (`shared_auth.py`) sets the session's user from the host-wide `ophir_auth` cookie on every request, and the master's `after_request` renews or clears that cookie ([shared-auth.md](shared-auth.md)).
- Unauthenticated routes: `/login`, the OAuth callback, `/health`, and the public profile (`/u/<slug>`, `/u/<slug>/images/<series|volumes>/<id>`, `/api/public/<slug>`).
- The grids are worked out in Python from a few queries (`listing.py`): all editions, their volumes, the account's rows; the rules for releases, gaps and variants read better there than in SQL, and a catalogue of some thousand volumes takes milliseconds.

## Where state lives

All state is in the directory of `DATABASE_PATH` (`/data` in the container, the `ophir_mangas_data` volume):

- `ophir-mangas.db` - accounts and settings (`users`, `login_failures`, `user_settings`, `app_settings`), the catalogue (`series`, `editions`, `volumes`, `price_observations`), account data (`collection_entries`, `volume_reads`, `series_reading`, `collected_editions`, `watchlists`, `watchlist_entries`, `preorders`, `preorder_events`, `import_operations`) and `schema_migrations`.
- `ophir-mangas.db.before-migration-NNNN` - copies taken before a migration (two kept).
- `volume-images/` - every picture once (volume covers and series pictures), named by the SHA-256 of its bytes (uploads cannot be fetched again: back this up); `volume-thumbnails/` - WebP thumbnails, rebuildable.
- In the browser: only the theme cookie (`ophir_mangas_theme`), the session cookie and, with the shared sign-in, the host-wide `ophir_auth` cookie; there is no offline mode.

## External services

- Deutsche Nationalbibliothek (SRU), Google Books, Open Library and AniList (GraphQL), free and without keys, asked only when someone looks up an ISBN or searches AniList ([lookup.md](lookup.md)).
- Product pages and pictures named by users' links, fetched only on request.
- One OAuth2/OIDC identity provider, optional ([auth.md](auth.md)).
- Google Fonts for the web fonts (decorative; the page renders without them).

## Tests

- `python -m pytest` (`tests/`): a throwaway database with a small sample catalogue (`tests/conftest.py`: three series, five editions, fifteen volumes), no network; `fake_fetch` replaces every outgoing request (GET and JSON POST).
- `node --test "tests/frontend/*.test.mjs"`: frontend unit tests in a bare JavaScript context (`scripts.mjs`), including the EAN-13 decoder and the bookmarklet; smoke tests and a layout test in headless Chrome against `tests/frontend/serve.py` ([frontend.md](frontend.md)).
- CI (`.github/workflows/container-image.yml`) runs both before an image is built.
