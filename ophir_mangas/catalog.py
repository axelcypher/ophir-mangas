"""The catalogue's shared rules: what a series, an edition and a volume may hold, how dates, ISBNs,
volume numbers and amounts are read from a form, and when two entries are the same.

The catalogue has three levels (docs/adr/0001): a series is the work, an edition one publisher's
publication of it in one language and format, a volume one numbered book of an edition. It is
shared by every account; anyone signed in adds and corrects entries, like a small wiki.
"""

import json
import re
from datetime import date

from . import search
from .config import CURRENCY
from .prices import parse_amount

LANGUAGES = {"de": "Deutsch", "ja": "Japanisch", "en": "Englisch", "fr": "Französisch", "it": "Italienisch", "es": "Spanisch",
             "ko": "Koreanisch", "zh": "Chinesisch"}
# Of a series in its country of origin and of an edition alike.
STATUSES = {"ongoing": "Laufend", "completed": "Abgeschlossen", "hiatus": "Pausiert", "cancelled": "Eingestellt"}
DEMOGRAPHICS = {"shounen": "Shōnen", "seinen": "Seinen", "shoujo": "Shōjo", "josei": "Josei", "kodomo": "Kodomo"}
# Offered in the forms; any other text is allowed too.
FORMATS = ("Taschenbuch", "Großformat", "Sammelband", "Hardcover", "Tankōbon", "Bunkoban", "Kanzenban", "Digital")
GENRES = ("Action", "Abenteuer", "Comedy", "Drama", "Fantasy", "Horror", "Mystery", "Psychologie", "Romance", "Science-Fiction",
          "Slice of Life", "Sport", "Thriller", "Übernatürliches", "Historisch", "Isekai", "Boys' Love", "Girls' Love")
CURRENCIES = ("EUR", "JPY", "USD", "GBP", "CHF", "CAD", "AUD")
TEXT_LIMIT, DESCRIPTION_LIMIT = 300, 5000
NUMBER_LIMIT = 9999
MONTHS = {"jan": 1, "januar": 1, "january": 1, "feb": 2, "februar": 2, "february": 2, "mar": 3, "mär": 3, "märz": 3, "march": 3,
          "apr": 4, "april": 4, "may": 5, "mai": 5, "jun": 6, "juni": 6, "june": 6, "jul": 7, "juli": 7, "july": 7,
          "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "okt": 10, "oktober": 10, "october": 10,
          "nov": 11, "november": 11, "dec": 12, "dez": 12, "dezember": 12, "december": 12}

SERIES_TEXT = ("title", "original_title", "alt_titles", "authors", "genres")
EDITION_TEXT = ("title", "label", "publisher", "format")
VOLUME_TEXT = ("title", "variant")
LIST_FIELDS = ("alt_titles", "authors", "genres")


class FieldError(ValueError):
    """A form value that cannot be taken; the message is shown to the user (German)."""


def normalize_date(value, field="Datum"):
    """'2025', '2025-03', '2025-03-14', '03/2025', '14.03.2025', 'March 2025', '2025年3月' ->
    ISO with as much precision as given. (value, error); empty stays empty."""
    text = str(value or "").strip()
    if not text:
        return "", None
    text = text.replace("年", "-").replace("月", "-").replace("日", "").strip("- ")
    patterns = (
        (r"(\d{4})", lambda m: (int(m[1]), None, None)),
        (r"(\d{4})[-/.](\d{1,2})", lambda m: (int(m[1]), int(m[2]), None)),
        (r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", lambda m: (int(m[1]), int(m[2]), int(m[3]))),
        (r"(\d{1,2})[/.](\d{4})", lambda m: (int(m[2]), int(m[1]), None)),
        (r"(\d{1,2})\.(\d{1,2})\.(\d{4})", lambda m: (int(m[3]), int(m[2]), int(m[1]))),
        (r"(\d{1,2})/(\d{1,2})/(\d{4})", lambda m: (int(m[3]), int(m[1]), int(m[2]))),   # US: 03/14/2025
        (r"([A-Za-zäÄ]+)\.?\s+(\d{4})", lambda m: (int(m[2]), MONTHS.get(m[1].lower()), None) if MONTHS.get(m[1].lower()) else None),
        (r"(\d{1,2})\.?\s+([A-Za-zäÄ]+)\.?\s+(\d{4})",
         lambda m: (int(m[3]), MONTHS.get(m[2].lower()), int(m[1])) if MONTHS.get(m[2].lower()) else None),
    )
    for pattern, build in patterns:
        match = re.fullmatch(pattern, text)
        parts = build(match) if match else None
        if not parts:
            continue
        year, month, day = parts
        try:
            if day:
                return date(year, month, day).isoformat(), None
            if month:
                date(year, month, 1)
                return f"{year:04d}-{month:02d}", None
            if 1900 <= year <= 2200:
                return f"{year:04d}", None
        except ValueError:
            break
    return None, f"{field} „{value}“ ist kein Datum (z. B. 2025-03 oder 14.03.2025)."


def is_released(release_date, today):
    """Whether a volume with this (possibly partial) release date is out on `today` (ISO date).
    A month counts once it is over, a year likewise; no date at all counts as out -- volumes
    entered without one are almost always old ones."""
    if not release_date:
        return True
    if len(release_date) >= 10:
        return release_date[:10] <= today
    return release_date < today[:len(release_date)]


def split_list(value):
    """"Kanehito Yamada, Tsukasa Abe; Action" -> ["Kanehito Yamada", "Tsukasa Abe", "Action"]."""
    if isinstance(value, (list, tuple)):
        parts = value
    else:
        parts = re.split(r"\s*[,;]\s*|\s+/\s+", str(value or ""))
    return list(dict.fromkeys(str(part).strip() for part in parts if str(part).strip()))


def isbn13_check(digits12):
    total = sum(int(digit) * (1 if index % 2 == 0 else 3) for index, digit in enumerate(digits12))
    return str((10 - total % 10) % 10)


def normalize_isbn(value):
    """An ISBN as typed or scanned (with hyphens, as ISBN-10 or -13) -> the 13 digits, '' for none.
    Raises FieldError for something that is no valid ISBN."""
    text = re.sub(r"[\s\-‐‑–.]", "", str(value or "")).upper().removeprefix("ISBN").lstrip(":")
    if not text:
        return ""
    if re.fullmatch(r"\d{9}[\dX]", text):
        total = sum((10 - index) * (10 if char == "X" else int(char)) for index, char in enumerate(text))
        if total % 11:
            raise FieldError(f"„{value}“ ist keine gültige ISBN (Prüfziffer stimmt nicht).")
        core = "978" + text[:9]
        return core + isbn13_check(core)
    if re.fullmatch(r"97[89]\d{10}", text):
        if isbn13_check(text[:12]) != text[12]:
            raise FieldError(f"„{value}“ ist keine gültige ISBN (Prüfziffer stimmt nicht).")
        return text
    raise FieldError(f"„{value}“ ist keine ISBN (10 oder 13 Ziffern, ISBN-13 beginnt mit 978 oder 979).")


def parse_volume_number(value):
    """'5', '5.5', '5,5', 'Band 5', 'Vol. 12', '第5巻' -> a number; '' -> None (special volume).
    Raises FieldError."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
    else:
        text = str(value).strip()
        if not text:
            return None
        match = re.fullmatch(r"(?:band|bd\.?|vol(?:ume)?\.?|nr\.?|no\.?|#|第)?\s*(\d{1,4}(?:[.,]\d{1,2})?)\s*(?:巻)?", text, re.I)
        if not match:
            raise FieldError(f"Die Bandnummer „{value}“ ist keine Zahl (z. B. 5 oder 10.5; leer für einen Sonderband).")
        number = float(match.group(1).replace(",", "."))
    if number != number or not 0 <= number <= NUMBER_LIMIT:
        raise FieldError(f"Die Bandnummer muss zwischen 0 und {NUMBER_LIMIT} liegen.")
    return round(number, 2)


def number_label(number):
    """5.0 -> '5', 10.5 -> '10.5', None -> ''."""
    if number is None:
        return ""
    return str(int(number)) if float(number).is_integer() else f"{number:g}"


def whole_number(value, field, low, high):
    raw = str(value if value is not None else "").strip()
    if not raw:
        return None
    if not re.fullmatch(r"\d{1,6}", raw) or not low <= int(raw) <= high:
        raise FieldError(f"{field} bitte als ganze Zahl von {low} bis {high}.")
    return int(raw)


def clean_text(payload, keys, fields):
    for key in keys:
        if key in payload:
            value = ", ".join(split_list(payload[key])) if key in LIST_FIELDS else re.sub(r"\s+", " ", str(payload[key] or "")).strip()
            if len(value) > TEXT_LIMIT:
                raise FieldError(f"„{key}“ ist zu lang (höchstens {TEXT_LIMIT} Zeichen).")
            fields[key] = value


def clean_links(payload, keys, fields):
    for key in keys:
        if key in payload:
            url = str(payload[key] or "").strip()
            if url and not re.match(r"https?://", url, re.I):
                raise FieldError("Links müssen mit http:// oder https:// beginnen.")
            fields[key] = url[:2000]


def clean_choice(payload, key, choices, fields, label):
    if key in payload:
        value = str(payload[key] or "").strip().lower()
        if value and value not in choices:
            raise FieldError(f"Unbekannter Wert für {label}.")
        fields[key] = value


def clean_price(payload, fields, label):
    if "list_price" in payload:
        fields["list_price"], error = parse_amount(payload["list_price"], label)
        if error:
            raise FieldError(error)
    if "currency" in payload:
        currency = str(payload["currency"] or CURRENCY).strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise FieldError("Die Währung bitte als Code mit drei Buchstaben (EUR, JPY, USD …).")
        fields["currency"] = currency


def clean_common(payload, fields):
    if "description" in payload:
        fields["description"] = str(payload["description"] or "").strip()[:DESCRIPTION_LIMIT]
    if "attributes" in payload:
        attributes = payload["attributes"] if isinstance(payload["attributes"], dict) else {}
        fields["attributes"] = json.dumps({str(k)[:80]: str(v)[:500] for k, v in list(attributes.items())[:60]}, ensure_ascii=False)


def required(fields, key, partial, message):
    if (not partial and not fields.get(key)) or (partial and key in fields and not fields[key]):
        raise FieldError(message)


def clean_series_fields(payload, partial=False):
    """The series fields of a request body, checked and normalized. Raises FieldError."""
    fields = {}
    clean_text(payload, SERIES_TEXT, fields)
    required(fields, "title", partial, "Der Titel der Reihe fehlt.")
    clean_choice(payload, "demographic", DEMOGRAPHICS, fields, "die Zielgruppe")
    clean_choice(payload, "status", STATUSES, fields, "den Status")
    if "original_volumes" in payload:
        fields["original_volumes"] = whole_number(payload["original_volumes"], "Die Bandanzahl im Original", 1, NUMBER_LIMIT)
    if "start_year" in payload:
        fields["start_year"] = whole_number(payload["start_year"], "Das Startjahr", 1900, 2200)
    if "anilist_id" in payload:
        fields["anilist_id"] = whole_number(payload["anilist_id"], "Die AniList-Nummer", 1, 99_999_999)
    clean_links(payload, ("source_url", "image_url"), fields)
    clean_common(payload, fields)
    return fields


def clean_edition_fields(payload, partial=False):
    """The edition fields of a request body (series_id is checked by the caller). Raises FieldError."""
    fields = {}
    clean_text(payload, EDITION_TEXT, fields)
    if "language" in payload or not partial:
        language = str(payload.get("language") or "de").strip().lower()
        if not re.fullmatch(r"[a-z]{2,3}", language):
            raise FieldError("Die Sprache bitte als Kürzel (de, ja, en …).")
        fields["language"] = language
    clean_choice(payload, "status", STATUSES, fields, "den Status")
    if "volume_count" in payload:
        fields["volume_count"] = whole_number(payload["volume_count"], "Die Bandanzahl", 1, NUMBER_LIMIT)
    clean_price(payload, fields, "Listenpreis")
    clean_links(payload, ("source_url",), fields)
    clean_common(payload, fields)
    fields.pop("attributes", None)
    return fields


def clean_volume_fields(payload, partial=False):
    """The volume fields of a request body (edition_id is checked by the caller). Raises FieldError."""
    fields = {}
    clean_text(payload, VOLUME_TEXT, fields)
    if "number" in payload:
        fields["number"] = parse_volume_number(payload["number"])
    if "isbn" in payload:
        fields["isbn"] = normalize_isbn(payload["isbn"])
    if "release_date" in payload:
        fields["release_date"], error = normalize_date(payload["release_date"], "Erscheinungstermin")
        if error:
            raise FieldError(error)
    if "pages" in payload:
        fields["pages"] = whole_number(payload["pages"], "Die Seitenzahl", 1, 9999)
    clean_price(payload, fields, "Listenpreis")
    clean_links(payload, ("source_url", "image_url"), fields)
    clean_common(payload, fields)
    if not partial and fields.get("number") is None and not fields.get("title"):
        raise FieldError("Ein Band braucht eine Nummer, ein Sonderband einen Titel.")
    return fields


def fold_key(*parts):
    return "|".join("".join(search.field_words(part or "")[0]) for part in parts)


def find_series_duplicate(connection, fields, exclude_id=0):
    """An existing series that is evidently the same work: the same AniList entry, or a title that
    matches its title or original title. (id, title, reason) or None."""
    if fields.get("anilist_id"):
        row = connection.execute("SELECT id,title FROM series WHERE anilist_id=? AND id!=?", (fields["anilist_id"], exclude_id)).fetchone()
        if row:
            return row["id"], row["title"], "gleicher AniList-Eintrag"
    keys = {fold_key(fields.get(key)) for key in ("title", "original_title") if fields.get(key)}
    for row in connection.execute("SELECT id,title,original_title FROM series WHERE id!=?", (exclude_id,)):
        if {fold_key(row["title"]), fold_key(row["original_title"]) if row["original_title"] else None} & keys:
            return row["id"], row["title"], "gleicher Titel"
    return None


def find_edition_duplicate(connection, series_id, fields, exclude_id=0):
    """An edition of the same series with the same language, publisher, label and format."""
    key = fold_key(fields.get("language"), fields.get("publisher"), fields.get("label"), fields.get("format"))
    for row in connection.execute("SELECT id,language,publisher,label,format FROM editions WHERE series_id=? AND id!=?", (series_id, exclude_id)):
        if fold_key(row["language"], row["publisher"], row["label"], row["format"]) == key:
            return row["id"], "gleicher Verlag, Sprache und Format"
    return None


def find_volume_duplicate(connection, edition_id, fields, exclude_id=0):
    """A volume that is evidently the same book: the same ISBN anywhere, or the same edition with
    the same number and variant (a special volume: the same title). (id, reason) or None."""
    if fields.get("isbn"):
        row = connection.execute("SELECT id FROM volumes WHERE isbn=? AND id!=?", (fields["isbn"], exclude_id)).fetchone()
        if row:
            return row["id"], "gleiche ISBN"
    variant = fold_key(fields.get("variant"))
    if fields.get("number") is not None:
        for row in connection.execute("SELECT id,variant FROM volumes WHERE edition_id=? AND number=? AND id!=?", (edition_id, fields["number"], exclude_id)):
            if fold_key(row["variant"]) == variant:
                return row["id"], "gleiche Bandnummer und Variante"
    elif fields.get("title"):
        title = fold_key(fields["title"])
        for row in connection.execute("SELECT id,title FROM volumes WHERE edition_id=? AND number IS NULL AND id!=?", (edition_id, exclude_id)):
            if fold_key(row["title"]) == title:
                return row["id"], "gleicher Sonderband"
    return None


def edition_name(edition, series_title):
    """What an edition is called: its own title or the series', plus its label (Perfect Edition)."""
    title = edition["title"] or series_title
    return f"{title} – {edition['label']}" if edition["label"] else title


def image_fields(row):
    return {"has_image": bool(row["image_key"] or row["image_url"]), "image_version": (row["image_key"] or "")[:12]}


def insert_row(connection, table, fields):
    columns = list(fields)
    return connection.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                              [fields[key] for key in columns]).lastrowid


def update_row(connection, table, row_id, fields, stamp):
    connection.execute(f"UPDATE {table} SET {','.join(f'{key}=?' for key in fields)}, updated_at=? WHERE id=?",
                       (*fields.values(), stamp, row_id))


def is_admin(connection, uid):
    row = connection.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
    return bool(row and row["role"] == "admin")


def volume_in_use(connection, volume_id):
    return any(connection.execute(sql, (volume_id,)).fetchone() for sql in (
        "SELECT 1 FROM collection_entries WHERE volume_id=? LIMIT 1",
        "SELECT 1 FROM preorders WHERE volume_id=? LIMIT 1",
        "SELECT 1 FROM watchlist_entries WHERE volume_id=? LIMIT 1",
        "SELECT 1 FROM volume_reads WHERE volume_id=? LIMIT 1",
    ))


def edition_in_use(connection, edition_id):
    """Whether any account uses the edition or one of its volumes."""
    if any(connection.execute(sql, (edition_id,)).fetchone() for sql in (
            "SELECT 1 FROM collected_editions WHERE edition_id=? LIMIT 1",
            "SELECT 1 FROM watchlist_entries WHERE edition_id=? LIMIT 1")):
        return True
    return any(volume_in_use(connection, row[0]) for row in connection.execute("SELECT id FROM volumes WHERE edition_id=?", (edition_id,)))


def series_in_use(connection, series_id):
    if connection.execute("SELECT 1 FROM series_reading WHERE series_id=? LIMIT 1", (series_id,)).fetchone():
        return True
    return any(edition_in_use(connection, row[0]) for row in connection.execute("SELECT id FROM editions WHERE series_id=?", (series_id,)))
