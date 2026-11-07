"""The shared catalogue: series, editions and volumes, the rules for their fields, duplicates and
who may delete what."""
import pytest

from conftest import AOT, AOT_DE, AOT_JA, FRIEREN, FRIEREN_DE, SPY_DE, login, own, query
from ophir_mangas.catalog import FieldError, is_released, normalize_isbn, number_label, parse_volume_number, split_list


@pytest.mark.parametrize("typed, isbn", [
    ("978-3-551-79905-0", "9783551799050"), ("3551799059", "9783551799050"), ("ISBN 3-551-79905-9", "9783551799050"),
    ("9783551799050", "9783551799050"), ("", ""), ("080442957X", "9780804429573"),
])
def test_isbns_are_read_as_typed_or_scanned(typed, isbn):
    assert normalize_isbn(typed) == isbn


@pytest.mark.parametrize("typed", ["9783551799051", "3551799056", "12345", "9773551799050"])
def test_a_wrong_isbn_is_refused(typed):
    with pytest.raises(FieldError):
        normalize_isbn(typed)


@pytest.mark.parametrize("typed, number", [("5", 5), ("Band 12", 12), ("Vol. 3", 3), ("10,5", 10.5), ("第7巻", 7), ("", None), (4, 4)])
def test_volume_numbers(typed, number):
    assert parse_volume_number(typed) == number


def test_number_labels_and_lists():
    assert (number_label(5.0), number_label(10.5), number_label(None)) == ("5", "10.5", "")
    assert split_list("Kanehito Yamada, Tsukasa Abe; Kanehito Yamada") == ["Kanehito Yamada", "Tsukasa Abe"]


@pytest.mark.parametrize("date, released", [("", True), ("2026-11-07", True), ("2026-11-08", False), ("2026-10", True), ("2026-11", False),
                                            ("2025", True), ("2026", False)])
def test_what_counts_as_released(date, released):
    assert is_released(date, "2026-11-07") is released


def test_a_series_is_created_with_its_list_fields_tidied(client):
    response = client.post("/api/series", json={"title": "  Blue  Lock ", "authors": "Muneyuki Kaneshiro; Yusuke Nomura",
                                                "genres": "Sport, Drama", "demographic": "shounen", "status": "ongoing", "start_year": "2018"})
    assert response.status_code == 201
    series = response.get_json()
    assert (series["title"], series["authors"], series["start_year"], series["editions"]) == ("Blue Lock", "Muneyuki Kaneshiro, Yusuke Nomura", 2018, [])


@pytest.mark.parametrize("payload, text", [({}, "Titel"), ({"title": "X", "demographic": "kids"}, "Zielgruppe"),
                                           ({"title": "X", "start_year": "neunzehn"}, "Startjahr"), ({"title": "X", "source_url": "ftp://x"}, "http")])
def test_a_series_needs_sensible_fields(client, payload, text):
    response = client.post("/api/series", json=payload)
    assert response.status_code == 400 and text in response.get_json()["error"]


def test_the_same_work_is_not_added_twice(client):
    for payload in ({"title": "attack on titan"}, {"title": "Shingeki", "original_title": "進撃の巨人"}, {"title": "AoT", "anilist_id": 53390}):
        response = client.post("/api/series", json=payload)
        assert response.status_code == 409 and response.get_json()["duplicate_id"] == AOT, payload
    assert client.post("/api/series", json={"title": "attack on titan", "force": True}).status_code == 201


def test_a_series_detail_lists_every_edition_with_the_accounts_progress(client):
    own(client, 1)
    series = client.get(f"/api/series/{AOT}").get_json()
    assert [edition["id"] for edition in series["editions"]] == [AOT_DE, AOT_JA], "owned first"
    assert series["editions"][0]["owned"] == 1 and series["stats"]["volumes"] == 1
    assert client.get("/api/series/999").status_code == 404


def test_the_series_picker_finds_by_any_title_or_author(client):
    assert [item["id"] for item in client.get("/api/series?q=Shingeki").get_json()] == [AOT]
    assert [item["id"] for item in client.get("/api/series?q=Yamada").get_json()] == [FRIEREN]
    assert len(client.get("/api/series").get_json()) == 3


def test_an_edition_belongs_to_a_series_and_is_unique_in_it(client):
    created = client.post("/api/editions", json={"series_id": FRIEREN, "publisher": "Shogakukan", "language": "ja", "title": "葬送のフリーレン",
                                                 "list_price": "550", "currency": "jpy", "volume_count": ""})
    assert created.status_code == 201
    edition = created.get_json()
    assert (edition["name"], edition["currency"], edition["list_price"], edition["volumes"]) == ("葬送のフリーレン", "JPY", 550, [])
    again = client.post("/api/editions", json={"series_id": FRIEREN, "publisher": "shogakukan", "language": "ja"})
    assert again.status_code == 409 and again.get_json()["duplicate_id"] == edition["id"]
    assert client.post("/api/editions", json={"series_id": 999, "publisher": "X"}).status_code == 400
    assert client.post("/api/editions", json={"series_id": FRIEREN, "language": "Deutsch"}).status_code == 400


def test_a_perfect_edition_is_an_edition_of_its_own(client):
    response = client.post("/api/editions", json={"series_id": AOT, "publisher": "Carlsen", "language": "de", "format": "Taschenbuch",
                                                  "label": "Deluxe Edition", "collect": True})
    assert response.status_code == 201
    edition = response.get_json()
    assert edition["name"] == "Attack on Titan – Deluxe Edition" and edition["collecting"] is True


def test_a_new_volume_takes_what_its_edition_fixes(client):
    response = client.post("/api/volumes", json={"edition_id": FRIEREN_DE, "number": "5", "isbn": "978-3-7704-3005-5"})
    assert response.status_code == 201, response.get_json()
    volume = response.get_json()
    assert (volume["number_label"], volume["list_price"], volume["currency"], volume["isbn"]) == ("5", 7.0, "EUR", "9783770430055")
    assert volume["edition"]["name"] == "Frieren" and volume["previous_id"] == 11


def test_the_next_volume_starts_after_the_highest(client):
    assert client.get(f"/api/editions/{FRIEREN_DE}/next-volume").get_json() == {"edition_id": FRIEREN_DE, "number": "5", "list_price": 7.0,
                                                                               "currency": "EUR"}
    assert client.get(f"/api/editions/{AOT_JA}/next-volume").get_json()["number"] == "2"


def test_a_volume_needs_a_number_or_as_a_special_volume_a_title(client):
    assert client.post("/api/volumes", json={"edition_id": SPY_DE}).status_code == 400
    special = client.post("/api/volumes", json={"edition_id": SPY_DE, "title": "Fanbook"})
    assert special.status_code == 201 and special.get_json()["number"] is None
    assert client.post("/api/volumes", json={"edition_id": SPY_DE, "title": "fanbook"}).status_code == 409
    assert client.post("/api/volumes", json={"edition_id": SPY_DE, "number": "drei"}).status_code == 400
    assert client.post("/api/volumes", json={"edition_id": 999, "number": 1}).status_code == 400


def test_volumes_are_unique_by_isbn_and_by_number_and_variant(client):
    same_isbn = client.post("/api/volumes", json={"edition_id": AOT_JA, "number": 2, "isbn": "9783551799050"})
    assert same_isbn.status_code == 409 and same_isbn.get_json()["duplicate_id"] == 5 and "ISBN" in same_isbn.get_json()["error"]
    assert client.post("/api/volumes", json={"edition_id": AOT_DE, "number": 5}).status_code == 409
    assert client.post("/api/volumes", json={"edition_id": AOT_DE, "number": 5, "variant": "limited edition"}).status_code == 409
    assert client.post("/api/volumes", json={"edition_id": AOT_DE, "number": 5, "variant": "Variant Cover"}).status_code == 201


def test_a_run_of_numbers_fills_an_edition_without_doubling(client):
    response = client.post(f"/api/editions/{AOT_DE}/volumes", json={"from": 1, "to": 8})
    assert response.status_code == 201 and len(response.get_json()["created"]) == 3, "1 to 5 are there already"
    numbers = [row["number"] for row in query("SELECT number FROM volumes WHERE edition_id=? AND variant='' ORDER BY number", (AOT_DE,))]
    assert numbers == [1, 2, 3, 4, 5, 6, 7, 8]
    assert client.post(f"/api/editions/{AOT_DE}/volumes", json={"from": 1, "to": 500}).status_code == 400


def test_the_edition_dialog_shows_every_number_with_its_volumes_and_the_gaps(client):
    own(client, 1)
    own(client, 6)                    # the Limited Edition of 5 counts for 5
    client.put(f"/api/editions/{AOT_DE}/collecting")
    edition = client.get(f"/api/editions/{AOT_DE}").get_json()
    assert len(edition["slots"]) == 34, "a completed edition of 34 volumes"
    assert edition["slots"][4] == {"number": 5, "number_label": "5", "volumes": [5, 6], "released": True, "gap": False}
    assert edition["slots"][1]["gap"] is True and edition["slots"][33] == {"number": 34, "number_label": "34", "volumes": [], "released": True,
                                                                           "gap": True}
    assert edition["owned"] == 2 and edition["gaps"][:3] == ["2", "3", "4"] and edition["gap_count"] == 32
    assert edition["series"]["title"] == "Attack on Titan" and [other["id"] for other in edition["other_editions"]] == [AOT_JA]


def test_editing_keeps_the_catalogue_free_of_duplicates(client):
    assert client.patch("/api/volumes/4", json={"number": 5}).status_code == 409
    assert client.patch("/api/volumes/4", json={"title": "Der Angriff"}).get_json()["title"] == "Der Angriff"
    assert client.patch(f"/api/editions/{AOT_JA}", json={"publisher": "Carlsen", "language": "de", "format": "Taschenbuch"}).status_code == 409
    assert client.patch(f"/api/series/{FRIEREN}", json={"title": "Attack on Titan"}).status_code == 409
    assert client.patch("/api/volumes/14", json={"title": ""}).status_code == 400, "a special volume keeps a title"


def test_only_unused_entries_can_be_deleted_by_their_creator_or_an_admin(client, admin):
    mine = client.post("/api/series", json={"title": "Eigene Reihe"}).get_json()["id"]
    edition = client.post("/api/editions", json={"series_id": mine, "publisher": "Selbst"}).get_json()["id"]
    volume = client.post("/api/volumes", json={"edition_id": edition, "number": 1}).get_json()["id"]
    assert client.delete("/api/volumes/1").status_code == 403, "created by the admin"
    own(client, volume)
    assert client.delete(f"/api/volumes/{volume}").status_code == 409
    assert client.delete(f"/api/series/{mine}").status_code == 409
    entry = query("SELECT id FROM collection_entries")[0]["id"]
    client.delete(f"/api/collection/{entry}")
    client.put(f"/api/volumes/{volume}/read")
    assert client.delete(f"/api/editions/{edition}").status_code == 409, "a read mark is a use too"
    client.delete(f"/api/volumes/{volume}/read")
    assert client.get(f"/api/series/{mine}").get_json()["can_delete"] is False, "reading it made the series one the account reads"
    client.put(f"/api/series/{mine}/reading", json={"status": ""})
    assert client.get(f"/api/series/{mine}").get_json()["can_delete"] is True
    assert client.delete(f"/api/series/{mine}").get_json() == {"deleted": True}
    assert query("SELECT COUNT(*) n FROM volumes WHERE id=?", (volume,))[0]["n"] == 0, "its editions and volumes go with it"
    assert admin.delete("/api/volumes/14").get_json() == {"deleted": True}


def test_the_catalogue_grid_counts_numbers_not_rows(client):
    own(client, 5)
    own(client, 6)
    aot = next(item for item in client.get("/api/editions").get_json()["editions"] if item["id"] == AOT_DE)
    assert (aot["owned"], aot["copies"], aot["catalogued"], aot["total"]) == (1, 2, 5, 34)


def test_an_isbn_finds_its_volume(client):
    assert client.get("/api/volumes/by-isbn/3551799059").get_json()["id"] == 5
    assert client.get("/api/volumes/by-isbn/9783551799999").status_code in (400, 404)
    missing = client.get("/api/volumes/by-isbn/9783770430055")
    assert missing.status_code == 404 and missing.get_json()["isbn"] == "9783770430055"


def test_suggestions_offer_what_the_catalogue_and_the_account_use(client):
    own(client, 1, shop="Thalia", location="Regal 2")
    suggestions = client.get("/api/catalog/suggestions").get_json()
    assert "Carlsen" in suggestions["publisher"] and "Taschenbuch" in suggestions["format"] and "Hajime Isayama" in suggestions["author"]
    assert suggestions["shop"] == ["Thalia"] and suggestions["location"] == ["Regal 2"] and suggestions["languages"]["de"] == "Deutsch"


def test_another_account_sees_the_same_catalogue_with_its_own_state(client):
    own(client, 1)
    other = login(("admin", "admin"))
    aot = next(item for item in other.get("/api/editions").get_json()["editions"] if item["id"] == AOT_DE)
    assert aot["owned"] == 0
