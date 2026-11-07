# Export, backup and restore

`backup.py` writes an account's data out (JSON backup, CSV tables) and restores a backup, with undo.

## Public interface

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/export.json` | The backup (`format` `ophir-mangas-backup`, `version` 1): `series`, `editions`, `volumes` (each with a `ref` and its parent's ref; an edition with all its volumes; volumes with `market_value`), `collection`, `preorders` (with `events`), `watchlists` (entries with `volume_ref` or `edition_ref`), `reads`, `reading`, `collecting`. |
| GET | `/api/export.csv` | Copies as a table (`;`, BOM): series, edition, authors, publisher, language, format, number, title, variant, ISBN, release, quantity, condition, first printing, extras, purchase, shop, place, notes, read, market value. |
| GET | `/api/export/preorders.csv` | Preorders as a table. |
| POST | `/api/import/json/preview` | `{data}`: what a restore would do, `series_new`, `editions_new`, `volumes_new` among them. |
| POST | `/api/import/json/apply` | `{data, strategy: add|replace}`: matches series, editions and volumes with the duplicate rules of catalog.py and creates the missing ones, then adds preorders (one already there, same volume, shop, order date and number, is skipped), copies (`replace` replaces the collection), read marks, reading statuses and collected editions the account does not have yet, and wishlist entries (lists merged by name). Returns what it did and the `operation_id`. |
| POST | `/api/import/<id>/undo` | Only the latest restore: removes what it added, puts a replaced collection back, deletes catalogue entries it created that nothing uses. |

- Every entry of a backup is checked like a form (`clean_*_fields`); a broken one stops the restore with a German message (400) and nothing is written.

## Dependencies

- `catalog` (field rules, duplicate rules, in-use checks), `collection`, `preorders`, `reading`, `prices`, `schema.ensure_user_lists`

## Decisions and assumptions

- A backup carries the catalogue it needs, so it restores onto another instance; pictures are not in it (their links are), the `ophir_mangas_data` volume holds the uploaded ones.
- Restoring never overwrites what the account already has (reading status, read marks, collected editions); only `replace` replaces the copies.
