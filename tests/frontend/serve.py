"""Serves the app for the browser tests (tests/frontend/*.test.mjs): the working tree, a throwaway
database and the same small catalogue the Python tests use. Nothing reaches the internet: shop
pages, the ISBN sources, AniList and pictures come from fakes.

    python tests/frontend/serve.py <port> [<path prefix, e.g. /mangas>]

With a prefix it stands in for the homelab's Traefik: only requests under the prefix reach the app,
with the prefix stripped and named in X-Forwarded-Prefix.

What the fakes know:
- ISBN 9783770430055: Frieren 5 from Egmont Manga (Google Books only) -- a new volume of an edition
  the catalogue has.
- ISBN 9783551800015: Blue Lock 1 from Carlsen (Google Books only) -- a series the catalogue lacks.
- https://shop.test/<anything>: a shop page for Blue Lock 2 (JSON-LD Book).
- AniList: one series, Blue Lock, for every search.
- Any picture link: a small PNG.
"""
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import conftest  # noqa: E402  -- points DATABASE_PATH at a temp file before the app is imported

conftest.add_users()
conftest.add_catalogue()

ophir_mangas = conftest.ophir_mangas
FetchError = ophir_mangas.fetch.FetchError

SHOP_PAGE = b"""<html><head><meta property="og:title" content="Blue Lock 2 | Test Shop"><meta property="og:site_name" content="Test Shop">
<script type="application/ld+json">{"@type":"Book","name":"Blue Lock 2","isbn":"9783551800022","author":[{"name":"Muneyuki Kaneshiro"},{"name":"Yusuke Nomura"}],
"publisher":{"name":"Carlsen"},"inLanguage":"de","numberOfPages":192,"datePublished":"2023-03-28","image":"https://cdn.test/bluelock-2.png",
"offers":{"price":"7.50","priceCurrency":"EUR"}}</script></head><body><h1>Blue Lock 2</h1></body></html>"""

GOOGLE = {
    "9783770430055": {"title": "Frieren 5", "authors": ["Kanehito Yamada", "Tsukasa Abe"], "publisher": "Egmont Manga", "publishedDate": "2022-09-06",
                      "pageCount": 192, "language": "de", "imageLinks": {"thumbnail": "https://cdn.test/frieren-5.png"}},
    "9783551800015": {"title": "Blue Lock 1", "authors": ["Muneyuki Kaneshiro", "Yusuke Nomura"], "publisher": "Carlsen", "publishedDate": "2023-01-31",
                      "pageCount": 192, "language": "de", "imageLinks": {"thumbnail": "https://cdn.test/bluelock-1.png"}},
}

ANILIST_MEDIA = {
    "id": 106130, "title": {"romaji": "Blue Lock", "english": "Blue Lock", "native": "ブルーロック"}, "synonyms": ["Buruu Rokku"],
    "staff": {"edges": [{"role": "Story", "node": {"name": {"full": "Muneyuki Kaneshiro"}}}, {"role": "Art", "node": {"name": {"full": "Yusuke Nomura"}}}]},
    "genres": ["Sports", "Drama"], "tags": [{"name": "Shounen", "category": "Demographic"}], "status": "RELEASING", "volumes": None,
    "startDate": {"year": 2018}, "coverImage": {"extraLarge": "https://cdn.test/bluelock.png", "large": None},
    "description": "Japans Fußball soll Weltklasse werden.", "countryOfOrigin": "JP", "siteUrl": "https://anilist.co/manga/106130", "format": "MANGA",
}


def picture():
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (60, 90), (120, 90, 160)).save(buffer, "PNG")
    return buffer.getvalue()


PICTURE = picture()


def fake_fetch(url, max_bytes, accept="*/*", session=None):
    if url.startswith("https://shop.test/"):
        return url, "text/html", SHOP_PAGE
    if url.startswith("https://cdn.test/"):
        return url, "image/png", PICTURE
    if url.startswith("https://www.googleapis.com/books/v1/volumes?q=isbn:"):
        info = GOOGLE.get(url.rsplit(":", 1)[1])
        body = {"totalItems": 1, "items": [{"volumeInfo": {**info, "industryIdentifiers": [{"type": "ISBN_13", "identifier": url.rsplit(":", 1)[1]}]}}]} \
            if info else {"totalItems": 0}
        return url, "application/json", json.dumps(body).encode()
    raise FetchError("Die Seite antwortet mit Fehler 404.")


def fake_post_json(url, payload, max_bytes=2 * 1024 * 1024, session=None):
    if url == ophir_mangas.lookup.ANILIST_URL:
        if "id" in (payload.get("variables") or {}):
            return {"data": {"Media": ANILIST_MEDIA}}
        return {"data": {"Page": {"media": [ANILIST_MEDIA]}}}
    raise FetchError("Die Seite antwortet mit Fehler 404.")


def strip_prefix(wsgi_app, prefix):
    """What Traefik's StripPrefix middleware does in front of the app: a 404 outside the prefix,
    otherwise the path without it and the prefix in X-Forwarded-Prefix."""
    from werkzeug.exceptions import NotFound

    def strip(environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path != prefix and not path.startswith(prefix + "/"):
            return NotFound()(environ, start_response)
        environ["PATH_INFO"] = path[len(prefix):] or "/"
        environ["HTTP_X_FORWARDED_PREFIX"] = prefix
        return wsgi_app(environ, start_response)
    return strip


for module in (ophir_mangas.fetch, ophir_mangas.images, ophir_mangas.link_import, ophir_mangas.lookup):
    module.fetch = fake_fetch
    if hasattr(module, "post_json"):
        module.post_json = fake_post_json
app = ophir_mangas.app
if len(sys.argv) > 2:
    app.wsgi_app = strip_prefix(ophir_mangas.web.behind_proxy(app.wsgi_app), sys.argv[2].rstrip("/"))
app.run(host="127.0.0.1", port=int(sys.argv[1]), debug=False, threaded=True)
