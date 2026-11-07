# Catalogue: series, editions, volumes

The shared catalogue in three levels (docs/adr/0001): `catalog.py` holds the rules for fields, ISBNs, volume numbers, dates and duplicates; `listing.py` turns editions and volumes into the list items every grid shows, seen by one account; `series.py`, `editions.py` and `volumes.py` are the routes. `search.py` is how every search box matches, `images.py` stores and serves pictures, `prices.py` keeps market values.

## Public interface

### catalog.py

- `clean_series_fields`, `clean_edition_fields`, `clean_volume_fields` `(payload, partial=False)` -> fields; raise `FieldError` (German message). Lists (`alt_titles`, `authors`, `genres`) are stored as `", "`-joined text; `language` is a 2-3 letter code; a volume needs a number or (special volume) a title.
- `normalize_isbn(value)` -> 13 digits or `''`; ISBN-10 is converted, hyphens and an `ISBN` prefix are dropped, the check digit is checked (`FieldError`). `isbn13_check(digits12)`.
- `parse_volume_number('Band 12' | 'Vol. 3' | '10,5' | '第7巻' | '')` -> float or None; `number_label(5.0)` -> `'5'`, `10.5` -> `'10.5'`.
- `normalize_date(value, field)` -> `(ISO with the given precision, error)`: `2025`, `2025-03`, `14.03.2025`, `03/2025`, `March 2025`, `14. März 2025`, `2025年3月`.
- `is_released(release_date, today)` - a full date on or before today; a month or a year once it is over; no date counts as released.
- `find_series_duplicate` (same AniList id, or a title equal to a title or original title), `find_edition_duplicate` (same series, language, publisher, label and format), `find_volume_duplicate` (same ISBN anywhere, or the same edition with the same number and variant; a special volume by title). Comparisons are folded (`fold_key`: case, accents, spacing, punctuation).
- `edition_name(edition, series_title)` - the printed title or the series', plus ` – <label>`.
- `volume_in_use`, `edition_in_use`, `series_in_use` - copies, preorders, wishes, read marks; collecting; reading status.
- Constants: `LANGUAGES`, `STATUSES` (ongoing, completed, hiatus, cancelled), `DEMOGRAPHICS`, `FORMATS`, `GENRES`, `CURRENCIES`.

### listing.py

- `Account(connection, uid)` - what one account has: `owned` (per volume: copies, value, spent, conditions, locations, first printing, dates), `read`, `preordered`, `wished_volumes`, `wished_editions`, `collected`, `reading`.
- `volume_items(connection, account, where, params)` - volumes with their edition's and series' facts, `number_label`, `edition_name`, `released`, `owned`, `value`, `read`, `preordered`, `wished`, `market_value`, picture fields.
- `edition_items(connection, account, where, params, with_volumes=False)` - editions with `name` and the summary: `catalogued`, `specials`, `highest`, `released_through` (the highest released number; the volume count for a completed edition), `total` (volume count or highest number), `owned` / `owned_numbers` (a number counts once, whatever variant), `copies`, `read` / `read_numbers`, `unread_owned`, `gaps` and `gap_count` (only when collected), `complete`, `next_release`, `latest_release`, `cover` (`{kind, id, version}`: the first volume with a cover, standard before variants, else the series' picture, else null), `value`, `spent`, `preordered`, `wished`, `edition_wished`, `collecting`, `isbns`, `reading_status`.
- Filters `apply_filters(items, args, kind)`: `language`, `publisher`, `format`, `demographic`, `status`, `series` (value), `author`, `genre` (one of the list's entries), each also `__none__`; `reading` (a status or `none`); `q`. Modes `EDITION_MODES` (all, owned, missing, collecting, gaps, complete, wished, preordered, unread) and `VOLUME_MODES` (all, owned, missing, read, unread, wished, preordered, upcoming). Sorts `EDITION_SORTS` (title, added, release, next, progress, value, publisher) and `VOLUME_SORTS` (title, release, added, value). `facets(items)`.
- Groups `grouped(args, items)` with `?group=series|publisher|author|genre|language|demographic&group_sort=name|count|owned|value|release`: `{group, groups}`; a group has `count` (editions), `owned`, `volumes`, `copies`, `read`, `gaps`, `collecting`, `wished`, `value`, `spent`, `latest_release`, `samples` (four `{id, name, cover, series_id}`). An edition with two authors or genres is in both groups; the group without a value comes last.

### Routes

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/series?q=&limit=` | Every series briefly (picker), best match first. |
| GET/POST | `/api/series/<id>`, `/api/series` | Detail with every edition (owned first) and the account's reading status / create (409 `{error, duplicate_id}`, `force` skips the check; `image_url` is fetched). |
| PATCH/DELETE | `/api/series/<id>` | Update / delete with its editions and volumes, only unused, by its creator or an admin. |
| GET | `/api/editions` | The catalogue grid: `{editions | group+groups, total, shown, facets, stats, shown_stats}`. |
| GET/POST | `/api/editions/<id>`, `/api/editions` | Detail: the edition item with `volumes` in order, `slots` (every number up to the larger of total, highest and released through, each with its volume ids, `released`, `gap`), `special_ids`, `series`, `other_editions`, `lists`, `owners`, `can_delete` / create (`series_id`; `collect` sets "Sammle ich"). |
| PATCH/DELETE | `/api/editions/<id>` | Update (also `series_id`) / delete with its volumes, only unused, by its creator or an admin. |
| PUT/DELETE | `/api/editions/<id>/collecting` | "Sammle ich" on and off. |
| GET | `/api/editions/<id>/next-volume` | The next number and the edition's list price, for the form. |
| POST | `/api/editions/<id>/volumes` | `{from, to}` creates the numbers the catalogue lacks (at most 200), with the edition's list price. |
| GET | `/api/volumes` | Every volume as a tile: `{volumes, total, shown, facets, stats, shown_stats}`. |
| GET/POST | `/api/volumes/<id>`, `/api/volumes` | Detail: the item plus the account's `entries`, `preorders`, `lists`, `prices`, `owners`, `previous_id`/`next_id` in the edition, `edition` summary, `can_delete` / create (`edition_id`; list price and currency from the edition unless given; `market_value` adds a first value). |
| PATCH/DELETE | `/api/volumes/<id>` | Update (also `edition_id`) / delete, only unused, by its creator or an admin. |
| GET | `/api/volumes/by-isbn/<isbn>` | The volume of a scanned barcode; 404 `{error, isbn}` when the catalogue lacks it. |
| GET | `/api/search?q=&limit=` | Quick search: `{editions, volumes}`; volumes for an ISBN (matched on its last ten digits) or a query with a digit. |
| GET | `/api/catalog/suggestions` | Autocomplete: publishers, formats, labels, variants, authors, genres, the account's shops and storage places, currencies, languages. |

### images.py

| Method | Path | Auth | What it does |
| --- | --- | --- | --- |
| GET | `/images/<series|volumes>/<id>` | login | The picture as stored (`image/avif`, `image/jpeg` …); the placeholder SVG (a closed book, 5 min cache) without one. |
| GET | `/images/<series|volumes>/<id>/thumb` | login | WebP, 480 px wide, made on first use. |
| POST/DELETE | `/api/<series|volumes>/<id>/image` | login | Multipart `file` or JSON `{url}`; 400 for anything Pillow cannot read as JPEG/PNG/WebP/GIF/AVIF or above 15 MB / clears the picture (the file stays, it may be shared). |

- `store_image(bytes)`, `download_image(url)`, `ensure_image(connection, table, entry)` (a pending `image_url` fetched on first view, a failed one not again for 600 s), `serve_image(table, id, size)` (also the public profile), `try_image(connection, table, id, url)`.

### prices.py

- `GET/POST /api/volumes/<id>/prices`, `DELETE /api/volumes/<id>/prices/<price_id>`; `market_value_sql`, `collection_value_sql()` (copies x market value, else x purchase price, else x list price in euros, else 0), `parse_amount` (`7,50`, `1.299,00`, `1,299.00`, `19.800`), `record_price`, `price_history`.

### search.py

- `score(query, text1, weight1, ...)` (SQL `search_score`), `query(text)`, `edition_fields(item)` / `volume_fields(item)` with the weights: titles 4, other titles, ISBN and number 3, authors and publisher 2, label, format, genres, variant 1, description 0.4.
- Every word must be in some field; words of 4+ letters without digits may be one edit off (two from 8 letters). Text with `| ^ $ \ [ ] * + ? { }` is matched literally or as a regular expression.

## Dependencies

- `web`, `config`, `prices` (amounts, value SQL), `images`, `preorders.preorder_rows` (volume detail), Pillow, `fetch` (pictures)

## Decisions and assumptions

- Series -> edition -> volume, the edition as the tile ([ADR-0001](../adr/0001-series-editions-volumes.md)); the edition fills in its volumes instead of line presets ([ADR-0002](../adr/0002-edition-is-the-preset.md)).
- A variant (Limited Edition) is a volume row of its own with the same number; progress and gaps count numbers. A special volume (no number) never counts as a gap.
- One shared catalogue that everyone may correct, like a small wiki; deleting is restricted to unused entries and their creator or an admin, duplicates are prevented on entry and merged by admins ([auth.md](auth.md)). Deleting a series or edition takes what is under it, so the foreign keys have no cascade of their own.
- No release date counts as released: volumes entered without a date are almost always old ones, and a gap that does not exist yet is easy to spot.
- Pictures are content-addressed and never deleted automatically: two entries may share one, and an upload cannot be fetched again.
