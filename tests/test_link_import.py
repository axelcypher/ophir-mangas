"""Filling in a volume from a product page: the server reading a page, the bookmarklet's snapshot,
and what is read from JSON-LD, meta tags and label/value tables -- answered in the lookup's
proposal shape, with the catalogue match."""
import pytest

from conftest import AOT, AOT_DE, AOT_JA, FRIEREN, FRIEREN_DE, SPY, SPY_DE
from ophir_mangas.fetch import FetchError

SHOP_PAGE = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<title>Attack on Titan 6 | Mangashop</title>
<meta property="og:site_name" content="Mangashop">
<meta property="og:title" content="Attack on Titan 6 | Mangashop">
<meta property="og:image" content="//cdn.mangashop.example/covers/aot6-small.jpg">
<link rel="canonical" href="https://mangashop.example/attack-on-titan-6">
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"BreadcrumbList"},
 {"@type":"Book","name":"Attack on Titan 6","isbn":"978-3-551-79906-7",
  "author":[{"@type":"Person","name":"Hajime Isayama"}],"translator":{"@type":"Person","name":"Claudia Peter"},
  "publisher":{"@type":"Organization","name":"Carlsen"},"datePublished":"2015-02-03","numberOfPages":192,"inLanguage":"de",
  "bookFormat":"https://schema.org/Paperback","image":["https://cdn.mangashop.example/covers/aot6.jpg"],
  "description":"Die Jagd auf den weiblichen Titan beginnt.",
  "offers":{"@type":"Offer","price":"7.50","priceCurrency":"EUR"}}]}</script>
</head><body><h1>Attack on Titan 6</h1></body></html>"""

BOOKSHOP_PAGE = """<html><head><meta charset="utf-8"><title>Frieren 5 – Buchhandlung</title>
<meta property="og:image" content="https://buch.example/img/frieren5.jpg"></head><body>
<h1>Frieren – Nach dem Ende der Reise 5</h1>
<table>
<tr><th>Reihe</th><td>Frieren – Nach dem Ende der Reise</td></tr>
<tr><th>Band</th><td>5</td></tr>
<tr><th>Autor</th><td>Kanehito Yamada (Autor), Tsukasa Abe (Zeichner), Hiro Yamada (Übersetzer)</td></tr>
<tr><th>Verlag</th><td>Egmont Manga</td></tr>
<tr><th>ISBN-13</th><td>978-3-7704-3005-5</td></tr>
<tr><th>Erscheinungstermin</th><td>05.07.2022</td></tr>
<tr><th>Seitenzahl</th><td>192 Seiten</td></tr>
<tr><th>Sprache</th><td>Deutsch</td></tr>
<tr><th>Einband</th><td>Taschenbuch</td></tr>
<tr><th>Preis</th><td>7,00 €</td></tr>
</table>
<dl><dt>Originaltitel</dt><dd>葬送のフリーレン</dd></dl></body></html>"""


def test_a_shop_page_is_read_from_its_json_ld(client, fake_fetch):
    fake_fetch.pages["https://mangashop.example/attack-on-titan-6"] = ("text/html", SHOP_PAGE.encode())
    result = client.post("/api/link-import", json={"url": "https://mangashop.example/attack-on-titan-6"}).get_json()
    assert result["volume"] == {
        "number": "6", "isbn": "9783551799067", "release_date": "2015-02-03", "list_price": 7.5, "currency": "EUR", "pages": 192,
        "description": "Die Jagd auf den weiblichen Titan beginnt.", "image_url": "https://cdn.mangashop.example/covers/aot6.jpg",
        "source_url": "https://mangashop.example/attack-on-titan-6"}
    assert result["edition"] == {"publisher": "Carlsen", "language": "de", "format": "Taschenbuch", "list_price": 7.5, "currency": "EUR"}
    assert result["series"] == {"title": "Attack on Titan", "authors": "Hajime Isayama"}, "the translator is no author"
    assert (result["covers"], result["sources"], result["warnings"]) == (["https://cdn.mangashop.example/covers/aot6.jpg"], ["page"], [])
    assert result["match"] == {"volume_id": None, "edition_id": AOT_DE, "series_id": AOT, "editions": [
        {"id": AOT_DE, "name": "Attack on Titan", "publisher": "Carlsen", "language": "de", "format": "Taschenbuch"},
        {"id": AOT_JA, "name": "進撃の巨人", "publisher": "Kodansha", "language": "ja", "format": "Tankōbon"}]}


def test_a_bookshop_page_is_read_from_its_labels(client, fake_fetch):
    fake_fetch.pages["https://buch.example/frieren-5"] = ("text/html; charset=utf-8", BOOKSHOP_PAGE.encode("utf-8"))
    result = client.post("/api/link-import", json={"url": "https://buch.example/frieren-5"}).get_json()
    assert result["series"] == {"title": "Frieren – Nach dem Ende der Reise", "original_title": "葬送のフリーレン",
                                "authors": "Kanehito Yamada, Tsukasa Abe"}
    volume = result["volume"]
    assert "title" not in volume, "the page's name is the series' title and the number"
    assert (volume["number"], volume["isbn"], volume["release_date"], volume["pages"]) == ("5", "9783770430055", "2022-07-05", 192)
    assert (volume["list_price"], volume["currency"], volume["image_url"]) == (7.0, "EUR", "https://buch.example/img/frieren5.jpg")
    assert result["edition"] == {"publisher": "Egmont Manga", "language": "de", "format": "Taschenbuch", "list_price": 7.0, "currency": "EUR"}
    assert (result["match"]["volume_id"], result["match"]["edition_id"], result["match"]["series_id"]) == (None, FRIEREN_DE, FRIEREN)


def test_the_bookmarklet_snapshot_takes_the_same_way(client, fake_fetch):
    snapshot = {
        "url": "https://shop.example/spy-x-family-2", "title": "Spy x Family 2 | Shop",
        "meta": {"og:title": "Spy x Family 2 | Shop", "og:site_name": "Shop", "og:image": "https://shop.example/spy2.jpg", "book:isbn": "9782842910020"},
        "jsonld": [], "fields": {"Herausgeber": "Kazé; 1. Edition (1. April 2021)", "Taschenbuch": "200 Seiten", "Sprache": "Deutsch"},
    }
    result = client.post("/api/link-import", json={"snapshot": snapshot}).get_json()
    assert (result["series"]["title"], result["volume"]["number"], result["volume"]["isbn"]) == ("Spy x Family", "2", "9782842910020")
    assert (result["volume"]["pages"], result["edition"]) == (200, {"publisher": "Kazé", "language": "de", "format": "Taschenbuch"})
    assert (result["match"]["volume_id"], result["match"]["edition_id"], result["match"]["series_id"]) == (13, SPY_DE, SPY)
    assert fake_fetch.requested == [], "the browser read the page, the server fetches nothing"


def test_a_japanese_shop_is_read_from_its_labels(client):
    snapshot = {
        "url": "https://shop.example.jp/aot1", "meta": {"og:title": "進撃の巨人（1）", "og:image": "https://shop.example.jp/aot1.jpg"},
        "fields": {"シリーズ": "進撃の巨人", "巻": "1", "著者": "諫山創", "出版社": "講談社", "発売日": "2010年3月17日", "ページ数": "194ページ",
                   "言語": "日本語", "価格": "429円", "ISBN": "978-4-06-384276-0"},
    }
    result = client.post("/api/link-import", json={"snapshot": snapshot}).get_json()
    assert result["series"] == {"title": "進撃の巨人", "authors": "諫山創"}
    volume = result["volume"]
    assert (volume["number"], volume["isbn"], volume["release_date"], volume["pages"]) == ("1", "9784063842760", "2010-03-17", 194)
    assert (volume["list_price"], volume["currency"]) == (429, "JPY")
    assert (result["edition"]["publisher"], result["edition"]["language"]) == ("講談社", "ja")
    assert (result["match"]["volume_id"], result["match"]["edition_id"], result["match"]["series_id"]) == (7, AOT_JA, AOT)


def test_what_a_page_does_not_say_is_pointed_out(client):
    result = client.post("/api/link-import", json={"snapshot": {"url": "https://shop.example/x", "meta": {}, "jsonld": [], "fields": {}}}).get_json()
    assert result["warnings"] == ["Auf der Seite war kein Titel zu finden.", "Keine ISBN gefunden – bitte von der Rückseite abtippen oder scannen.",
                                  "Kein Bild gefunden – du kannst eins hochladen."]
    assert (result["series"], result["covers"]) == ({}, [])
    assert result["match"] == {"volume_id": None, "edition_id": None, "series_id": None, "editions": []}


def test_a_page_behind_a_bot_check_says_what_to_do_instead(client, fake_fetch):
    fake_fetch.pages["https://www.amazon.example/dp/1"] = FetchError("Die Seite lässt keinen automatischen Abruf zu (Schutz vor Bots).", blocked=True)
    response = client.post("/api/link-import", json={"url": "https://www.amazon.example/dp/1"})
    assert response.status_code == 422 and response.get_json()["blocked"] is True
    fake_fetch.pages["https://shop.example/gone"] = FetchError("Die Seite antwortet mit Fehler 404.")
    response = client.post("/api/link-import", json={"url": "https://shop.example/gone"})
    assert response.status_code == 422 and response.get_json()["blocked"] is False


@pytest.mark.parametrize("payload, status", [({}, 400), ({"url": ""}, 400), ({"snapshot": "kaputt"}, 400)])
def test_empty_requests_are_refused(client, payload, status):
    assert client.post("/api/link-import", json=payload).status_code == status


def test_a_link_to_something_else_than_a_page_is_refused(client, fake_fetch):
    fake_fetch.pages["https://shop.example/file.zip"] = ("application/zip", b"PK")
    response = client.post("/api/link-import", json={"url": "https://shop.example/file.zip"})
    assert response.status_code == 422 and "Webseite" in response.get_json()["error"]
