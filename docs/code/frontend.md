# Browser frontend

`templates/index.html` plus plain scripts in `static/js/` that share one global scope (no build step, no framework), in this order: `core.js`, `scanner.js`, `mangas-ui.js`, `views.js`, `dashboard.js`, `settings.js`, `admin.js`, `import.js`, `main.js`. `filter-panel.js` and `stat-pill.js` define the custom elements `ophir-filter-panel` and `ophir-stat-pill`. The public profile has its own `static/public.js`.

## Public interface

### core.js

- `state` - `boot`, `route`, `edit` (quick edit: ＋ and ✓ on tiles and slots), filters per view (`catalogFilters`, `collectionFilters`, `watchFilters`, with `MANGA_FACETS()`), `grouping` per grid (`catalog`, `collection`, `watch`: `{by, sort, open}`; `by` is `''` for editions, `'volumes'` for single volumes, or a kind of group; it comes back from the setting `groupings`), `watchlistId`, `preorderStatus`, `readingStatus`, `modalEdition`, `modalVolume`, `modalTab`, `suggestions`.
- `APP_ROOT` / `appUrl(path)` - the path the app is served under, from `<html data-root>`; every address of the app goes through it (`api`, pictures, CSV and SSO links, the bookmarklet). `public.js` reads the same attribute.
- `api(url, options)`, `post`, `patch`, `del` - JSON; 401 goes to `/login`; a failed read is tried once more after 400 ms, a write is not.
- `routeTo(route)` - `dashboard`, `catalog`, `collection`, `reading`, `gaps`, `calendar`, `watchlist`, `preorders`, `settings`, `admin`; `renderGuard()`, `refreshCurrentView()`, `refreshCounts()`, `paintCounts()`.
- `openDialog({id, eyebrow, title, intro, body, stack, wide})` / `closeDialog()`; `fieldValues(root)`.
- Pictures: `volumeThumb`, `volumeImage`, `seriesThumb`, `coverThumb(cover, seriesId)` (an edition's cover, else the series' picture or placeholder). Labels: `languageLabel`, `readingLabel`, `seriesStatusLabel`, `demographicLabel`, `volumeLabel` ("Band 5", a special volume by title). `searchMatcher` (as search.py), `doSearch` (quick search: editions and volumes), `applyAppearance()` (cookie `ophir_mangas_theme`).

### scanner.js

- `decodeEan13({data, width, height})` - an EAN-13 from RGBA pixels: 24 lines across the middle (and columns for a sideways barcode), each split into light and dark runs against a sliding window, read forwards and backwards; the code must pass its check digit. `ean13Valid`, `isIsbnBarcode` (978/979).
- `openScanner({onIsbn})` - the dialog: camera picture (`getUserMedia`, back camera) read every 180 ms with `BarcodeDetector` where the browser has it, else `decodeEan13`; a photo (`capture=environment`) as the way without camera access; typing the ISBN. The camera stops when the dialog closes any way.

### mangas-ui.js

- Tiles and grids: `editionTile` (cover, owned/total, ★ collecting, gaps, VB, heart = whole edition on the default list, ＋ = the next missing volume, owned and read progress, next release), `volumeTile`, `renderGrid(container, items, {tile, empty})` (pages of 180), `quickAddVolume`, `quickAddNext`, `setRead`, `toggleEditionWish`, `toggleVolumeWish`.
- `filterBar` / `wireFilterBar` / `filterQuery`; groups: `groupSwitch` (Ausgaben · Bände · Reihe · Verlag · Autor:in · Genre · Sprache · Zielgruppe), `wireGroups`, `gridQuery`, `syncOpenGroup`, `openGroup`, `groupHead`, `groupTile`, `renderGroupGrid`, `restoreGroupings`.
- `openEdition(id)` - the edition dialog (`#edition-modal`): head with collect toggle, reading status, "Bände besitze ich …" (`openOwnRange`: ranges like `1-12, 14`, missing numbers created first), "Gelesen bis …" (`openReadThrough`), wish, new volume, edit; the slots (`slotHtml`: cover, number, read badge, release date, variants, gap/later outlines, quick ＋ and ✓ on hover or in quick edit; an empty slot creates its volume); special volumes; facts and other editions.
- `openVolume(id, tab)` - the volume dialog (`#volume-modal`, over the edition dialog) with previous/next and tabs `copies`, `preorders`, `value`, `lists`, `info`; `openSeriesDialog(id)`.
- Forms: `openSeriesForm` (AniList search fills it), `openEditionForm`, `openVolumeForm` (ISBN lookup and scan, cover choices from the lookup, "Danach": copy, catalogue only, copy and read, preorder, wish), `openEntryDialog`, `openPreorderDialog`, `openWishDialog(kind, id)`, `openImageDialog(kind, item)`; a duplicate (409) offers the existing entry or saving anyway.
- Adding: `openNewManga({isbn, title})` - ISBN (typed or scanned), link, or by hand (series search); `handleProposal(result)` opens the volume when the catalogue has it, else the volume form in the matched edition, else the editions of the matched series to choose from (`chooseEdition`), else series -> edition -> volume forms (`startNewSeries`, `startNewEdition`), each filled from the proposal.
- `parseNumbers`, `compactNumbers`, `bookmarkletHref()`, `handleImportFragment()` (`#import=<snapshot>` from the bookmarklet).

### views.js, dashboard.js, settings.js, admin.js, import.js, main.js

- `renderCatalog`, `renderCollection` (editions with gaps shown, or volumes with conditions and places), `renderReading` (rows by status with the next volume and "✓ Gelesen"), `renderGaps` (`gapRows`: catalogued gaps one by one, uncatalogued numbers in runs with "Alle anlegen"), `renderCalendar` (recent, then by month, with own/preorder buttons), `renderWatchlist`, `renderPreorders`, `pickVolume`, `scanToVolume` (a scanned ISBN opens its volume or the lookup); `renderDashboard` (summary, six quick links, continue reading, coming soon, gaps, recently out, latest additions); `renderSettings` (account, appearance, bookmarklet, public profile with wishlist and reading); `renderAdmin` (SSO, accounts, duplicates per level); `openImportExport`; `init()`.

## Tests

- `tests/frontend/unit.test.mjs` - the scripts in a vm context (`scripts.mjs`): formatting, labels, search matching, tiles, number ranges, preorder grouping, gap runs, groups, the EAN-13 decoder on synthetic barcodes (fractional module width, sideways, upside down, noise), the bookmarklet against a fake page, the app under a root, the slave views.
- `tests/frontend/smoke.test.mjs` - headless Chrome over the DevTools protocol (`harness.mjs`) against `serve.py`: every view; the catalogue filtered and an edition opened to its 34 slots and a volume's tabs; groups and the volume level remembered; an ISBN into an existing edition and the collection; a shop link through AniList to series, edition and volume; collecting, owning a range, reading through and the reading and gaps views following; wish -> preorder -> arrival; the scanner's typed fallback; settings; admin; the app under `/mangas` (every request has to carry the prefix).
- `tests/frontend/layout.test.mjs` - every view and what opens on it (groups, volume level, filter panel, edition dialog with quick buttons, own range, volume tabs, copy dialog, series dialog, new manga, volume form after a lookup, series form with AniList results, edition form, scanner, quick search, preorder dialog, import/export, public profile and edition, sign-in page, admin) in both appearances on 390 px and 1440 px: nothing past the right edge, every text at least 3:1 against its background, no console error. `OPHIR_SCREENSHOTS=<directory>` saves each state.
- `tests/frontend/serve.py <port> [<prefix>]` - the sample catalogue and fakes: ISBN 9783770430055 (Frieren 5, Egmont) and 9783551800015 (Blue Lock 1, Carlsen) answer from Google Books only, `https://shop.test/…` is a Blue Lock 2 page, AniList knows Blue Lock, every picture link gives a small PNG; with a prefix it stands in for Traefik's StripPrefix.
- On Windows, Chrome now and then gives up on a connection to the local server; `harness.mjs` retries sign-in and views (as in Ophir Figures).

## Decisions and assumptions

- The look and the shared components are Ophir Figures' and keep their `fig-*` names, so `design-system.css` and the component styles stay portable between the Ophir apps; manga components are `mg-*` at the end of `mangas.css`. Shared fixes go into `design-system.css` for every page at once (here: stat-pill labels with room for the dots of capital umlauts).
- Both appearances from the start: every colour comes from the design steps (`--ds-*`) or a pair of manga tokens defined for light and dark (`--mg-read`, `--mg-warn-bg`, `--mg-later`), checked by the layout test.
- Slots of numbers the catalogue lacks are drawn as places to create the volume, so an edition shows its full length (34 numbers for a completed edition of 34) and the shelf can be brought in quickly.
- No service worker and no offline mode.
