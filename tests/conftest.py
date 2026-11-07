"""Shared test setup.

The app opens its database at import time, so DATABASE_PATH has to point at a throwaway file
before the package is imported -- which is why that happens here, at module level, rather than in
a fixture. Every test then starts from the same small catalogue (see SAMPLE_*) with no user data.
Nothing in the suite touches the network: fetches go through ophir_mangas.fetch.fetch (and
post_json), which the tests that need it replace (fake_fetch).
"""
import atexit
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA_DIR = Path(tempfile.mkdtemp(prefix="ophir-mangas-tests-"))
os.environ["DATABASE_PATH"] = str(DATA_DIR / "ophir-mangas.test.db")
atexit.register(shutil.rmtree, DATA_DIR, ignore_errors=True)
os.environ.pop("SECRET_KEY", None)

import ophir_mangas  # noqa: E402

DEMO = ("demo", "mangas-1234")
ADMIN = ("admin", "admin")
STAMP = "2026-01-01T00:00:00+00:00"

# Ids of the sample catalogue the tests refer to by name.
AOT, FRIEREN, SPY = 1, 2, 3                                  # series
AOT_DE, AOT_JA, FRIEREN_DE, SPY_DE, FRIEREN_EN = 1, 2, 3, 4, 5   # editions
SAMPLE_SERIES = (
    (AOT, "Attack on Titan", "進撃の巨人", "Shingeki no Kyojin", "Hajime Isayama", "Action, Drama, Fantasy", "shounen", "completed", 34, 2009, 53390),
    (FRIEREN, "Frieren – Nach dem Ende der Reise", "葬送のフリーレン", "Sousou no Frieren, Frieren: Beyond Journey's End",
     "Kanehito Yamada, Tsukasa Abe", "Abenteuer, Drama, Fantasy", "shounen", "ongoing", None, 2020, 118586),
    (SPY, "Spy x Family", "SPY×FAMILY", "", "Tatsuya Endo", "Action, Comedy", "shounen", "ongoing", None, 2019, None),
)
SAMPLE_EDITIONS = (
    # id, series, title, label, publisher, language, format, status, volume_count, list_price, currency
    (AOT_DE, AOT, "", "", "Carlsen", "de", "Taschenbuch", "completed", 34, 7.5, "EUR"),
    (AOT_JA, AOT, "進撃の巨人", "", "Kodansha", "ja", "Tankōbon", "completed", 34, 429, "JPY"),
    (FRIEREN_DE, FRIEREN, "Frieren", "", "Egmont Manga", "de", "Taschenbuch", "ongoing", None, 7.0, "EUR"),
    (SPY_DE, SPY, "", "", "Kazé", "de", "Taschenbuch", "ongoing", None, 7.0, "EUR"),
    (FRIEREN_EN, FRIEREN, "Frieren: Beyond Journey's End", "", "Viz Media", "en", "Tankōbon", "ongoing", None, 9.99, "USD"),
)
SAMPLE_VOLUMES = (
    # id, edition, number, title, variant, isbn, release_date, list_price, currency
    (1, AOT_DE, 1, "", "", "9783551799012", "2014-04-01", 7.5, "EUR"),
    (2, AOT_DE, 2, "", "", "9783551799029", "2014-06-03", 7.5, "EUR"),
    (3, AOT_DE, 3, "", "", "9783551799036", "2014-08-05", 7.5, "EUR"),
    (4, AOT_DE, 4, "", "", "9783551799043", "2014-10-07", 7.5, "EUR"),
    (5, AOT_DE, 5, "", "", "9783551799050", "2014-12-02", 7.5, "EUR"),
    (6, AOT_DE, 5, "", "Limited Edition", "9783551799555", "2014-12-02", 14.0, "EUR"),
    (7, AOT_JA, 1, "", "", "9784063842760", "2010-03-17", 429, "JPY"),
    (8, FRIEREN_DE, 1, "", "", "9783770430017", "2022-01-04", 7.0, "EUR"),
    (9, FRIEREN_DE, 2, "", "", "9783770430024", "2022-03-01", 7.0, "EUR"),
    (10, FRIEREN_DE, 3, "", "", "9783770430031", "2022-05-03", 7.0, "EUR"),
    (11, FRIEREN_DE, 4, "", "", "9783770430048", "2099-02", 7.0, "EUR"),
    (12, SPY_DE, 1, "", "", "9782842910013", "2021-02-01", 7.0, "EUR"),
    (13, SPY_DE, 2, "", "", "9782842910020", "2021-04-01", 7.0, "EUR"),
    (14, SPY_DE, None, "Official Guide", "", "9782842910990", "2023-06-01", 12.0, "EUR"),
    (15, FRIEREN_EN, 1, "", "", "9781974710010", "2021-11-09", 9.99, "USD"),
)


def add_users():
    """The suite's accounts: demo (id 1), an ordinary user, and admin (id 2), in place of the
    admin the app seeds."""
    from werkzeug.security import generate_password_hash
    connection = sqlite3.connect(ophir_mangas.config.DB_PATH)
    connection.execute("PRAGMA foreign_keys=OFF")
    connection.execute("DELETE FROM users")
    connection.executemany("INSERT INTO users(id, username, display_name, password_hash, role, created_at) VALUES(?,?,?,?,?,?)", [
        (1, "demo", "Alex Morgan", generate_password_hash(DEMO[1]), "user", STAMP),
        (2, "admin", "Ophir Mangas Admin", generate_password_hash("admin"), "admin", STAMP),
    ])
    connection.commit()
    connection.close()
    ophir_mangas.schema.init_database()


def add_catalogue():
    connection = sqlite3.connect(ophir_mangas.config.DB_PATH)
    connection.executemany(
        """INSERT INTO series(id,title,original_title,alt_titles,authors,genres,demographic,status,original_volumes,start_year,anilist_id,
                              created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,2,?,?)""",
        [(*row, STAMP, STAMP) for row in SAMPLE_SERIES])
    connection.executemany(
        """INSERT INTO editions(id,series_id,title,label,publisher,language,format,status,volume_count,list_price,currency,
                                created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,2,?,?)""",
        [(*row, STAMP, STAMP) for row in SAMPLE_EDITIONS])
    connection.executemany(
        """INSERT INTO volumes(id,edition_id,number,title,variant,isbn,release_date,list_price,currency,created_by,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,2,?,?)""",
        [(*row, STAMP, STAMP) for row in SAMPLE_VOLUMES])
    connection.commit()
    connection.close()


def query(statement, args=()):
    connection = sqlite3.connect(ophir_mangas.config.DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in connection.execute(statement, args)]
        connection.commit()
        return rows
    finally:
        connection.close()


@pytest.fixture(autouse=True)
def fresh_database():
    connection = sqlite3.connect(ophir_mangas.config.DB_PATH)
    connection.execute("PRAGMA foreign_keys=OFF")
    tables = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name!='schema_migrations'"
    for (table,) in connection.execute(tables).fetchall():
        connection.execute(f"DELETE FROM {table}")
    connection.execute("DELETE FROM sqlite_sequence")
    connection.commit()
    connection.close()
    add_users()
    add_catalogue()
    yield


def login(credentials=DEMO):
    client = ophir_mangas.app.test_client()
    if credentials:
        assert client.post("/login", data={"username": credentials[0], "password": credentials[1]}).status_code == 302
    return client


@pytest.fixture
def client():
    return login()


@pytest.fixture
def admin():
    return login(ADMIN)


@pytest.fixture
def anonymous():
    return login(None)


def default_list(client):
    return next(item["id"] for item in client.get("/api/watchlists").get_json() if item["is_default"])


def own(client, volume_id, **fields):
    """Adds a copy of the volume to the client's collection; returns the row."""
    response = client.post("/api/collection", json={"volume_id": volume_id, **fields})
    assert response.status_code == 201, response.get_json()
    return response.get_json()


@pytest.fixture
def fake_fetch(monkeypatch):
    """Replaces every outgoing request: register answers with pages[url] = (content type, bytes)
    or an exception to raise; JSON POSTs (posts[url] = answer dict, or a callable getting the
    payload) are recorded in `posted`."""
    from ophir_mangas import fetch as fetch_module
    pages, posts = {}, {}
    requested, posted = [], []

    def fetch(url, max_bytes, accept="*/*", session=None):
        requested.append(url)
        answer = pages.get(url)
        if answer is None:
            raise fetch_module.FetchError("Die Seite antwortet mit Fehler 404.")
        if isinstance(answer, Exception):
            raise answer
        content_type, body = answer
        if len(body) > max_bytes:
            raise fetch_module.FetchError("Die Antwort ist zu groß.")
        return url, content_type, body

    def post_json(url, payload, max_bytes=2 * 1024 * 1024):
        posted.append((url, payload))
        answer = posts.get(url)
        if answer is None:
            raise fetch_module.FetchError("Die Seite antwortet mit Fehler 404.")
        if isinstance(answer, Exception):
            raise answer
        return answer(payload) if callable(answer) else answer

    for module in (fetch_module, ophir_mangas.images, ophir_mangas.link_import, ophir_mangas.lookup):
        monkeypatch.setattr(module, "fetch", fetch, raising=False)
        monkeypatch.setattr(module, "post_json", post_json, raising=False)
    return type("FakeWeb", (), {"pages": pages, "posts": posts, "requested": requested, "posted": posted})()


def png_bytes(color=(200, 30, 60), size=(40, 60)):
    return picture_bytes("PNG", color, size)


def avif_bytes(color=(30, 120, 200), size=(40, 60)):
    """Made with Pillow here, so no binary fixture has to live in the repository."""
    return picture_bytes("AVIF", color, size)


def picture_bytes(image_format, color=(200, 30, 60), size=(40, 60)):
    import io

    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, image_format)
    return buffer.getvalue()
