# Preorders

`preorders.py` tracks volumes ordered before their release: payment, the expected release and how often it moved, status until arrival, and booking the arrived copies into the collection. Taken over from Ophir Figures, with the volume in place of the figure.

## Public interface

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/preorders?status=` | `open` (default: ordered, paid, shipped), one status, or `all`. Returns `{preorders, stats, statuses}`; `stats` always over all of the account's preorders: `open`, `open_copies`, `outstanding`, `open_total`, `paid`, `due_this_month`, `overdue`, `next_month`, `delivered`, `cancelled`, `postponed`. |
| POST | `/api/preorders` | `{volume_id, status, shop, order_number, ordered_at (default today), quantity (1-99), price, shipping, paid, expected_release (default the volume's release date), tracking, notes, delivered_at, remove_from_wishlists}`. Without a price, the list price in euros times the quantity. 201 with the row. |
| PATCH | `/api/preorders/<id>` | Any subset; only the owner's (404 otherwise). |
| DELETE | `/api/preorders/<id>` | Booked copies stay (their `preorder_id` becomes NULL). |

A row (`preorder_rows(uid, where, params)`, also used by the volume detail): the table's columns plus `number`, `number_label`, `volume_title`, `variant`, `isbn`, `volume_release`, `edition_id`, `edition_name`, `publisher`, `language`, `series_id`, `series_title`, picture fields, `total`, `outstanding`, `events`, `delays`, `booked_entry_ids`. Order: open first, then by expected release.

Status effects (`apply_status_side_effects`):

- to `paid`: `paid` is raised to the total (logged as a `paid` event);
- to `delivered`: `delivered_at` = today unless set; the copies are booked once (`book_delivery`): condition `new`, first printing, purchase price = total / quantity, date = `ordered_at`, shop, note `Vorbestellung <order number>`;
- from `delivered` to anything else: `delivered_at` cleared, booked rows deleted;
- while `delivered`, changing quantity, price, shipping, shop or order date rebooks.

## Dependencies

- `catalog` (dates, names), `prices.parse_amount`, `collection_entries` (booking)

## Decisions and assumptions

- Statuses are a fixed list (CHECK constraint) so the overview can count and group them.
- The expected release is the shop's, kept per preorder: the volume's release date is a fact about the book, the preorder's what a shop currently promises.
- An arrived preorder counts as a first printing: a volume preordered arrives from the first print run.
