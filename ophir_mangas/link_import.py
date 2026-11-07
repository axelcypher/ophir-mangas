"""Filling in a volume from a product page: a shop, a publisher's page, a database entry.

Two ways in, one way out. Both turn the page into a *snapshot* -- its meta tags (OpenGraph and
the like), its JSON-LD blocks and the label/value pairs it shows (definition lists, two-column
table rows, data fields) -- and extract() maps a snapshot onto a proposal, the same shape the
ISBN lookup answers with (lookup.py):

- POST /api/link-import {url}: the server fetches the page (fetch.py) and reads it.
- POST /api/link-import {snapshot}: the browser read the page itself, through the bookmarklet
  (static/js/import.js). Many shops answer server requests with a bot check; the bookmarklet runs
  in the page the user has open in their own browser, so nothing is circumvented.

Nothing is saved here: the result fills the form, which the user checks and saves.
"""

import json
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin

from flask import jsonify, request

from .catalog import DESCRIPTION_LIMIT, FieldError, fold_key, normalize_date, normalize_isbn
from .fetch import FetchError, fetch
from .lookup import build_proposal, language_code, match_catalogue, split_title_number, volume_label
from .web import app, db, login_required

MAX_PAGE_BYTES = 4 * 1024 * 1024
MAX_SNAPSHOT_FIELDS = 200
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

# Label words (lower case, as German, English and Japanese shops write them) -> field. A label
# matches when it equals one of these or starts with one of more than three letters.
LABELS = {
    "isbn": ("isbn", "isbn-13", "isbn13", "isbn-10", "isbn10", "ean", "ean-13", "isbn/ean", "ean/isbn", "gtin"),
    "publisher": ("verlag", "publisher", "herausgeber", "出版社"),
    "release_date": ("erscheinungsdatum", "erscheinungstermin", "erscheint am", "erschienen am", "release date", "release",
                     "publication date", "veröffentlichung", "発売日", "発売予定日"),
    "pages": ("seiten", "seitenzahl", "anzahl seiten", "umfang", "pages", "page count", "print length", "ページ数"),
    "number": ("band", "bandnummer", "band-nr", "volume", "vol", "巻", "巻数"),
    "series": ("reihe", "serie", "series", "シリーズ"),
    "authors": ("autor", "autorin", "autoren", "zeichner", "zeichnerin", "mangaka", "künstler", "author", "authors", "illustrator",
                "著者", "作者", "von"),
    "language": ("sprache", "language", "言語"),
    "format": ("format", "einband", "einbandart", "binding", "produktform"),
    "price": ("preis", "price", "listenpreis", "価格", "定価"),
    "original_title": ("originaltitel", "original title", "原題"),
}
# Labels that are a binding themselves, with the page count as their value (Amazon: "Taschenbuch: 192 Seiten").
BINDINGS = ("taschenbuch", "paperback", "softcover", "broschiert", "kartoniert", "hardcover", "gebundene ausgabe", "gebunden")
FORMAT_WORDS = (("taschenbuch", "Taschenbuch"), ("paperback", "Taschenbuch"), ("softcover", "Taschenbuch"), ("broschiert", "Taschenbuch"),
                ("kartoniert", "Taschenbuch"), ("hardcover", "Hardcover"), ("gebunden", "Hardcover"), ("e-book", "Digital"),
                ("ebook", "Digital"))
# Role notes of people who neither wrote nor drew the book.
NOT_AUTHORS = re.compile(r"übersetz|translat|herausgeb|editor|lektor|redaktion|umschlag|cover|翻訳|訳", re.I)


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.children, self.parent = tag, attrs, [], parent

    def elements(self):
        return [child for child in self.children if isinstance(child, Node)]

    def walk(self):
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.walk()

    def text(self):
        parts = []
        for child in self.children:
            if isinstance(child, Node):
                if child.tag in ("script", "style", "noscript", "template"):
                    continue
                if child.tag == "br":
                    parts.append(" ")
                parts.append(child.text())
            else:
                parts.append(child)
        return re.sub(r"\s+", " ", " ".join(parts)).strip()

    def classes(self):
        return set((self.attrs.get("class") or "").split())


class TreeBuilder(HTMLParser):
    """A forgiving tree of the page: unclosed tags are closed by their parent's end tag."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self.current = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {key: value or "" for key, value in attrs}, self.current)
        self.current.children.append(node)
        if tag not in VOID_TAGS:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.current.children.append(Node(tag, {key: value or "" for key, value in attrs}, self.current))

    def handle_endtag(self, tag):
        node = self.current
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.current = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def add_field(fields, label, value):
    label = re.sub(r"\s+", " ", str(label or "")).strip().rstrip(":：").strip()
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    if label and value and len(label) <= 60 and label not in fields and len(fields) < MAX_SNAPSHOT_FIELDS:
        fields[label] = value[:500]


def snapshot_from_html(html, url):
    """The snapshot of a page from its HTML (what the bookmarklet gathers in the browser)."""
    builder = TreeBuilder()
    builder.feed(html)
    builder.close()
    root = builder.root
    meta, jsonld, fields = {}, [], {}
    title = heading = canonical = ""
    for node in root.walk():
        if node.tag == "meta":
            key = node.attrs.get("property") or node.attrs.get("name") or node.attrs.get("itemprop")
            if key and node.attrs.get("content") and key not in meta:
                meta[key] = unescape(node.attrs["content"]).strip()
        elif node.tag == "link" and "canonical" in (node.attrs.get("rel") or "").lower().split() and not canonical:
            canonical = urljoin(url, node.attrs.get("href") or "")
        elif node.tag == "title" and not title:
            title = node.text()
        elif node.tag == "h1" and not heading:
            heading = node.text()
        elif node.tag == "script" and "ld+json" in (node.attrs.get("type") or "").lower():
            raw = "".join(child for child in node.children if isinstance(child, str)).strip()
            try:
                jsonld.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
    for node in root.walk():
        if "data-field" in node.classes():
            label = next((child for child in node.walk() if "data-label" in child.classes()), None)
            value = next((child for child in node.walk() if "data-value" in child.classes()), None)
            if label and value:
                add_field(fields, label.text(), value.text())
    for node in root.walk():
        if node.tag == "dt":
            siblings = node.parent.elements()
            index = siblings.index(node)
            if index + 1 < len(siblings) and siblings[index + 1].tag == "dd":
                add_field(fields, node.text(), siblings[index + 1].text())
        elif node.tag == "tr":
            cells = [child for child in node.elements() if child.tag in ("th", "td")]
            if len(cells) == 2:
                add_field(fields, cells[0].text(), cells[1].text())
    return {"url": url, "canonical": canonical, "title": title, "heading": heading, "meta": meta, "jsonld": jsonld, "fields": fields}


def walk_jsonld(value):
    if isinstance(value, list):
        for item in value:
            yield from walk_jsonld(item)
    elif isinstance(value, dict):
        yield value
        for key in ("@graph", "hasVariant", "mainEntity", "itemListElement", "item"):
            if key in value:
                yield from walk_jsonld(value[key])


def types_of(item):
    kind = item.get("@type")
    return {str(value).lower() for value in (kind if isinstance(kind, list) else [kind]) if value}


def first_book(jsonld):
    """The page's Book, else its Product (shops describe books as either)."""
    items = list(walk_jsonld(jsonld))
    return (next((item for item in items if "book" in types_of(item)), None)
            or next((item for item in items if types_of(item) & {"product", "individualproduct", "productmodel", "productgroup"}), {}))


def ld_text(value):
    if isinstance(value, dict):
        return ld_text(value.get("name") or value.get("@value") or value.get("url"))
    if isinstance(value, list):
        return ld_text(value[0]) if value else ""
    return unescape(str(value or "")).strip()


def ld_image(value):
    if isinstance(value, list):
        return next((image for image in (ld_image(item) for item in value) if image), "")
    if isinstance(value, dict):
        return ld_image(value.get("url") or value.get("contentUrl"))
    return str(value or "").strip()


def offer_of(product):
    offers = product.get("offers")
    for offer in walk_jsonld(offers) if offers else []:
        price = offer.get("price") or offer.get("lowPrice")
        if price is None and isinstance(offer.get("priceSpecification"), dict):
            price = offer["priceSpecification"].get("price")
        amount = parse_number(price)
        if amount is not None:
            currency = str(offer.get("priceCurrency") or (offer.get("priceSpecification") or {}).get("priceCurrency") or "").upper()
            return {"price": amount, "currency": currency}
    return None


def parse_number(value):
    if value in (None, ""):
        return None
    text = str(value).strip()
    match = re.search(r"\d[\d.,\s]*", text)
    if not match:
        return None
    number = match.group(0).strip().replace(" ", "")
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", number):           # 14,800 / 14.800
        number = re.sub(r"[.,]", "", number)
    elif "," in number and "." in number:                       # 1.299,00 / 1,299.00
        number = number.replace(".", "").replace(",", ".") if number.rfind(",") > number.rfind(".") else number.replace(",", "")
    else:
        number = number.replace(",", ".")
    try:
        return round(float(number), 2)
    except ValueError:
        return None


CURRENCY_HINTS = (("¥", "JPY"), ("円", "JPY"), ("yen", "JPY"), ("jpy", "JPY"), ("€", "EUR"), ("eur", "EUR"), ("$", "USD"), ("usd", "USD"),
                  ("£", "GBP"), ("gbp", "GBP"), ("cny", "CNY"), ("rmb", "CNY"), ("hk$", "HKD"),
                  ("chf", "CHF"), ("sfr", "CHF"))


def price_from_text(text):
    amount = parse_number(text)
    if amount is None:
        return None
    lowered = text.lower()
    currency = next((code for hint, code in sorted(CURRENCY_HINTS, key=lambda pair: -len(pair[0])) if hint in lowered), "")
    return {"price": amount, "currency": currency}


def labelled(fields, key):
    """The value of the first field whose label is one of LABELS[key] (or starts with one)."""
    words = LABELS[key]
    for label, value in fields.items():
        lowered = label.lower()
        if lowered in words:
            return value
    for label, value in fields.items():
        lowered = label.lower()
        if any(lowered.startswith(word) for word in words if len(word) > 3):
            return value
    return ""


def people(value):
    """'Hajime Isayama (Autor), Claudia Peter (Übersetzer)' -> ['Hajime Isayama']: the names, without
    the translator and the others whose role note says they neither wrote nor drew it."""
    names = []
    for part in re.split(r"(?:\s*[,;、/]\s*|\s+(?:und|and|&)\s+)(?![^()（）]*[)）])", value or ""):
        role = re.search(r"[(（]([^)）]*)[)）]", part)
        if role and NOT_AUTHORS.search(role.group(1)):
            continue
        name = re.sub(r"\s*[(（][^)）]*[)）]\s*", " ", part).strip()
        if name and name not in names:
            names.append(name)
    return names


def ld_names(value):
    """The names of a JSON-LD author or illustrator: a Person, a list of them, or text."""
    if isinstance(value, list):
        return [name for item in value for name in ld_names(item)]
    if isinstance(value, dict):
        name = ld_text(value.get("name"))
        return [name] if name else []
    text = unescape(str(value or "")).strip()
    return people(text) if text and not text.startswith("http") else []


def first_date(text):
    for pattern in (r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", r"\d{1,2}[./]\d{1,2}[./]\d{4}", r"\d{4}年\d{1,2}月(?:\d{1,2}日)?",
                    r"\d{4}[-/.]\d{1,2}", r"\d{1,2}[/.]\d{4}", r"[A-Za-zäÄ]+\.?\s+\d{4}", r"\b\d{4}\b"):
        for match in re.finditer(pattern, text or ""):
            value, error = normalize_date(match.group(0))
            if value and not error:
                return value
    return ""


def clean_title(title, site_name):
    title = re.sub(r"\s+", " ", title or "").strip()
    if site_name and site_name.lower() in title.lower():
        parts = [part.strip() for part in re.split(r"\s+[|–—-]\s+|\s*\|\s*", title) if part.strip()]
        parts = [part for part in parts if site_name.lower() not in part.lower()]
        title = " - ".join(parts) or title
    return re.sub(r"^(?:Buy|Pre-?order|Vorbestellung|Kaufen)\s*:?\s+", "", title, flags=re.I).strip()


def isbn_in(*values):
    """The first valid ISBN in the values ('978-3-551-79905-0', 'ISBN 3551799059', '9783551799050 /
    3551799059'), as 13 digits; '' for none."""
    for value in values:
        text = str(value or "")
        for candidate in re.findall(r"[\dX][\d\-‐‑]{8,16}[\dX]", text, re.I) + re.findall(r"[\dX][\d\s\-‐‑]{8,16}[\dX]", text, re.I):
            try:
                isbn = normalize_isbn(candidate)
            except FieldError:
                continue
            if isbn:
                return isbn
    return ""


def book_format(text):
    """'Taschenbuch', 'Broschiert', 'https://schema.org/Paperback' -> the forms' word ('Taschenbuch');
    another printed format as it is, schema.org's others (GraphicNovel) not at all."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    lowered = text.lower()
    for needle, name in FORMAT_WORDS:
        if needle in lowered:
            return name
    return "" if "schema.org" in lowered or lowered in ("graphicnovel", "audiobookformat") else text[:300]


def publisher_name(text):
    """'Carlsen; 1. Edition (2. Dezember 2014)' -> 'Carlsen'."""
    return re.sub(r"\s*[(（][^)）]*[)）]", "", re.split(r"\s*;\s*", text or "")[0]).strip()


def page_binding(page_fields):
    """(format, pages) from a label that is a binding itself, as Amazon writes "Taschenbuch: 192 Seiten"."""
    for label, value in page_fields.items():
        if label.lower() in BINDINGS:
            return label, value if re.search(r"seiten|pages", value, re.I) else ""
    return "", ""


def page_price(page_fields, book, example, meta):
    """{"price", "currency"} from a labelled price, the JSON-LD offer or the product meta tags; None."""
    price_text = labelled(page_fields, "price")
    offer = (price_from_text(price_text) if price_text else None) or offer_of(book) or offer_of(example)
    if not offer and meta.get("product:price:amount"):
        amount = parse_number(meta["product:price:amount"])
        offer = {"price": amount, "currency": (meta.get("product:price:currency") or "").upper()} if amount is not None else None
    return offer if offer and offer["price"] else None


def extract(snapshot):
    """A proposal (lookup.build_proposal, without the match) from a snapshot: the volume, its edition
    and its series as far as the page tells them, its picture, and notes on what is missing."""
    meta = snapshot.get("meta") if isinstance(snapshot.get("meta"), dict) else {}
    page_fields = snapshot.get("fields") if isinstance(snapshot.get("fields"), dict) else {}
    page_fields = {str(key): str(value) for key, value in list(page_fields.items())[:MAX_SNAPSHOT_FIELDS]}
    book = first_book(snapshot.get("jsonld") or [])
    # A Book's printed form (with ISBN, binding, pages) is often its workExample.
    example = next(walk_jsonld(book.get("workExample")), {}) if book.get("workExample") else {}

    def ld(key):
        return book.get(key) or example.get(key)

    url = str(snapshot.get("url") or "")
    canonical = str(snapshot.get("canonical") or meta.get("og:url") or url)
    name = ld_text(book.get("name")) or meta.get("og:title") or snapshot.get("heading") or snapshot.get("title") or ""
    name = clean_title(name, meta.get("og:site_name", ""))[:300]
    image = ld_image(book.get("image")) or meta.get("og:image") or meta.get("og:image:secure_url") or meta.get("twitter:image") or ""
    image = urljoin(url, image) if image else ""
    description = ld_text(book.get("description")) or meta.get("og:description") or meta.get("description") or ""

    # The series and number from what the page labels them, else from the product name ("Attack on Titan 5").
    series_text = labelled(page_fields, "series") or ld_text(ld("isPartOf"))
    series_title, series_number = split_title_number(series_text) if series_text else ("", "")
    name_title, name_number = split_title_number(name)
    number = volume_label(labelled(page_fields, "number") or ld_text(ld("position") or ld("volumeNumber"))) or series_number or name_number
    own_title = name if series_text and fold_key(series_title) not in fold_key(name) else ""
    series_title = series_title or name_title

    authors = people(labelled(page_fields, "authors")) or ld_names(book.get("author")) + ld_names(book.get("illustrator"))
    authors = authors or ld_names(meta.get("book:author"))
    isbn = isbn_in(labelled(page_fields, "isbn"), ld_text(ld("isbn")), ld_text(ld("gtin13")), ld_text(ld("gtin")),
                   meta.get("books:isbn"), meta.get("book:isbn"), ld_text(ld("sku")))
    binding, binding_pages = page_binding(page_fields)
    pages = re.search(r"\d{1,4}", labelled(page_fields, "pages") or binding_pages)
    release = labelled(page_fields, "release_date")
    release = first_date(release) if release else first_date(ld_text(ld("datePublished") or ld("releaseDate")) or meta.get("book:release_date"))
    offer = page_price(page_fields, book, example, meta)
    price, currency = (offer["price"], offer["currency"]) if offer else (None, "")

    warnings = []
    if not (series_title or own_title):
        warnings.append("Auf der Seite war kein Titel zu finden.")
    if not isbn:
        warnings.append("Keine ISBN gefunden – bitte von der Rückseite abtippen oder scannen.")
    if not image:
        warnings.append("Kein Bild gefunden – du kannst eins hochladen.")
    volume = {"number": number, "title": own_title, "isbn": isbn, "release_date": release, "list_price": price, "currency": currency,
              "pages": int(pages.group(0)) if pages else (ld("numberOfPages") if isinstance(ld("numberOfPages"), int) else None),
              "description": re.sub(r"\s+", " ", description).strip()[:DESCRIPTION_LIMIT], "image_url": image,
              "source_url": canonical if canonical.startswith("http") else url}
    edition = {"publisher": publisher_name(labelled(page_fields, "publisher")) or ld_text(ld("publisher")),
               "language": language_code(labelled(page_fields, "language")) or language_code(ld_text(ld("inLanguage"))),
               "format": book_format(labelled(page_fields, "format") or binding) or book_format(ld_text(ld("bookFormat"))),
               "list_price": price, "currency": currency}
    series = {"title": series_title, "original_title": labelled(page_fields, "original_title")[:300], "authors": ", ".join(authors)}
    return build_proposal(volume, edition, series, [image], ["page"], warnings)


def sanitize_snapshot(raw):
    """A snapshot from the browser, cut down to the shape and size extract() expects."""
    if not isinstance(raw, dict):
        return None
    jsonld = raw.get("jsonld") if isinstance(raw.get("jsonld"), list) else []
    return {
        "url": str(raw.get("url") or "")[:2000], "canonical": str(raw.get("canonical") or "")[:2000],
        "title": str(raw.get("title") or "")[:500], "heading": str(raw.get("heading") or "")[:500],
        "meta": {str(k)[:100]: str(v)[:2000] for k, v in list((raw.get("meta") or {}).items())[:300]} if isinstance(raw.get("meta"), dict) else {},
        "jsonld": jsonld[:30],
        "fields": {str(k)[:60]: str(v)[:500] for k, v in list((raw.get("fields") or {}).items())[:MAX_SNAPSHOT_FIELDS]} if isinstance(raw.get("fields"), dict) else {},
    }


@app.post("/api/link-import")
@login_required
def link_import():
    payload = request.get_json(force=True) or {}
    if payload.get("snapshot") is not None:
        snapshot = sanitize_snapshot(payload["snapshot"])
        if not snapshot:
            return jsonify({"error": "Die übermittelten Seitendaten sind unvollständig."}), 400
    else:
        url = str(payload.get("url") or "").strip()
        if not url:
            return jsonify({"error": "Bitte einen Link einfügen."}), 400
        try:
            final_url, content_type, body = fetch(url, MAX_PAGE_BYTES, accept="text/html,application/xhtml+xml;q=0.9,*/*;q=0.5")
        except FetchError as error:
            return jsonify({"error": str(error), "blocked": error.blocked}), 422
        if content_type and "html" not in content_type and "xml" not in content_type:
            return jsonify({"error": "Der Link führt nicht zu einer Webseite."}), 422
        charset = re.search(rb'charset=["\']?([\w-]+)', body[:4096])
        try:
            html = body.decode(charset.group(1).decode() if charset else "utf-8", errors="replace")
        except LookupError:
            html = body.decode("utf-8", errors="replace")
        snapshot = snapshot_from_html(html, final_url)
    proposal = extract(snapshot)
    proposal["match"] = match_catalogue(db(), proposal)
    return jsonify(proposal)
