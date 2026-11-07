"""Filling in a volume from its ISBN (DNB, Google Books, Open Library) and a series from AniList,
the matching against the catalogue, and the guards of the JSON POST the AniList lookup uses."""
import pytest

import ophir_mangas
from conftest import AOT, AOT_DE, AOT_JA, SPY, SPY_DE
from ophir_mangas.fetch import FetchError
from ophir_mangas.lookup import (ANILIST_URL, DNB_COVER, DNB_URL, GOOGLE_URL, NOTHING_FOUND, OPENLIBRARY_URL, euro_price, person_name,
                                 split_title_number)

AOT6 = "9783551799067"          # Attack on Titan 6: not in the sample catalogue, its edition AOT_DE is
SPY_GUIDE = "9782842910990"     # Spy x Family Official Guide: in the sample catalogue (volume 14)
CONTROL_008 = "140612s2015    gw ||||| |||| 00||||ger  "

AOT6_MARC = f"""<record xmlns="http://www.loc.gov/MARC21/slim" type="Bibliographic">
<leader>00000nam a2200000 c 4500</leader>
<controlfield tag="001">1060001234</controlfield>
<controlfield tag="008">{CONTROL_008}</controlfield>
<datafield tag="020" ind1=" " ind2=" "><subfield code="a">9783551799067</subfield>
  <subfield code="c">kart. : EUR 7.80 (AT), EUR 7.50 (DE), sfr 10.50 (freier Pr.)</subfield><subfield code="9">978-3-551-79906-7</subfield></datafield>
<datafield tag="041" ind1="1" ind2=" "><subfield code="a">ger</subfield><subfield code="h">jpn</subfield></datafield>
<datafield tag="100" ind1="1" ind2=" "><subfield code="0">(DE-588)1034567890</subfield><subfield code="a">Isayama, Hajime</subfield>
  <subfield code="d">1986-</subfield><subfield code="4">aut</subfield></datafield>
<datafield tag="245" ind1="1" ind2="0"><subfield code="a">Attack on Titan</subfield><subfield code="n">6</subfield>
  <subfield code="c">Hajime Isayama ; aus dem Japanischen von Claudia Peter</subfield></datafield>
<datafield tag="250" ind1=" " ind2=" "><subfield code="a">1. Auflage</subfield></datafield>
<datafield tag="264" ind1=" " ind2="1"><subfield code="a">Hamburg</subfield><subfield code="b">Carlsen</subfield><subfield code="c">[2015]</subfield></datafield>
<datafield tag="300" ind1=" " ind2=" "><subfield code="a">192 Seiten</subfield><subfield code="b">Illustrationen</subfield><subfield code="c">18 cm</subfield></datafield>
<datafield tag="490" ind1="0" ind2=" "><subfield code="a">Carlsen Manga!</subfield></datafield>
<datafield tag="490" ind1="1" ind2=" "><subfield code="a">Attack on Titan</subfield><subfield code="v">Band 6</subfield></datafield>
<datafield tag="700" ind1="1" ind2=" "><subfield code="a">Peter, Claudia</subfield><subfield code="4">trl</subfield><subfield code="e">Übersetzer</subfield></datafield>
</record>"""

SPY_GUIDE_MARC = f"""<record xmlns="http://www.loc.gov/MARC21/slim" type="Bibliographic">
<controlfield tag="001">1290009876</controlfield>
<controlfield tag="008">{CONTROL_008}</controlfield>
<datafield tag="020" ind1=" " ind2=" "><subfield code="a">978-2-84291-099-0</subfield><subfield code="c">Pp. : EUR 12.00</subfield></datafield>
<datafield tag="100" ind1="1" ind2=" "><subfield code="a">Endō, Tatsuya,</subfield></datafield>
<datafield tag="245" ind1="1" ind2="0"><subfield code="a">Spy x Family :</subfield><subfield code="b">Official Guide /</subfield></datafield>
<datafield tag="264" ind1=" " ind2="1"><subfield code="b">Kazé</subfield><subfield code="c">2023</subfield></datafield>
<datafield tag="300" ind1=" " ind2=" "><subfield code="a">256 S.</subfield></datafield>
<datafield tag="490" ind1="0" ind2=" "><subfield code="a">Spy x Family</subfield></datafield>
</record>"""


def sru(*records):
    """An SRU searchRetrieve answer of the DNB with these MARC 21 records."""
    items = "".join(f"<record><recordSchema>MARC21-xml</recordSchema><recordPacking>xml</recordPacking><recordData>{record}</recordData>"
                    f"<recordPosition>{index}</recordPosition></record>" for index, record in enumerate(records, 1))
    return ('<?xml version="1.0" encoding="UTF-8"?><searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/"><version>1.1</version>'
            f"<numberOfRecords>{len(records)}</numberOfRecords><records>{items}</records></searchRetrieveResponse>").encode("utf-8")


GOOGLE_AOT6 = b"""{"kind": "books#volumes", "totalItems": 1, "items": [{"id": "aot6", "volumeInfo": {
  "title": "Attack on Titan 6", "authors": ["Hajime Isayama"], "publisher": "CARLSEN Verlag GmbH", "publishedDate": "2015-02-03",
  "description": "Die Jagd auf den <b>weiblichen Titan</b> beginnt.", "pageCount": 190, "language": "de",
  "imageLinks": {"smallThumbnail": "http://books.google.com/books/content?id=aot6&printsec=frontcover&img=1&zoom=5&edge=curl&source=gbs_api",
                 "thumbnail": "http://books.google.com/books/content?id=aot6&printsec=frontcover&img=1&zoom=1&edge=curl&source=gbs_api"},
  "infoLink": "https://books.google.de/books?id=aot6"}}]}"""
GOOGLE_COVER = "https://books.google.com/books/content?id=aot6&printsec=frontcover&img=1&zoom=1&source=gbs_api"
OPENLIBRARY_AOT6 = b"""{"ISBN:9783551799067": {"url": "https://openlibrary.org/books/OL1M/Attack_on_Titan_6", "title": "Attack on Titan 6",
  "authors": [{"url": "https://openlibrary.org/authors/OL1A", "name": "Hajime Isayama"}], "publishers": [{"name": "Carlsen"}],
  "publish_date": "Feb 3, 2015", "number_of_pages": 192, "cover": {"large": "https://covers.openlibrary.org/b/id/1-L.jpg"}}}"""


def answer(fake_fetch, isbn, dnb=None, google=None, openlibrary=None):
    for url, kind, body in ((DNB_URL, "application/xml", dnb), (GOOGLE_URL, "application/json", google),
                            (OPENLIBRARY_URL, "application/json", openlibrary)):
        if body is not None:
            fake_fetch.pages[url.format(isbn=isbn)] = body if isinstance(body, Exception) else (kind, body)


@pytest.mark.parametrize("text, expected", [
    ("Attack on Titan 5", ("Attack on Titan", "5")), ("Frieren 3", ("Frieren", "3")), ("Attack on Titan, Band 5", ("Attack on Titan", "5")),
    ("Frieren: Beyond Journey's End, Vol. 1", ("Frieren: Beyond Journey's End", "1")), ("Spy x Family Bd. 12", ("Spy x Family", "12")),
    ("Naruto - Band 12", ("Naruto", "12")), ("One Piece 10.5", ("One Piece", "10.5")), ("Attack on Titan (Band 5)", ("Attack on Titan", "5")),
    ("進撃の巨人(5)", ("進撃の巨人", "5")), ("進撃の巨人 第5巻", ("進撃の巨人", "5")), ("Band 5", ("", "5")),
    ("Attack on Titan", ("Attack on Titan", "")), ("Kaiju No. 8", ("Kaiju No. 8", "")), ("Kaiju No. 8 3", ("Kaiju No. 8", "3")),
    ("1984", ("1984", "")), ("Akira (1982)", ("Akira (1982)", "")),
])
def test_series_title_and_number_are_split(text, expected):
    assert split_title_number(text) == expected


@pytest.mark.parametrize("terms, price", [
    ("kart. : EUR 7.80 (AT), EUR 7.50 (DE), sfr 10.50 (freier Pr.)", 7.5), ("EUR 7,80 (AT)", 7.8), ("Pp. : 12,00 EUR", 12.0), ("sfr 10.50", None),
])
def test_the_german_price_is_taken_from_the_terms_of_availability(terms, price):
    assert euro_price(terms) == price


@pytest.mark.parametrize("text, name", [("Isayama, Hajime", "Hajime Isayama"), ("Endō, Tatsuya,", "Tatsuya Endō"),
                                        ("Isayama, Hajime, 1986-", "Hajime Isayama"), ("Oda", "Oda")])
def test_marc_names_are_turned_around(text, name):
    assert person_name(text) == name


def test_an_isbn_is_filled_in_from_all_three_sources_dnb_first(client, fake_fetch):
    answer(fake_fetch, AOT6, sru(AOT6_MARC), GOOGLE_AOT6, OPENLIBRARY_AOT6)
    result = client.get("/api/lookup/isbn/978-3-551-79906-7").get_json()
    assert (result["isbn"], result["found"], result["sources"], result["warnings"]) == (AOT6, True, ["dnb", "google", "openlibrary"], [])
    assert result["volume"] == {
        "number": "6", "isbn": AOT6, "release_date": "2015-02-03", "list_price": 7.5, "currency": "EUR", "pages": 192,
        "description": "Die Jagd auf den weiblichen Titan beginnt.", "image_url": DNB_COVER.format(isbn=AOT6),
        "source_url": "https://d-nb.info/1060001234"}, "DNB first; Google adds the day and the description"
    assert result["edition"] == {"publisher": "Carlsen", "language": "de", "list_price": 7.5, "currency": "EUR"}
    assert result["series"] == {"title": "Attack on Titan", "authors": "Hajime Isayama"}, "the translator is no author, the imprint no series"
    assert result["covers"] == [DNB_COVER.format(isbn=AOT6), "https://covers.openlibrary.org/b/id/1-L.jpg", GOOGLE_COVER]
    assert result["match"] == {"volume_id": None, "edition_id": AOT_DE, "series_id": AOT, "editions": [
        {"id": AOT_DE, "name": "Attack on Titan", "publisher": "Carlsen", "language": "de", "format": "Taschenbuch"},
        {"id": AOT_JA, "name": "進撃の巨人", "publisher": "Kodansha", "language": "ja", "format": "Tankōbon"}]}


def test_a_failing_source_costs_a_warning_and_the_others_still_answer(client, fake_fetch):
    blocked = FetchError("Die Seite lässt keinen automatischen Abruf zu (Schutz vor Bots).", blocked=True)
    answer(fake_fetch, AOT6, blocked, GOOGLE_AOT6, b"{}")
    response = client.get(f"/api/lookup/isbn/{AOT6}")
    result = response.get_json()
    assert response.status_code == 200 and result["found"] and result["sources"] == ["google"]
    assert result["warnings"] == ["Deutsche Nationalbibliothek nicht erreichbar: Die Seite lässt keinen automatischen Abruf zu (Schutz vor Bots).",
                                  "Open Library kennt diese ISBN nicht."]
    assert (result["volume"]["number"], result["volume"]["pages"], result["volume"]["image_url"]) == ("6", 190, GOOGLE_COVER)
    assert "list_price" not in result["volume"] and result["covers"] == [GOOGLE_COVER]
    assert result["edition"]["publisher"] == "CARLSEN Verlag GmbH"
    assert (result["match"]["series_id"], result["match"]["edition_id"]) == (AOT, AOT_DE), "Carlsen Verlag GmbH is the catalogue's Carlsen"


def test_an_unreadable_answer_is_a_warning_too(client, fake_fetch):
    answer(fake_fetch, AOT6, b"<html><body>Wartungsarbeiten</body>", openlibrary=OPENLIBRARY_AOT6)
    result = client.get(f"/api/lookup/isbn/{AOT6}").get_json()
    assert result["warnings"] == ["Deutsche Nationalbibliothek hat eine unlesbare Antwort geschickt.",
                                  "Google Books nicht erreichbar: Die Seite antwortet mit Fehler 404."]
    assert result["sources"] == ["openlibrary"] and result["covers"] == ["https://covers.openlibrary.org/b/id/1-L.jpg"]
    assert (result["volume"]["number"], result["volume"]["release_date"], result["series"]["title"]) == ("6", "2015-02-03", "Attack on Titan")


def test_an_isbn_nobody_knows_still_finds_the_catalogue_volume(client, fake_fetch):
    """Given as ISBN-10; the volume is Attack on Titan 5 of the sample catalogue."""
    answer(fake_fetch, "9783551799050", sru(), b'{"kind": "books#volumes", "totalItems": 0}', b"{}")
    result = client.get("/api/lookup/isbn/3-551-79905-9").get_json()
    assert (result["isbn"], result["found"], result["warnings"], result["sources"]) == ("9783551799050", False, [NOTHING_FOUND], [])
    assert (result["volume"], result["edition"], result["series"], result["covers"]) == ({"isbn": "9783551799050"}, {}, {}, [])
    assert (result["match"]["volume_id"], result["match"]["edition_id"], result["match"]["series_id"]) == (5, AOT_DE, AOT)
    assert DNB_URL.format(isbn="9783551799050") in fake_fetch.requested


def test_a_special_volume_from_the_dnb_alone(client, fake_fetch):
    answer(fake_fetch, SPY_GUIDE, sru(SPY_GUIDE_MARC), b'{"totalItems": 0}', b"{}")
    result = client.get(f"/api/lookup/isbn/{SPY_GUIDE}").get_json()
    volume = result["volume"]
    assert "number" not in volume and volume["title"] == "Official Guide"
    assert (volume["list_price"], volume["pages"], volume["release_date"]) == (12.0, 256, "2023")
    assert result["edition"] == {"publisher": "Kazé", "language": "de", "list_price": 12.0, "currency": "EUR"}, "language from 008"
    assert result["series"] == {"title": "Spy x Family", "authors": "Tatsuya Endō"}
    assert result["warnings"] == ["Google Books kennt diese ISBN nicht.", "Open Library kennt diese ISBN nicht."]
    assert (result["match"]["volume_id"], result["match"]["edition_id"], result["match"]["series_id"]) == (14, SPY_DE, SPY)


@pytest.mark.parametrize("isbn", ["9783551799051", "12345", "abc"])
def test_no_isbn_no_lookup(client, fake_fetch, isbn):
    response = client.get(f"/api/lookup/isbn/{isbn}")
    assert response.status_code == 400 and "ISBN" in response.get_json()["error"]
    assert fake_fetch.requested == []


AOT_MEDIA = {
    "id": 53390, "title": {"romaji": "Shingeki no Kyojin", "english": "Attack on Titan", "native": "進撃の巨人"},
    "synonyms": ["AoT", "SnK", "Attack on Titan", "L'Attaque des Titans, la série"],
    "staff": {"edges": [{"role": "Story & Art", "node": {"name": {"full": "Hajime Isayama"}}},
                        {"role": "Translator (English)", "node": {"name": {"full": "Sheldon Drzka"}}},
                        {"role": "Assistant", "node": {"name": {"full": "Someone Else"}}}]},
    "genres": ["Action", "Drama", "Fantasy", "Mystery", "Psychological", "Supernatural"],
    "tags": [{"name": "Survival", "category": "Theme-Other"}, {"name": "Shounen", "category": "Demographic"}],
    "status": "FINISHED", "volumes": 34, "startDate": {"year": 2009},
    "coverImage": {"extraLarge": "https://s4.anilist.co/file/anilistcdn/media/manga/cover/large/bx53390.jpg",
                   "large": "https://s4.anilist.co/file/anilistcdn/media/manga/cover/medium/bx53390.jpg"},
    "description": "Several hundred years ago, humans were nearly exterminated by titans.<br><br>\n<i>Titans</i> are typically several "
                   "stories tall.<br><br>\n(Source: Kodansha USA)",
    "countryOfOrigin": "JP", "siteUrl": "https://anilist.co/manga/53390", "format": "MANGA",
}
KIDS_MEDIA = {
    "id": 999001, "title": {"romaji": "Chiisana Mahou", "english": None, "native": "ちいさなまほう"}, "synonyms": [],
    "staff": {"edges": [{"role": "Story", "node": {"name": {"full": "Aki Mori"}}}, {"role": "Art", "node": {"name": {"full": "Ben Kato"}}}]},
    "genres": ["Adventure", "Sci-Fi", "Sports", "Comedy"], "tags": [{"name": "Kids", "category": "Demographic"}],
    "status": "RELEASING", "volumes": None, "startDate": {"year": 2023}, "coverImage": {"extraLarge": None, "large": "https://s4.anilist.co/k.jpg"},
    "description": None, "countryOfOrigin": "JP", "siteUrl": "https://anilist.co/manga/999001", "format": "MANGA",
}
NIGHT_MEDIA = {
    "id": 999002, "title": {"romaji": "Yoru no Hanashi", "english": "Night Story", "native": "夜の話"},
    "synonyms": [f"Night {index}" for index in range(10)], "staff": {"edges": []}, "genres": ["Romance", "Hentai"],
    "tags": [{"name": "Seinen", "category": "Demographic"}], "status": "CANCELLED", "volumes": 3, "startDate": {"year": None},
    "coverImage": {}, "description": "", "siteUrl": "https://anilist.co/manga/999002",
}


def test_anilist_entries_become_series_with_german_genres(client, fake_fetch):
    fake_fetch.posts[ANILIST_URL] = {"data": {"Page": {"media": [AOT_MEDIA, KIDS_MEDIA, NIGHT_MEDIA]}}}
    results = client.get("/api/lookup/anilist?q=attack").get_json()["results"]
    url, payload = fake_fetch.posted[0]
    assert url == ANILIST_URL and payload["variables"] == {"search": "attack"} and "type: MANGA" in payload["query"]

    aot, kids, night = results
    assert aot["series"] == {
        "title": "Attack on Titan", "original_title": "進撃の巨人", "alt_titles": "Shingeki no Kyojin, AoT, SnK", "authors": "Hajime Isayama",
        "genres": "Action, Drama, Fantasy, Mystery, Psychologie, Übernatürliches", "demographic": "shounen", "status": "completed",
        "original_volumes": 34, "start_year": 2009,
        "description": "Several hundred years ago, humans were nearly exterminated by titans.\n\nTitans are typically several stories tall.",
        "image_url": AOT_MEDIA["coverImage"]["extraLarge"], "source_url": "https://anilist.co/manga/53390", "anilist_id": 53390}
    assert aot["covers"] == [AOT_MEDIA["coverImage"]["extraLarge"], AOT_MEDIA["coverImage"]["large"]] and aot["match"] == {"series_id": AOT}

    assert kids["series"]["title"] == "Chiisana Mahou" and "alt_titles" not in kids["series"], "romaji is the title when there is no English one"
    assert (kids["series"]["authors"], kids["series"]["genres"]) == ("Aki Mori, Ben Kato", "Abenteuer, Science-Fiction, Sport, Comedy")
    assert (kids["series"]["demographic"], kids["series"]["status"], kids["series"]["image_url"]) == ("kodomo", "ongoing", "https://s4.anilist.co/k.jpg")
    assert "original_volumes" not in kids["series"] and kids["match"] == {"series_id": None}

    assert night["series"]["alt_titles"] == "Yoru no Hanashi, Night 0, Night 1, Night 2, Night 3, Night 4, Night 5, Night 6"
    assert (night["series"]["genres"], night["series"]["demographic"], night["series"]["status"]) == ("Romance", "seinen", "cancelled")
    assert night["covers"] == [] and "authors" not in night["series"]


def test_an_anilist_entry_by_id_is_matched_by_its_id(client, fake_fetch):
    renamed = {**AOT_MEDIA, "title": {"romaji": "Kyojin", "english": "Titans", "native": "巨人"}, "synonyms": []}
    fake_fetch.posts[ANILIST_URL] = lambda payload: {"data": {"Media": renamed if payload["variables"]["id"] == 53390 else None}}
    result = client.get("/api/lookup/anilist/53390").get_json()
    assert result["series"]["title"] == "Titans" and result["match"] == {"series_id": AOT}, "no title in common, the same AniList entry"
    missing = client.get("/api/lookup/anilist/1")
    assert missing.status_code == 404 and missing.get_json()["error"]
    fake_fetch.posts[ANILIST_URL] = FetchError("Der Dienst antwortet mit Fehler 404.", status=404)
    assert client.get("/api/lookup/anilist/2").status_code == 404, "AniList answers an unknown id with 404"


def test_a_failing_anilist_is_a_bad_gateway(client, fake_fetch):
    fake_fetch.posts[ANILIST_URL] = FetchError("Der Dienst antwortet mit Fehler 500.", status=500)
    response = client.get("/api/lookup/anilist?q=frieren")
    assert response.status_code == 502 and "AniList" in response.get_json()["error"]
    assert client.get("/api/lookup/anilist/53390").status_code == 502
    fake_fetch.posts[ANILIST_URL] = {"errors": [{"message": "Too Many Requests.", "status": 429}], "data": None}
    assert client.get("/api/lookup/anilist?q=frieren").status_code == 502


def test_an_anilist_search_needs_two_characters(client, fake_fetch):
    assert client.get("/api/lookup/anilist?q=a").status_code == 400
    assert client.get("/api/lookup/anilist").status_code == 400
    assert fake_fetch.posted == []


def test_lookups_need_a_login(anonymous):
    assert anonymous.get(f"/api/lookup/isbn/{AOT6}").status_code == 401
    assert anonymous.get("/api/lookup/anilist?q=attack").status_code == 401


class Answer:
    def __init__(self, status, body=b"", headers=None):
        self.status_code, self.body, self.headers = status, body, headers or {}
        self.is_redirect = status in (301, 302, 303, 307, 308)

    def iter_content(self, size):
        for start in range(0, len(self.body), size):
            yield self.body[start:start + size]

    def close(self):
        pass


class Session:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.answer


@pytest.mark.parametrize("url", ["http://127.0.0.1:8080/graphql", "http://192.168.1.10/api", "ftp://graphql.anilist.co/"])
def test_a_json_post_into_the_local_network_is_never_sent(url):
    session = Session(Answer(200, b"{}"))
    with pytest.raises(FetchError):
        ophir_mangas.fetch.post_json(url, {"query": "{}"}, session=session)
    assert session.calls == []


def test_a_json_post_does_not_follow_a_redirect(monkeypatch):
    monkeypatch.setattr(ophir_mangas.fetch, "public_address", lambda host: True)
    session = Session(Answer(307, headers={"Location": "http://127.0.0.1/graphql"}))
    with pytest.raises(FetchError, match="Weiterleitung"):
        ophir_mangas.fetch.post_json("https://graphql.example/", {"query": "{}"}, session=session)
    assert len(session.calls) == 1


def test_a_json_post_sends_json_and_reads_json(monkeypatch):
    monkeypatch.setattr(ophir_mangas.fetch, "public_address", lambda host: True)
    session = Session(Answer(200, b'{"data": {"Page": {"media": []}}}'))
    assert ophir_mangas.fetch.post_json("https://graphql.example/", {"query": "{}"}, session=session) == {"data": {"Page": {"media": []}}}
    url, options = session.calls[0]
    assert options["json"] == {"query": "{}"} and options["allow_redirects"] is False and options["timeout"]
    assert options["headers"]["User-Agent"] == ophir_mangas.fetch.USER_AGENT


@pytest.mark.parametrize("answer, blocked, status", [
    (Answer(429), True, 429), (Answer(403), True, 403), (Answer(500), False, 500), (Answer(200, b"<html>"), False, None),
    (Answer(200, b"[1, 2]"), False, None), (Answer(200, b'{"x": "' + b"a" * 200 + b'"}'), False, None),
])
def test_a_json_post_that_brings_no_usable_answer_fails(monkeypatch, answer, blocked, status):
    monkeypatch.setattr(ophir_mangas.fetch, "public_address", lambda host: True)
    with pytest.raises(FetchError) as caught:
        ophir_mangas.fetch.post_json("https://graphql.example/", {}, max_bytes=100, session=Session(answer))
    assert (caught.value.blocked, caught.value.status) == (blocked, status)
