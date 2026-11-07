# Reading, collecting, gaps and the release calendar

`reading.py` keeps read marks on volumes and the reading status of series; `planning.py` works out the gaps of the editions an account collects and its release calendar. "Sammle ich" itself is set in `editions.py` (`PUT/DELETE /api/editions/<id>/collecting`).

## Public interface

### reading.py

| Method | Path | What it does |
| --- | --- | --- |
| PUT/DELETE | `/api/volumes/<id>/read` | Mark read (optional `read_at`, default today) / unmark. PUT answers `{read, reading_status}`. |
| POST | `/api/editions/<id>/read` | `{through: n}`: every numbered volume up to n (variants too) read, those after it unread; 0 clears. Special volumes keep their marks. |
| PUT | `/api/series/<id>/reading` | `{status}`: one of `READING_STATUSES` or empty for none. |
| GET | `/api/reading` | `{series, counts, statuses}`: every series with a status or a read volume, with the edition read in (most read marks, then collected, then most owned), its progress, the next released unread volume (`owned` or not), `unread_owned`, `last_read`. Ordered by status (reading, planned, paused, finished, dropped, none), then the latest read first. |

- `READING_STATUSES` - `reading` Lese ich · `planned` Geplant · `paused` Pausiert · `finished` Fertig · `dropped` Abgebrochen.
- `follow_read_marks(connection, uid, edition_id)` - the only automatic changes: a read mark makes a series without status (or planned) "reading"; reading every volume of a completed edition makes a series that is being read "finished".
- `reading_overview(connection, uid)` (also the dashboard), `set_reading_status`.

### planning.py

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/gaps` | `{editions, stats}`: every collected edition with gaps, most first; each gap `{number_label, volume}` (`volume` null when the catalogue lacks that number). `stats`: `editions`, `gaps`, `uncatalogued`, `estimate` (list prices in euros). |
| GET | `/api/calendar?months=6` | `{months: [{month, volumes}], recent, undated}`: volumes of collected or wished editions and wished volumes, due from the start of last month to `months` ahead; `recent` what came out in the last 45 days and is not owned; `undated` how many of those volumes have no date. Each volume item carries `collecting`. |

- `gap_overview`, `calendar`, `dashboard_planning(uid)` (gap count, the next 8 releases of three months, 6 recent ones).

## Dependencies

- `listing` (Account, edition and volume items), `catalog.number_label`, `config.today_iso` (patched in tests to fix the date)

## Decisions and assumptions

- A gap is a released number of a collected edition owned in no variant (GLOSSARY.md); "released through" is the highest released catalogued number, or the volume count of a completed edition. Numbers the catalogue lacks still count, so an edition of 34 volumes with five entered shows 29 more gaps, which the gaps view offers to create at once.
- "Sammle ich" is never set automatically (decided with the user on 2026-11-07): a first volume bought to try a series must not fill the gaps and the calendar.
- Reading status belongs to the series (the story), read marks to volumes (docs/adr/0001): reading the German edition and collecting the Japanese one are separate.
