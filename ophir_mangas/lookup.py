"""Filling in volumes and series from free bibliographic services (docs/adr/0003).

- GET /api/lookup/isbn/<isbn> asks the Deutsche Nationalbibliothek (SRU, MARC 21), Google Books and
  Open Library about a volume, each on its own -- one that is down or knows nothing costs a
  warning, never the answer -- and merges what they say field by field in that order: the DNB has
  the publisher's price and the series numbering of German volumes, which are most of what is
  collected here; the others fill the gaps (a description, the day of the release).
- GET /api/lookup/anilist?q= and /api/lookup/anilist/<id> read a series from AniList's public
  GraphQL API.

Every answer is a *proposal*: what the forms for a volume, its edition and its series would be
filled with, candidate covers, and where in the catalogue it belongs already (match_catalogue,
which the link import uses as well). Nothing is saved here; the user checks the form and saves.
"""

import json
import re
import xml.etree.ElementTree as ElementTree
from html import unescape

from flask import jsonify, request

from . import search
from .catalog import DESCRIPTION_LIMIT, LANGUAGES, FieldError, edition_name, fold_key, normalize_date, normalize_isbn, number_label, \
    parse_volume_number, split_list
from .fetch import FetchError, fetch, post_json
from .web import app, db, login_required

MAX_ANSWER_BYTES = 2 * 1024 * 1024
DNB_URL = ("https://services.dnb.de/sru/dnb?version=1.1&operation=searchRetrieve&query=num%3D{isbn}"
           "&recordSchema=MARC21-xml&maximumRecords=3")
GOOGLE_URL = "https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
OPENLIBRARY_URL = "https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
DNB_COVER = "https://portal.dnb.de/opac/mvb/cover?isbn={isbn}"
OPENLIBRARY_COVER = "https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false"
ANILIST_URL = "https://graphql.anilist.co"
MARC = "{http://www.loc.gov/MARC21/slim}"

SOURCE_NAMES = {"dnb": "Deutsche Nationalbibliothek", "google": "Google Books", "openlibrary": "Open Library"}
NOTHING_FOUND = "Zu dieser ISBN hat keine der Quellen (DNB, Google Books, Open Library) etwas gefunden."
# What reading a source's answer fails with when it is not what was expected (broken XML or JSON, odd shapes).
UNREADABLE = (ValueError, TypeError, AttributeError, KeyError, SyntaxError)

VOLUME_KEYS = ("number", "title", "variant", "isbn", "release_date", "list_price", "currency", "pages", "description", "image_url", "source_url")
EDITION_KEYS = ("title", "label", "publisher", "language", "format", "list_price", "currency")
SERIES_KEYS = ("title", "original_title", "alt_titles", "authors", "genres", "demographic", "status", "original_volumes", "start_year",
               "description", "image_url", "source_url", "anilist_id")

# MARC language codes (041, 008) and the language names shops print -> the catalogue's codes.
LANGUAGE_CODES = {
    "ger": "de", "deu": "de", "deutsch": "de", "german": "de", "jpn": "ja", "japanisch": "ja", "japanese": "ja", "日本語": "ja",
    "eng": "en", "englisch": "en", "english": "en", "fre": "fr", "fra": "fr", "französisch": "fr", "french": "fr",
    "ita": "it", "italienisch": "it", "italian": "it", "spa": "es", "spanisch": "es", "spanish": "es",
    "kor": "ko", "koreanisch": "ko", "korean": "ko", "chi": "zh", "zho": "zh", "chinesisch": "zh", "chinese": "zh",
}
# Words that do not tell two publishers apart: "Carlsen Verlag GmbH" is the catalogue's "Carlsen".
PUBLISHER_NOISE = {"verlag", "gmbh", "co", "kg", "ag", "inc", "ltd", "llc", "publishing", "publishers", "manga", "books", "media"}

# A volume number after a word that says so may have four digits, a bare one only three: a year in
# brackets is no volume number.
MARKED_NUMBER = re.compile(r"^(?P<title>.*?)[\s,:;–—-]*(?:\b(?:band|bd|vol|volume|nr|tome|teil)\b\.?|#|第)\s*"
                           r"(?P<number>\d{1,4}(?:[.,]\d{1,2})?)\s*巻?$", re.I)
BRACKETED_NUMBER = re.compile(r"^(?P<title>.*?)\s*[(（]\s*(?P<number>\d{1,3}(?:[.,]\d{1,2})?)\s*[)）]$")
TRAILING_NUMBER = re.compile(r"^(?P<title>.*\S)[\s,:;–—-]+(?P<number>\d{1,3}(?:[.,]\d{1,2})?)$")

ANILIST_MEDIA = """id title { romaji english native } synonyms staff(perPage: 8) { edges { role node { name { full } } } }
  genres tags { name category } status volumes startDate { year } coverImage { extraLarge large }
  description(asHtml: false) countryOfOrigin siteUrl format"""
ANILIST_SEARCH = "query ($search: String) { Page(perPage: 10) { media(search: $search, type: MANGA, sort: SEARCH_MATCH) { %s } } }" % ANILIST_MEDIA
ANILIST_ONE = "query ($id: Int) { Media(id: $id, type: MANGA) { %s } }" % ANILIST_MEDIA
# AniList's genres where the app's list (catalog.GENRES) has a German word for them.
ANILIST_GENRES = {"Adventure": "Abenteuer", "Psychological": "Psychologie", "Sci-Fi": "Science-Fiction", "Sports": "Sport",
                  "Supernatural": "Übernatürliches"}
ANILIST_DEMOGRAPHICS = {"Shounen": "shounen", "Seinen": "seinen", "Shoujo": "shoujo", "Josei": "josei", "Kids": "kodomo"}
ANILIST_STATUSES = {"RELEASING": "ongoing", "FINISHED": "completed", "HIATUS": "hiatus", "CANCELLED": "cancelled"}
ANILIST_ALT_TITLES = 8


# --- The proposal and where it belongs in the catalogue ------------------------------------------

def present(value):
    return value is not None and value != "" and value != []


def compact(section, keys):
    """The section's keys that have a value, in the shape's order."""
    fields = {}
    for key in keys:
        value = section.get(key)
        value = value.strip() if isinstance(value, str) else value
        if present(value):
            fields[key] = value
    return fields


def build_proposal(volume=None, edition=None, series=None, covers=(), sources=(), warnings=()):
    """The answer the lookups and the link import share: {volume, edition, series, covers, sources,
    warnings}, with only the fields something was found for. The caller adds `match`
    (match_catalogue)."""
    return {"volume": compact(volume or {}, VOLUME_KEYS), "edition": compact(edition or {}, EDITION_KEYS),
            "series": compact(series or {}, SERIES_KEYS), "covers": list(dict.fromkeys(url for url in covers if url)),
            "sources": list(sources), "warnings": list(warnings)}


def publisher_key(name):
    words = [word for word in search.field_words(name or "")[0] if word not in PUBLISHER_NOISE]
    return "".join(words) or fold_key(name)


def find_series(connection, series):
    """The catalogue's series a proposal is about: the same AniList entry, or a title or original
    title that is a series' title, original title or one of its other titles -- failing that, the
    printed title of one of its editions ("Frieren" for Frieren – Nach dem Ende der Reise).
    Id or None."""
    if series.get("anilist_id"):
        row = connection.execute("SELECT id FROM series WHERE anilist_id=? ORDER BY id LIMIT 1", (series["anilist_id"],)).fetchone()
        if row:
            return row["id"]
    keys = {fold_key(series.get(key)) for key in ("title", "original_title") if series.get(key)} - {""}
    if not keys:
        return None
    for row in connection.execute("SELECT id,title,original_title,alt_titles FROM series ORDER BY id"):
        names = {fold_key(row["title"]), fold_key(row["original_title"]), *(fold_key(name) for name in split_list(row["alt_titles"]))}
        if names & keys:
            return row["id"]
    for row in connection.execute("SELECT series_id,title FROM editions WHERE title!='' ORDER BY id"):
        if fold_key(row["title"]) in keys:
            return row["series_id"]
    return None


def find_edition(connection, series_id, edition):
    """The edition of the series with the proposal's publisher (and language, when known). Label
    and format only decide between several such editions; no label means the standard one."""
    publisher = publisher_key(edition.get("publisher"))
    if not publisher:
        return None
    language = edition.get("language")
    rows = connection.execute("SELECT id,label,publisher,language,format FROM editions WHERE series_id=? ORDER BY id", (series_id,))
    candidates = [row for row in rows if publisher_key(row["publisher"]) == publisher and (not language or row["language"] == language)]
    if len(candidates) > 1:
        candidates = [row for row in candidates if fold_key(row["label"]) == fold_key(edition.get("label"))] or candidates
    if len(candidates) > 1 and edition.get("format"):
        candidates = [row for row in candidates if fold_key(row["format"]) == fold_key(edition["format"])] or candidates
    return candidates[0]["id"] if len(candidates) == 1 else None


def find_volume(connection, edition_id, volume):
    """A volume of the edition with the proposal's number and variant that has no ISBN yet -- one
    with another ISBN is another book."""
    try:
        number = parse_volume_number(volume.get("number"))
    except FieldError:
        return None
    if number is None:
        return None
    for row in connection.execute("SELECT id,variant FROM volumes WHERE edition_id=? AND number=? AND isbn='' ORDER BY id", (edition_id, number)):
        if fold_key(row["variant"]) == fold_key(volume.get("variant")):
            return row["id"]
    return None


def match_catalogue(connection, proposal):
    """Where the proposal belongs in the catalogue: the volume with its ISBN (and with it its
    edition and series), else the series by AniList entry or title and the edition by publisher
    and language. Lists the series' editions, so the form can offer them."""
    volume, edition, series = (proposal.get(key) or {} for key in ("volume", "edition", "series"))
    volume_id = edition_id = series_id = None
    if volume.get("isbn"):
        row = connection.execute("""SELECT v.id, v.edition_id, e.series_id FROM volumes v JOIN editions e ON e.id=v.edition_id
                                    WHERE v.isbn=? ORDER BY v.id LIMIT 1""", (volume["isbn"],)).fetchone()
        if row:
            volume_id, edition_id, series_id = row["id"], row["edition_id"], row["series_id"]
    if series_id is None:
        series_id = find_series(connection, series)
    if series_id is not None and edition_id is None:
        edition_id = find_edition(connection, series_id, edition)
        if edition_id is not None:
            volume_id = find_volume(connection, edition_id, volume)
    editions = []
    if series_id is not None:
        title = connection.execute("SELECT title FROM series WHERE id=?", (series_id,)).fetchone()["title"]
        rows = connection.execute("SELECT id,title,label,publisher,language,format FROM editions WHERE series_id=? ORDER BY id", (series_id,))
        editions = [{"id": row["id"], "name": edition_name(row, title), "publisher": row["publisher"], "language": row["language"],
                     "format": row["format"]} for row in rows]
    return {"volume_id": volume_id, "edition_id": edition_id, "series_id": series_id, "editions": editions}


# --- Reading what services and shops write -------------------------------------------------------

def split_title_number(text):
    """'Attack on Titan 5', 'Attack on Titan, Band 5', 'Frieren Vol. 3', '進撃の巨人(5)', '進撃の巨人 第5巻'
    -> (series title, number label); (text, '') when no volume number is in it. A bare number after
    "No." belongs to the title (Kaiju No. 8)."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    text = re.sub(r"\s*[(（]((?:band|bd|vol|volume)\.?\s*\d[^)）]*)[)）]$", r" \1", text, flags=re.I)   # "Attack on Titan (Band 5)"
    for pattern in (MARKED_NUMBER, BRACKETED_NUMBER, TRAILING_NUMBER):
        match = pattern.match(text)
        if not match or (pattern is TRAILING_NUMBER and (re.search(r"\b(?:no|nr)\.?$", match["title"], re.I)
                                                         or not re.search(r"[^\W\d_]", match["title"]))):
            continue
        try:
            number = parse_volume_number(match["number"])
        except FieldError:
            continue
        return match["title"].rstrip(" ,:;–—-"), number_label(number)
    return text, ""


def volume_label(text):
    """'Band 5', '5', 'Bd. 5', 'Vol. 10.5', '5 von 34' -> '5' / '10.5'; '' when there is no number."""
    match = re.search(r"\d{1,4}(?:[.,]\d{1,2})?", str(text or ""))
    if not match:
        return ""
    try:
        return number_label(parse_volume_number(match.group(0)))
    except FieldError:
        return ""


def language_code(value):
    """'ger', 'de-DE', 'Deutsch', 'German' -> 'de'; '' for a language the catalogue does not know."""
    text = str(value or "").strip().lower()
    if text in LANGUAGE_CODES:
        return LANGUAGE_CODES[text]
    short = re.split(r"[-_\s]", text)[0] if text else ""
    return short if short in LANGUAGES else LANGUAGE_CODES.get(short, "")


def parse_date(text):
    """A (possibly partial) ISO date from what a service writes: '2014-12-02', '[2014]', 'Dec 2, 2014',
    'März 2015'. '' when there is none."""
    text = re.sub(r"[\[\]©℗]", " ", str(text or "")).strip(" .")
    value, error = normalize_date(text)
    if value and not error:
        return value
    american = re.fullmatch(r"([A-Za-zäÄ]+)\.?\s+(\d{1,2}),?\s+(\d{4})", text)
    if american:
        value, error = normalize_date(f"{american[2]}. {american[1]} {american[3]}")
        if value and not error:
            return value
    year = re.search(r"(?<!\d)(19\d\d|2[01]\d\d)(?!\d)", text)
    return year.group(1) if year else ""


def euro_price(terms):
    """'kart. : EUR 7.50 (DE), EUR 7.80 (AT), sfr 10.50 (freier Pr.)' -> 7.5: the German price, else
    the first one in euros. None when there is none."""
    prices = re.findall(r"EUR\s*(\d{1,4}(?:[.,]\d{1,2})?)\s*(?:\(([^)]*)\))?", terms or "", re.I)
    if not prices:
        prices = [(amount, "") for amount in re.findall(r"(\d{1,4}(?:[.,]\d{1,2})?)\s*(?:EUR|€)", terms or "", re.I)]
    for amount, country in prices:
        if country.strip().upper() == "DE":
            return float(amount.replace(",", "."))
    return float(prices[0][0].replace(",", ".")) if prices else None


def https(url):
    return re.sub(r"^http://", "https://", str(url or "").strip())


def plain_text(text):
    """A description without HTML and without AniList's "(Source: …)" notes, at most DESCRIPTION_LIMIT long."""
    text = re.sub(r"<br\s*/?>", "\n", str(text or ""), flags=re.I)
    text = unescape(re.sub(r"<[^>]+>", "", text))
    text = re.sub(r"\(\s*Source:[^)]*\)|\[\s*Written by[^\]]*\]", "", text, flags=re.I)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()[:DESCRIPTION_LIMIT]


# --- Deutsche Nationalbibliothek (SRU, MARC 21) -------------------------------------------------

def marc_text(value):
    """A MARC subfield without the DNB's non-sorting marks (¬Die¬) and the ISBD punctuation that
    ends it (" :", " /", ";", ",", ".")."""
    text = re.sub(r"\s+", " ", re.sub(r"[\u0098\u009c¬]", "", str(value or ""))).strip()
    text = re.sub(r"[\s:;/,=]+$", "", text)
    return re.sub(r"(?<![.\s])\.$", "", text).strip()


def subfields(field, code):
    return [text for text in (marc_text(sub.text) for sub in field.findall(f"{MARC}subfield") if sub.get("code") == code) if text]


def datafields(record, *tags):
    return [field for field in record.findall(f"{MARC}datafield") if field.get("tag") in tags]


def first_subfield(record, tag, code):
    return next((value for field in datafields(record, tag) for value in subfields(field, code)), "")


def controlfield(record, tag):
    return next((field.text or "" for field in record.findall(f"{MARC}controlfield") if field.get("tag") == tag), "")


def field_isbns(field):
    isbns = set()
    for value in subfields(field, "a"):
        try:
            isbns.add(normalize_isbn(value.split()[0]))
        except FieldError:
            pass
    return isbns


AUTHOR_CODES = {"aut", "art", "ill", "cre", "author", "artist", "illustrator"}
AUTHOR_WORDS = ("verfass", "autor", "zeichn", "illustr", "künstl", "author", "artist")


def is_author(field):
    """Whether a person field names an author or artist rather than the translator or an editor
    (700 $4 trl): roles come as relator codes ($4, sometimes as URIs) or words ($e)."""
    codes = {re.split(r"[/#]", code)[-1].lower() for code in subfields(field, "4")}
    roles = " ".join(subfields(field, "e")).lower()
    if not codes and not roles:
        return True
    return bool(codes & AUTHOR_CODES) or any(word in roles for word in AUTHOR_WORDS)


def person_name(text):
    """'Isayama, Hajime' -> 'Hajime Isayama'; life dates left in the name are dropped."""
    parts = [part.strip() for part in marc_text(text).split(",") if part.strip() and not re.fullmatch(r"[\d\s.?–-]+", part.strip())]
    return f"{parts[1]} {parts[0]}" if len(parts) >= 2 else (parts[0] if parts else "")


def dnb_series(record, title, part_number):
    """(series title, number): from a series statement with a volume ($v) -- 490 $a, 800 $t, 830 $a --
    else from the title proper and its part number (245 $a $n). A series statement without $v is
    mostly the publisher's imprint ("Carlsen Manga!"), not the work."""
    for field in datafields(record, "490", "800", "830"):
        names = subfields(field, "t") or ([] if field.get("tag") == "800" else subfields(field, "a"))
        number = volume_label(" ".join(subfields(field, "v")))
        if names and number:
            return names[0], number
    if part_number:
        return title, volume_label(part_number)
    return split_title_number(title)


def dnb_release(record):
    """The projected release month of a forthcoming volume (263, YYYYMM), else the year of
    publication (264/260 $c, else 008)."""
    year = parse_date(first_subfield(record, "264", "c") or first_subfield(record, "260", "c")) or parse_date(controlfield(record, "008")[7:11])
    projected = re.fullmatch(r"(\d{4})(\d{2})(\d{2})?", re.sub(r"\D", "", first_subfield(record, "263", "a")))
    if projected and (not year or year.startswith(projected[1])):
        value, error = normalize_date("-".join(part for part in projected.groups() if part))
        if value and not error:
            return value
    return year


def dnb_price(record, isbn):
    """The price on the record's 020 for this ISBN, else on any 020 that has one in euros."""
    fallback = None
    for field in datafields(record, "020"):
        price = euro_price(" ".join(subfields(field, "c")))
        if price is None:
            continue
        if isbn in field_isbns(field):
            return price
        fallback = price if fallback is None else fallback
    return fallback


def dnb_edition_statement(record):
    """(variant, label) from the edition statement (250): "Limited Edition" makes a variant, "Perfect
    Edition" names the edition; a printing ("1. Auflage") says nothing about either."""
    statement = first_subfield(record, "250", "a")
    if re.search(r"limit|special|collector|deluxe|sonderedition|schuber|box", statement, re.I):
        return statement, ""
    if statement and not re.search(r"auflage|aufl\b|druck|ausgabe$|^\d+\.?$", statement, re.I):
        return "", statement
    return "", ""


def parse_dnb(body, isbn):
    """The DNB's record for the ISBN as a partial proposal, or None when it has none."""
    root = ElementTree.fromstring(body)
    records = list(root.iter(f"{MARC}record"))
    if not records:
        return None
    record = next((candidate for candidate in records if any(isbn in field_isbns(field) for field in datafields(candidate, "020"))), records[0])

    title, subtitle = first_subfield(record, "245", "a"), first_subfield(record, "245", "b")
    part_number, part_name = first_subfield(record, "245", "n"), first_subfield(record, "245", "p")
    series_title, number = dnb_series(record, title, part_number)
    own_title = part_name
    if not own_title and title and fold_key(split_title_number(title)[0]) != fold_key(series_title):
        own_title = title
    if not own_title and not number:
        own_title = subtitle   # a special volume: "Attack on Titan : Inside"

    authors = []
    for field in datafields(record, "100", "700"):
        name = person_name((subfields(field, "a") or [""])[0]) if is_author(field) else ""
        if name and name not in authors:
            authors.append(name)
    publisher = (next((value for field in datafields(record, "264") if field.get("ind2") == "1" for value in subfields(field, "b")), "")
                 or first_subfield(record, "264", "b") or first_subfield(record, "260", "b"))
    pages = re.search(r"(\d{1,4})\]?\s+(?:ungezählte\s+|unnummerierte\s+)?(?:Seiten|S\b|pages|p\b)", first_subfield(record, "300", "a"))
    language = language_code(first_subfield(record, "041", "a")) or language_code(controlfield(record, "008")[35:38])
    price = dnb_price(record, isbn)
    currency = "EUR" if price is not None else ""
    variant, label = dnb_edition_statement(record)
    idn = controlfield(record, "001").strip()
    return {
        "volume": {"number": number, "title": own_title, "variant": variant, "isbn": isbn, "release_date": dnb_release(record),
                   "list_price": price, "currency": currency, "pages": int(pages.group(1)) if pages else None,
                   "description": first_subfield(record, "520", "a"), "source_url": f"https://d-nb.info/{idn}" if idn else ""},
        "edition": {"label": label, "publisher": publisher, "language": language, "list_price": price, "currency": currency},
        "series": {"title": series_title, "authors": ", ".join(authors)},
        "cover": DNB_COVER.format(isbn=isbn),
    }


# --- Google Books and Open Library ---------------------------------------------------------------

def parse_google(body, isbn):
    items = json.loads(body).get("items") or []
    if not items:
        return None
    info = items[0].get("volumeInfo") or {}
    series_title, number = split_title_number(info.get("title"))
    if not number and info.get("subtitle"):
        rest, subtitle_number = split_title_number(info["subtitle"])   # subtitle "Band 3"
        number = "" if rest else subtitle_number
    links = info.get("imageLinks") or {}
    image = next((links[key] for key in ("extraLarge", "large", "medium", "small", "thumbnail", "smallThumbnail") if links.get(key)), "")
    return {
        "volume": {"number": number, "isbn": isbn, "release_date": parse_date(info.get("publishedDate")), "pages": info.get("pageCount") or None,
                   "description": plain_text(info.get("description")), "source_url": info.get("infoLink") or info.get("canonicalVolumeLink") or ""},
        "edition": {"publisher": info.get("publisher") or "", "language": language_code(info.get("language"))},
        "series": {"title": series_title, "authors": ", ".join(split_list(info.get("authors") or []))},
        "cover": https(image).replace("&edge=curl", "") if image else "",
    }


def parse_openlibrary(body, isbn):
    record = json.loads(body).get(f"ISBN:{isbn}")
    if not isinstance(record, dict) or not record:
        return None

    def names(key):
        return [item["name"] for item in record.get(key) or [] if isinstance(item, dict) and item.get("name")]

    series_title, number = split_title_number(record.get("title"))
    return {
        "volume": {"number": number, "isbn": isbn, "release_date": parse_date(record.get("publish_date")),
                   "pages": record.get("number_of_pages") or None, "source_url": record.get("url") or ""},
        "edition": {"publisher": (names("publishers") or [""])[0]},
        "series": {"title": series_title, "authors": ", ".join(split_list(names("authors")))},
        "cover": https((record.get("cover") or {}).get("large")) or OPENLIBRARY_COVER.format(isbn=isbn),
    }


SOURCES = (("dnb", DNB_URL, "application/xml", parse_dnb), ("google", GOOGLE_URL, "application/json", parse_google),
           ("openlibrary", OPENLIBRARY_URL, "application/json", parse_openlibrary))


def ask_sources(isbn):
    """What each source has on the ISBN: [(source, partial proposal)] for those with a record,
    warnings for those that failed, and notes for those without a record."""
    records, warnings, empty = [], [], []
    for key, url, accept, parse in SOURCES:
        name = SOURCE_NAMES[key]
        try:
            _, _, body = fetch(url.format(isbn=isbn), MAX_ANSWER_BYTES, accept=accept)
            record = parse(body, isbn)
        except FetchError as error:
            warnings.append(f"{name} nicht erreichbar: {error}")
            continue
        except UNREADABLE:
            warnings.append(f"{name} hat eine unlesbare Antwort geschickt.")
            continue
        if record:
            records.append((key, record))
        else:
            empty.append(f"{name} kennt diese ISBN nicht.")
    return records, warnings, empty


def merge(records):
    """The sources' fields, the first source's value for each (DNB, Google, Open Library); a release
    date is made more precise by a later source that agrees with it ('2015' -> '2015-02-03')."""
    merged = {"volume": {}, "edition": {}, "series": {}}
    for _, record in records:
        for section, fields in merged.items():
            for key, value in (record.get(section) or {}).items():
                if not present(value):
                    continue
                current = fields.get(key)
                if not present(current):
                    fields[key] = value
                elif key == "release_date" and len(value) > len(current) and value.startswith(current):
                    fields[key] = value
    return merged


@app.get("/api/lookup/isbn/<isbn>")
@login_required
def lookup_isbn(isbn):
    try:
        isbn = normalize_isbn(isbn)
    except FieldError as error:
        return jsonify({"error": str(error)}), 400
    if not isbn:
        return jsonify({"error": "Bitte eine ISBN angeben."}), 400
    records, warnings, empty = ask_sources(isbn)
    merged, by_source = merge(records), dict(records)
    covers = [by_source[key]["cover"] for key in ("dnb", "openlibrary", "google") if by_source.get(key, {}).get("cover")]
    volume = {**merged["volume"], "isbn": isbn, "image_url": covers[0] if covers else ""}
    warnings += empty if records else [NOTHING_FOUND]
    proposal = build_proposal(volume, merged["edition"], merged["series"], covers, [key for key, _ in records], warnings)
    proposal["match"] = match_catalogue(db(), proposal)
    return jsonify({**proposal, "isbn": isbn, "found": bool(records)})


# --- AniList -------------------------------------------------------------------------------------

def ask_anilist(query, variables):
    """The data of an AniList GraphQL answer. Raises FetchError."""
    answer = post_json(ANILIST_URL, {"query": query, "variables": variables}, MAX_ANSWER_BYTES)
    if not isinstance(answer.get("data"), dict):
        raise FetchError("AniList hat die Anfrage nicht beantwortet.")
    return answer["data"]


def anilist_series(media):
    """An AniList Media entry as series fields."""
    titles = media.get("title") or {}
    title = (titles.get("english") or titles.get("romaji") or "").strip()
    native = (titles.get("native") or "").strip()
    seen, alt_titles = {fold_key(title), fold_key(native)}, []
    for name in [titles.get("romaji"), *(media.get("synonyms") or [])]:
        name = str(name or "").strip()
        # The catalogue keeps other titles as a comma-separated list: one with a comma would fall apart.
        if not name or re.search(r"[,;]", name) or fold_key(name) in seen or len(alt_titles) >= ANILIST_ALT_TITLES:
            continue
        seen.add(fold_key(name))
        alt_titles.append(name)
    authors = []
    for edge in (media.get("staff") or {}).get("edges") or []:
        role = str(edge.get("role") or "")
        name = str((((edge.get("node") or {}).get("name") or {}).get("full")) or "").strip()
        if name and ("Story" in role or "Art" in role) and name not in authors:
            authors.append(name)
    genres = [ANILIST_GENRES.get(genre, genre) for genre in media.get("genres") or [] if genre and genre != "Hentai"]
    demographic = next((ANILIST_DEMOGRAPHICS[tag.get("name")] for tag in media.get("tags") or []
                        if tag.get("category") == "Demographic" and tag.get("name") in ANILIST_DEMOGRAPHICS), "")
    cover = media.get("coverImage") or {}
    return {
        "title": title, "original_title": native, "alt_titles": ", ".join(alt_titles), "authors": ", ".join(authors),
        "genres": ", ".join(dict.fromkeys(genres)), "demographic": demographic, "status": ANILIST_STATUSES.get(media.get("status"), ""),
        "original_volumes": media.get("volumes") or None, "start_year": (media.get("startDate") or {}).get("year") or None,
        "description": plain_text(media.get("description")), "image_url": cover.get("extraLarge") or cover.get("large") or "",
        "source_url": media.get("siteUrl") or "", "anilist_id": media.get("id"),
    }


def anilist_entry(connection, media):
    cover = media.get("coverImage") or {}
    proposal = build_proposal(series=anilist_series(media), covers=[cover.get("extraLarge"), cover.get("large")])
    return {"series": proposal["series"], "covers": proposal["covers"], "match": {"series_id": find_series(connection, proposal["series"])}}


def anilist_failed(error):
    return jsonify({"error": f"AniList ist gerade nicht erreichbar: {error}"}), 502


@app.get("/api/lookup/anilist")
@login_required
def lookup_anilist():
    text = request.args.get("q", "").strip()
    if len(text) < 2:
        return jsonify({"error": "Bitte mindestens zwei Zeichen eingeben."}), 400
    try:
        data = ask_anilist(ANILIST_SEARCH, {"search": text[:200]})
    except FetchError as error:
        return anilist_failed(error)
    connection = db()
    return jsonify({"results": [anilist_entry(connection, media) for media in (data.get("Page") or {}).get("media") or []
                                if isinstance(media, dict)]})


@app.get("/api/lookup/anilist/<int:anilist_id>")
@login_required
def lookup_anilist_entry(anilist_id):
    try:
        media = ask_anilist(ANILIST_ONE, {"id": anilist_id}).get("Media")
    except FetchError as error:
        if error.status != 404:   # AniList answers an unknown id with 404
            return anilist_failed(error)
        media = None
    if not isinstance(media, dict):
        return jsonify({"error": "Diesen Eintrag gibt es bei AniList nicht."}), 404
    return jsonify(anilist_entry(db(), media))
