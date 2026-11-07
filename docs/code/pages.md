# Page shell, bootstrap, dashboard and public profile

`pages.py` serves the page shell and what the app loads first; `public_profile.py` the shared view of a collection for visitors without an account.

## Public interface

### pages.py

| Method | Path | Auth | What it does |
| --- | --- | --- | --- |
| GET | `/` | login | `templates/index.html`. |
| GET | `/api/bootstrap` | login | `user` (with `oauth_linked`, `password_set`), `settings`, `counts` (`collection` editions owned or collected, `volumes`, `wished` entries, open `preorders`, series being read (`reading`), `collecting`, `catalog` editions), `watchlists`, last 4 `imports`, `oauth`, `auth` (`mode`, `base`; [shared-auth.md](shared-auth.md)), `conditions`, `statuses` (preorders), `reading_statuses`, `languages`, `series_statuses`, `demographics`, `formats`, `currency`. |
| GET | `/api/dashboard` | login | `collection` (collection.dashboard_collection), `preorders` (`stats`, `upcoming`), `planning` (planning.dashboard_planning), `reading` (series being read, 8), `counts`. |

### public_profile.py

| Method | Path | Auth | What it does |
| --- | --- | --- | --- |
| GET/PUT | `/api/account/public-profile` | login | The owner's setting: `enabled`, `slug` (3-32 of `a-z0-9-`, unique), `name` (60), `show_wishlist`, `show_reading`, `theme` (`auto`/`light`/`dark`); `url` built on `PUBLIC_PROFILE_URL` or the request's root URL. Enabling needs a slug. |
| GET | `/u/<slug>` | none | `templates/public.html`; 404 page when off or unknown. |
| GET | `/api/public/<slug>` | none | `{name, slug, collection, stats (series, editions, volumes, read?), facets (language, publisher), show_reading, wishlist?}`; editions through `public_edition` only. |
| GET | `/u/<slug>/images/<series|volumes>/<id>` | none | Thumbnail, or the full picture with `?size=full`: an owned volume, the cover of a shown edition, or the series picture of a shown edition without a cover; 404 otherwise. |

- `public_edition(item, profile)` / `public_volume` are the only shapes that leave the server for visitors: `id, series_id, name, series_title, original_title, authors, genres, demographic, publisher, language, format, status, total, owned, latest_release, cover` and the owned volumes (`id, number_label, title, variant, release_date`, picture fields, `owned`); with `show_reading` also the reading status and read marks. No prices, values, purchase data, conditions, storage places, notes, preorders or target prices.

## Dependencies

- `collection`, `preorders`, `planning`, `reading`, `watchlists`, `listing`, `images.serve_image`, `auth.resolve_oauth_config`

## Decisions and assumptions

- An off and an unknown profile answer the same 404, so addresses cannot be probed.
- The setting is only written through its own endpoint, which checks the slug; `/api/settings` skips the key.
- The wishlist on the profile shows editions (whole or with wished volumes) without their volumes.
