# Ophir Mangas

Self-hosted, multi-user collection manager for manga: a catalogue of series, their editions (publisher, language, format) and their volumes shared by every account, and each account's copies, reading, gaps, release calendar, wishlists, preorders and a public profile. One Flask app with an SQLite database, shipped as a single container image. The third app of the Ophir family next to [Ophir Cards](https://github.com/axelcypher/deckledger) and [Ophir Figures](https://github.com/axelcypher/ophir-figures), built from Ophir Figures' code base. Complete and tested; not deployed yet.

## Features

- Local accounts with user and admin roles; optional sign-in through one OAuth2/OIDC provider; optionally one sign-in shared with the other Ophir apps on the same host
- A catalogue in three levels: a **series** (titles, authors, genres, target group, status), its **editions** (Carlsen German, Kodansha Japanese, a Perfect Edition …: publisher, language, format, number of volumes, list price) and their **volumes** (number, ISBN, release date, price, pages, cover); a Limited Edition is a variant under the same number, a fanbook a special volume
- Volumes from their ISBN: typed or scanned with the phone's camera (or from a photo), looked up at the Deutsche Nationalbibliothek, Google Books and Open Library; series from AniList; anything else from a shop or publisher page, with the bookmarklet "Zu Ophir Mangas" for pages that refuse automatic requests. What the catalogue lacks on the way (series, edition) is created in the same flow
- The edition as the tile: owned and read progress, the next volume, and a dialog with every number in order - owned, read, missing, coming - where a missing number is created with one click and "Bände besitze ich …" takes a whole shelf (`1-12, 14`) at once
- Copies with condition (Neu/OVP, Sehr gut, Mit Lesespuren, Beschädigt), first printing, extras, purchase price, date, shop, storage place and notes
- Reading: read marks per volume (owned or not), a reading status per series (Lese ich, Geplant, Pausiert, Fertig, Abgebrochen), "Gelesen bis Band …", and a reading view with the next volume of each series
- "Sammle ich" per edition, set by hand: its gaps (released numbers owned in no variant) and a release calendar of what comes next
- Groups side by side: catalogue, collection and wishlists by series, publisher, author, genre, language or target group, each with covers and counts; or single volumes instead of editions
- Wishlists of whole editions or single volumes, with target prices; preorders from order to arrival, every postponed release logged, arrival booked into the collection
- Values: what was paid, and a market value history for volumes where it matters; without one a copy counts with its purchase price, else its list price
- Pictures: downloaded from a link or uploaded as JPEG, PNG, WebP, GIF or AVIF (up to 15 MB), thumbnails made on the server
- Public profile at `/u/<address>`: the collection (optionally the wishlist and the reading status) with covers, readable without signing in, without prices or private data
- JSON backup and restore (also onto another instance, with undo), CSV export of collection and preorders
- Duplicate check on entry (ISBN, number and variant, same edition, same series) and, for admins, merging duplicates at every level
- Dark and light appearance, works on phones

## Requirements

- Docker with Compose - runs the container ([compose.yaml](compose.yaml))
- Python 3.13 - development and the test suite (the image is `python:3.13-slim`)
- Node.js 22 or newer - the frontend tests use Node's own test runner (CI uses Node 24)
- Chrome or Chromium - the browser tests; without it they are skipped locally

## Setup

1. Clone the repository:

    ```bash
    git clone https://github.com/axelcypher/ophir-mangas.git
    cd ophir-mangas
    ```

2. Set a strong `SECRET_KEY` in the environment or in a `.env` file next to `compose.yaml`; without it Compose refuses to start the stack, and the app refuses to serve:

    ```dotenv
    SECRET_KEY=<long random string>
    ```

    One way to get such a string: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

3. Build and start:

    ```bash
    docker compose up --build -d
    ```

4. Open <http://localhost:18083> and sign in as `admin` / `admin`. Change that password under **Admin → Benutzer** right away and create the other accounts there.

Password sign-ins are throttled: after 10 failed attempts for one username or 30 from one address within 15 minutes, the login page answers 429 until the oldest of them is 15 minutes old, without checking the password. Single sign-on is not affected. Behind a reverse proxy set `TRUST_PROXY_HEADERS`, otherwise every client counts as the proxy's address.

The first start creates the database in the `ophir_mangas_data` volume. There is no demo data: the catalogue starts empty and grows with what you add.

## Configuration

| Setting | Where | Description | Default | Required |
| --- | --- | --- | --- | --- |
| `SECRET_KEY` | env | Signs the session cookies (and, with the shared sign-in, the `ophir_auth` cookie); gunicorn (the container) does not start without it | none; only `python app.py`, the demo server and the tests fall back to a public development key | yes |
| `DATABASE_PATH` | env | SQLite file; pictures and thumbnails live in `volume-images/` and `volume-thumbnails/` next to it | `ophir-mangas.db` in the repo root; `/data/ophir-mangas.db` in the image | no |
| `TRUST_PROXY_HEADERS` | env | `true`, `1` or `yes`: honour `X-Forwarded-For` / `-Proto` / `-Host` / `-Prefix` (client address for the login throttle, `https://` redirect URIs, the path the app is served under) | off | behind a TLS-terminating proxy |
| `OAUTH_CONFIG_PATH` | env | SSO config file that replaces the Admin UI settings | `/config/oauth.json` | no |
| `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `OAUTH_DISCOVERY_URL` | env | SSO settings that replace the Admin UI settings (a mounted config file still wins); `OAUTH_CLIENT_ID` switches SSO on. Every other field of [oauth.json.example](oauth.json.example) works the same way, e.g. `OAUTH_PROVIDER_NAME`, `OAUTH_ACCOUNT_MATCHING` | none | no |
| `PUBLIC_PROFILE_URL` | env | Base URL public profile links are built on, e.g. `https://mangas.example.org` or, under a path, `https://example.org/mangas` | the address the settings page was opened on | no |
| SSO settings | **Admin → Single Sign-On** or `oauth.json` | One OAuth2/OIDC provider, shape as in [oauth.json.example](oauth.json.example) | off | no |
| `OPHIR_AUTH_MODE` | env | `standalone`, `master` or `slave`: sign users in itself, also for the other Ophir apps on the host, or take the master's sign-in; any other value stops the app at start-up | `standalone` | no |
| `OPHIR_AUTH_PATH` | env | Where the master serves sign-in on the shared host; the same in every app | `/auth` | no |
| `OPHIR_AUTH_HOME` | env | Master only: where a sign-in at the auth path ends that did not say where to go, e.g. `/mangas/` | `/` | no |

The lookups (DNB, Google Books, Open Library, AniList) need no key or account.

### Under a path

The app can share a host with others under a path such as `https://example.org/mangas`. The reverse proxy strips the path before passing a request on and names it in `X-Forwarded-Prefix` (Traefik's `StripPrefix` middleware does both); with `TRUST_PROXY_HEADERS` set, every link, redirect and request of the app then carries it. The session cookie has a name of its own (`ophir_mangas_session`, with its own signing salt), so another app on the same host does not overwrite or read it.

### Shared sign-in with other Ophir apps

When several Ophir apps share a host (`ophir.example.org/cards`, `/figures`, `/mangas`), one of them can sign people in for all: the **master** serves sign-in under `/auth` on that host, and the others (**slaves**) take that sign-in. Signing out anywhere signs out everywhere, and there is one SSO redirect URI for all apps: `https://ophir.example.org/auth/oauth/callback`.

- All apps need the same `SECRET_KEY`; it signs the shared sign-in cookie (`ophir_auth`).
- The proxy serves the master under its own path **and** under `/auth`; slaves only under their own path.
- Accounts and roles are managed at the master. A slave creates its own account for someone on their first visit (no password of its own, with a default wishlist), or links an existing one with the same email or username, and takes the display name, email and role from the master. In a slave, accounts, passwords and SSO cannot be changed; **Einstellungen** and **Admin** show them as managed by the master.
- An account deleted or demoted at the master keeps working at the slaves for up to 12 hours.

The protocol is in [docs/code/shared-auth.md](docs/code/shared-auth.md); `ophir_auth.py` is the same file in every Ophir app.

### Single sign-on (OAuth2 / OIDC)

Configured under **Admin → Single Sign-On** (stored in the database), with `OAUTH_*` environment variables, or with a config file mounted read-only at `/config/oauth.json`. A file wins over the variables, the variables over the Admin UI, which is then read-only. Required are `client_id`, `client_secret` and either `discovery_url` or all of `authorize_url`, `token_url` and `userinfo_url`. `account_matching` is `manual` (an identity must be linked under **Einstellungen → Konto**), `email` (an unlinked account with the same email is linked, but only when the provider sends `email_verified: true`) or `auto_provision` (default: also creates a `user` account for an unknown identity). The redirect URI is `https://<host>/oauth/callback` (under a path: `https://<host>/<path>/oauth/callback`).

## Usage

### Adding manga

**＋ Manga** (or **Scannen**) is the way in:

- **ISBN**: type it or scan the barcode on the back of a volume. The app asks the Deutsche Nationalbibliothek, Google Books and Open Library and fills in the volume. If the catalogue has its edition, the volume form opens there; if it has the series, you pick the edition or start a new one; otherwise the series form opens first (with an AniList search that fills titles, authors, genres and the target group), then the edition, then the volume. A scanned volume that is already in the catalogue just opens.
- **Link**: a shop or publisher page; pages with a bot check work through the bookmarklet **★ Zu Ophir Mangas** from **Einstellungen**, which reads the page in your own browser and passes it on in the address's fragment (never logged by a server).
- **By hand**: search a series in the catalogue or create one.

The scanner uses the browser's barcode reader where there is one (Chrome on Android) and a reader of its own elsewhere; it needs the camera (https) or takes a photo. In the edition dialog, an empty number creates that volume, **Bände besitze ich …** adds a range at once, and **Gelesen bis …** sets the read marks.

### Collecting, gaps and new releases

**Sammle ich** in an edition's dialog tells the app you collect it. Only then do its gaps (released numbers you own in no variant) show under **Lücken**, and its coming volumes under **Neuerscheinungen**, together with what is on your wishlists. Numbers the catalogue lacks still count as gaps; **Alle anlegen** creates them.

### Reading

A volume is marked read in its dialog, on its slot (✓) or with **Gelesen bis …**. The first read volume makes a series "Lese ich"; reading the last volume of a completed edition makes it "Fertig". **Lesen** lists every series by status with the next volume to read.

### Preorders

A preorder starts with the volume's release date and its list price. Changing the expected release logs the move; **Bezahlt** sets the paid amount to price plus shipping; **Angekommen** adds the copies to the collection as new first printings at the order's price per copy. Setting it back takes those copies out again; deleting a preorder keeps them.

### Backup

**Import / Export** in the user menu downloads a JSON backup (copies, reading, collected editions, preorders with their history, wishlists, and every series, edition and volume they refer to) or CSV tables. Restoring matches the catalogue and creates what is missing; **Rückgängig** takes the latest restore back. Pictures are not in the backup; their links are, and the `ophir_mangas_data` volume holds the uploaded ones.

### Operations

```bash
docker compose ps
docker compose logs -f
docker compose down
```

`docker compose down` keeps the `ophir_mangas_data` volume; it holds the database and every picture, so it is what to back up. `GET /health` answers with the database name, `schema_version` and `schema_expected`. Before an existing database is migrated, a copy is written next to it (`ophir-mangas.db.before-migration-NNNN`, the two newest kept); a database written by a newer version is refused at start-up.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python app.py
```

`python app.py` starts Flask's debug server on port 8080 with `ophir-mangas.db` in the repo root (without `SECRET_KEY` it warns and signs sessions with a public development key). `python tests/frontend/serve.py <port>` serves the app with a throwaway database and the small test catalogue (account `demo` / `mangas-1234`), lookups and links answering only from fakes.

- Code layout: `app.py` is only the entry point; the application is the `ophir_mangas` package. Module docs: [docs/code/](docs/code/architecture.md); terms: [GLOSSARY.md](GLOSSARY.md); decisions: [docs/adr/](docs/adr/).
- Schema changes: add `ophir_mangas/migrations/mNNNN_<what>.py` with `NAME` and `apply(connection, context)` and list it in `MIGRATIONS`. A released migration is never edited; nothing else creates or alters tables (a test enforces it).
- Python tests: `python -m pytest` - every API against a throwaway database with a small built-in catalogue; outgoing requests are replaced by fakes.
- Frontend tests: `node --test "tests/frontend/*.test.mjs"` - script logic, the EAN-13 decoder and the bookmarklet in a bare JavaScript context; smoke tests that drive the real app in headless Chrome (also under `/mangas`); a layout test of every view and dialog in both appearances on a phone and a wide screen (nothing past the right edge, every text readable against its background). `CHROME_BIN` sets the browser, `OPHIR_PYTHON` the interpreter that starts the app, `OPHIR_SCREENSHOTS=<directory>` saves a screenshot of every state the layout test checks.
- Lint / format: none configured.

## Release

[.github/workflows/container-image.yml](.github/workflows/container-image.yml) runs on every push to `main`, on `v*` tags, on pull requests and by hand. It runs both test suites, then builds the image and, except for pull requests, pushes it to `ghcr.io/<owner>/<repository>` (`ghcr.io/axelcypher/ophir-mangas`) with the tags `main`, `latest`, `sha-<commit>` and, for a `v*` tag, the semver tags, and attests it. There is no version number in the code; images are identified by their `sha-<commit>` tag.

After a published build, the job `update-deployment-repository` writes that tag into an env file of another repository. It stays off until the repository variable `OPHIR_MANGAS_DEPLOY_REPOSITORY` is set:

| Variable / secret | Description | Default |
| --- | --- | --- |
| `OPHIR_MANGAS_DEPLOY_REPOSITORY` | Target repository, `owner/repository` | none (job disabled) |
| `OPHIR_MANGAS_DEPLOY_BRANCH` | Branch to commit to | `main` |
| `OPHIR_MANGAS_DEPLOY_ENV_FILE` | Env file in the target repository | `.env` |
| `OPHIR_MANGAS_DEPLOY_IMAGE_KEY` | Variable that receives the tag | `OPHIR_MANGAS_IMAGE_VERSION` |
| `OPHIR_MANGAS_DEPLOY_TOKEN` (secret) | Fine-grained token with read/write access to the target's contents | none |

## Documentation

- Module docs for agents: [docs/code/](docs/code/architecture.md)
- Detailed docs: vault note `homelab-docs/projects/ophir-mangas.md`
