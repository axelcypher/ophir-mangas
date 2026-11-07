# Collection and wishlists

`collection.py` holds an account's copies; `watchlists.py` its wishlists of volumes and whole editions. Both list editions as the catalogue does (listing.py), or single volumes with `level=volumes`.

## Public interface

### collection.py

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/collection` | The editions the account has volumes of or collects, with the catalogue's filters, modes (`all`, `collecting`, `gaps`, `complete`, `unread` …), sorts and groups; `{editions | groups, stats, shown_stats, facets, conditions}`. With `level=volumes`: the owned volumes, also by `location` and `condition`, facets with `location`. |
| POST | `/api/collection` | `{volume_id, quantity (1-999), condition (default new), first_printing, extras, purchase_price, purchased_at, shop, location, notes}`; 201 with the row. `volume_ids` instead adds the same to each (a run bought at once): `{created: [ids]}`. |
| PATCH | `/api/collection/<id>` | Any subset; only the owner's rows (404 otherwise). |
| DELETE | `/api/collection/<id>` | Returns `{deleted: row}`, enough to post it back (undo in the UI). |

- `CONDITIONS` - `new` Neu/OVP · `very_good` Sehr gut · `reading_marks` Mit Lesespuren · `damaged` Beschädigt.
- `clean_entry_fields(payload, partial)`, `dashboard_collection(uid)` (volumes, copies, editions, spent, value, unread, read, 12 latest additions, copies per language).
- A copy's value: market value, else its purchase price, else the list price in euros (prices.py).

### watchlists.py

| Method | Path | What it does |
| --- | --- | --- |
| GET/POST | `/api/watchlists` | The account's lists with `count`, default first / `{name}` (60 characters, unique per account ignoring case). |
| PATCH/DELETE | `/api/watchlists/<id>` | Rename / delete (not the default list). |
| GET | `/api/watchlists/<id>/entries` | The editions the list touches (a whole edition: `whole`, `note`; wished volumes: `wished_volumes`, `target_reached`), as the catalogue grid with groups; `level=volumes`: the wished volumes with `target_price`, `note`, `wished_at`, `target_reached` (market value <= target), `mode=missing` hides owned ones. `sort=wished` (default) is the latest wish first. `list_stats`: `editions`, `whole`, `volumes`, `owned`, `target_reached`, `estimate` (market values, else target, else list price, of what is not owned). |
| POST | `/api/watchlists/<id>/volumes`, `/editions` | `{volume_id | edition_id, target_price, note}`; adding again only updates the given fields; an edition has no target price. `{added, lists}`. |
| PATCH/DELETE | `/api/watchlists/<id>/volumes/<volume_id>`, `/editions/<edition_id>` | `target_price`, `note` / remove, returning `{removed, lists}`. |

- `lists_of(uid)` (also in bootstrap).

## Dependencies

- `listing` (items, filters, facets, groups), `editions.grid_answer`, `volumes.volume_grid_answer`, `prices`, `catalog.normalize_date`, `schema.ensure_user_lists`

## Decisions and assumptions

- A collection row groups copies with the same condition and purchase; several rows per volume are normal.
- The collection grid also shows editions the account collects but has no volume of yet, so a new "Sammle ich" is visible there.
- The heart on a tile always means the default list: on an edition the whole edition, on a volume that volume. Other lists are chosen in the dialogs.
- "Mit Lesespuren" instead of "Gelesen" for a used copy, so the word "gelesen" belongs to the reading status alone (GLOSSARY.md).
