# Lookup and link import

`lookup.py` fills in volumes from their ISBN and series from AniList; `link_import.py` reads a product page (by the server, or in the user's browser through the bookmarklet). Both answer with a *proposal* and where it fits in the catalogue; nothing is saved, the forms are filled and the user saves. `fetch.py` is the guarded HTTP client for all of it. The barcode scanner (static/js/scanner.js) only reads the ISBN off the cover; the lookup does the rest ([frontend.md](frontend.md)).

## Public interface

### The proposal

```
{"volume": {number, title, variant, isbn, release_date, list_price, currency, pages, description, image_url, source_url},
 "edition": {title, label, publisher, language, format, list_price, currency},
 "series": {title, original_title, alt_titles, authors, genres, demographic, status, original_volumes, start_year, description, image_url, source_url, anilist_id},
 "covers": [...], "sources": ["dnb","google","openlibrary"] | ["page"], "warnings": [...],
 "match": {"volume_id", "edition_id", "series_id", "editions": [{"id","name","publisher","language","format"}]}}
```

Empty values are left out; `number` is a label (`"5"`, `"10.5"`).

- `build_proposal(volume, edition, series, covers, sources, warnings)`, `match_catalogue(connection, proposal)`: the volume by ISBN; else the series by AniList id or a title equal to its title, original title or one of its other titles (and an edition's printed title); the edition within it by language and publisher (`publisher_key` drops words like Verlag, GmbH, Manga, Media); with an edition, a volume of the same number and variant that has no ISBN yet.
- Helpers: `split_title_number('Frieren 5' | 'Attack on Titan, Band 5' | 'Vol. 3')` (a bare trailing or bracketed number only up to three digits, so `Akira (1982)` keeps its title), `language_code`, `parse_date`, `euro_price` (the `(DE)` price of MARC 020 $c), `parse_dnb`, `parse_google`, `parse_openlibrary`, `anilist_series`.

### Routes

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/lookup/isbn/<isbn>` | Asks the DNB (SRU, MARC 21: 245, 490/800/830 for series and number, 264/260, 020 $c, 300, 041/008, 100/700, 250), Google Books and Open Library, each on its own, and merges field by field in that order (a later, more precise release date that agrees wins). Covers: the DNB's cover service, Open Library's, Google's. A failing source is a warning, one without a record a note. Answer: the proposal plus `isbn` and `found`. 400 for an invalid ISBN. |
| GET | `/api/lookup/anilist?q=` | `{results: [{series, covers, match: {series_id}}]}` from AniList's GraphQL search (10). 400 under two characters, 502 when AniList fails. |
| GET | `/api/lookup/anilist/<id>` | One AniList entry; 404 when AniList has none. |
| POST | `/api/link-import` | `{url}`: the server fetches the page (4 MB); `{snapshot}`: what the bookmarklet read. The proposal plus `match`. 422 `{error, blocked}` when the page cannot be fetched (`blocked` for 401/403/429/503: use the bookmarklet). |

- AniList mapping: title = English or romaji; original title = native; other titles = romaji and synonyms (8); authors = staff with a Story or Art role; genres in German where the app's list has a word (Adventure -> Abenteuer …, Hentai dropped); demographic from a Demographic tag; status RELEASING/FINISHED/HIATUS/CANCELLED -> ongoing/completed/hiatus/cancelled; description without HTML and "(Source: …)".
- Link import (`extract(snapshot)`): JSON-LD Book/Product (isbn, gtin13, author, publisher, datePublished, numberOfPages, inLanguage, bookFormat, image, offers, isPartOf/position), meta tags (og:*, books:isbn, product:price), label/value pairs in German, English and Japanese (ISBN, Verlag, Erscheinungstermin, Seiten, Band, Reihe, Autor/Zeichner, Sprache, Format, Preis, Originaltitel); translators and the like are dropped from the people.

### fetch.py

- `fetch(url, max_bytes, accept)` -> `(final url, content type, bytes)` and `post_json(url, payload, max_bytes)` -> dict; both raise `FetchError` with a German message, `blocked` (401/403/429/503) and `status`. Only http(s), only hosts whose every address is global, redirects followed by hand (5, each checked; `post_json` follows none), 15 s timeout, size limit, user agent `Mozilla/5.0 (compatible; OphirMangas/1.0; +…)`.

## Dependencies

- `catalog` (field rules, folding, names), `fetch`, `web`; the DNB SRU service, Google Books, Open Library and AniList (all without a key)

## Decisions and assumptions

- Free sources without keys, DNB first, a barcode decoder of our own ([ADR-0003](../adr/0003-lookup-sources.md)).
- A proposal is never saved by the server: the volume, edition and series forms open filled in, in that order where the catalogue lacks something, so the user sees and corrects every field.
- The DNB's cover service is offered only when the DNB had a record, since it answers for any ISBN.
