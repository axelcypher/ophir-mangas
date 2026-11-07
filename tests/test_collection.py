"""The collection: copies with condition and purchase, what they cost and are worth, the grids of
owned editions and volumes, filters, sorts and groups."""
import pytest

from conftest import ADMIN, AOT, AOT_DE, AOT_JA, FRIEREN_DE, FRIEREN_EN, SPY_DE, login, own, query


def test_copies_are_added_with_their_purchase(client):
    entry = own(client, 5, quantity=2, condition="very_good", purchase_price="6,50", purchased_at="14.03.2025", shop="Thalia",
                location="Regal 1", notes="signiert", first_printing=True, extras="Postkarte")
    assert (entry["quantity"], entry["condition"], entry["purchase_price"], entry["purchased_at"]) == (2, "very_good", 6.5, "2025-03-14")
    assert (entry["shop"], entry["location"], entry["notes"], entry["first_printing"], entry["extras"]) == ("Thalia", "Regal 1", "signiert", 1,
                                                                                                          "Postkarte")
    assert own(client, 1)["condition"] == "new", "a bought volume is new unless said otherwise"


@pytest.mark.parametrize("fields, message", [
    ({"quantity": 0}, "zwischen 1"), ({"quantity": "viele"}, "keine Zahl"), ({"condition": "gelesen"}, "Zustand"),
    ({"purchase_price": "teuer"}, "keine Zahl"), ({"purchased_at": "gestern"}, "kein Datum"),
])
def test_wrong_input_is_refused(client, fields, message):
    response = client.post("/api/collection", json={"volume_id": 5, **fields})
    assert response.status_code == 400 and message in response.get_json()["error"]
    assert client.post("/api/collection", json={"volume_id": 999}).status_code == 404


def test_a_run_bought_at_once_is_added_in_one_go(client):
    response = client.post("/api/collection", json={"volume_ids": [1, 2, 3, 3], "purchase_price": 7, "shop": "Carlsen"})
    assert response.status_code == 201 and len(response.get_json()["created"]) == 3
    assert {row["shop"] for row in query("SELECT shop FROM collection_entries")} == {"Carlsen"}
    assert client.post("/api/collection", json={"volume_ids": [1, 999]}).status_code == 404


def test_the_collection_shows_owned_and_collected_editions(client):
    own(client, 1, purchase_price=7)
    own(client, 6, purchase_price=14)
    own(client, 8)
    client.put(f"/api/editions/{SPY_DE}/collecting")
    data = client.get("/api/collection").get_json()
    rows = {row["id"]: row for row in data["editions"]}
    assert set(rows) == {AOT_DE, FRIEREN_DE, SPY_DE}, "a collected edition without volumes yet is there too"
    assert (rows[AOT_DE]["owned"], rows[AOT_DE]["copies"], rows[AOT_DE]["spent"], rows[AOT_DE]["value"]) == (2, 2, 21, 21)
    assert data["stats"]["volumes"] == 3 and data["stats"]["editions"] == 3 and data["stats"]["series"] == 3


def test_owned_volumes_filter_by_place_and_condition(client):
    own(client, 1, location="Regal", condition="new")
    own(client, 2, location="Kiste", condition="reading_marks")
    own(client, 8, location="Regal")
    ids = lambda **args: [row["id"] for row in client.get("/api/collection", query_string={"level": "volumes", **args}).get_json()["volumes"]]
    assert ids(location="Regal", sort="title") == [1, 8]
    assert ids(condition="reading_marks") == [2]
    assert ids(language="de", sort="added", direction="asc") == [1, 2, 8]
    facets = client.get("/api/collection?level=volumes").get_json()["facets"]
    assert facets["location"] == [["Regal", 2], ["Kiste", 1]]


def test_rows_are_edited_and_deleted_by_their_owner_only(client):
    entry = own(client, 5)
    assert client.patch(f"/api/collection/{entry['id']}", json={"quantity": 3, "shop": "Hugendubel"}).get_json()["quantity"] == 3
    other = login(ADMIN)
    assert other.patch(f"/api/collection/{entry['id']}", json={"quantity": 9}).status_code == 404
    assert other.delete(f"/api/collection/{entry['id']}").status_code == 404
    deleted = client.delete(f"/api/collection/{entry['id']}").get_json()["deleted"]
    assert deleted["shop"] == "Hugendubel" and query("SELECT COUNT(*) n FROM collection_entries")[0]["n"] == 0
    restored = client.post("/api/collection", json={key: deleted[key] for key in ("volume_id", "quantity", "condition", "shop")})
    assert restored.status_code == 201, "what came back is enough to put the row back (undo)"


def test_catalogue_modes_and_value_filters(client):
    own(client, 1)
    client.put(f"/api/editions/{FRIEREN_DE}/collecting")
    ids = lambda **args: sorted(row["id"] for row in client.get("/api/editions", query_string=args).get_json()["editions"])
    assert ids(mode="owned") == [AOT_DE]
    assert ids(mode="collecting") == [FRIEREN_DE]
    assert ids(language="ja") == [AOT_JA]
    assert ids(publisher="Viz Media") == [FRIEREN_EN]
    assert ids(author="Tsukasa Abe") == [FRIEREN_DE, FRIEREN_EN]
    assert ids(genre="Comedy") == [SPY_DE]
    assert ids(q="Shingeki") == [AOT_DE, AOT_JA], "the series' other titles"
    assert ids(q="9783770430031") == [FRIEREN_DE], "an ISBN finds its edition"
    assert ids(q="Friren") == [FRIEREN_DE, FRIEREN_EN], "a letter off is fine"
    facets = client.get("/api/editions").get_json()["facets"]
    assert ["de", 3] in facets["language"] and ["Hajime Isayama", 2] in facets["author"]


def test_catalogue_sorts(client):
    own(client, 8)
    titles = [row["id"] for row in client.get("/api/editions?sort=title").get_json()["editions"]]
    assert titles[:2] == [AOT_DE, AOT_JA]
    progress = [row["id"] for row in client.get("/api/editions?sort=progress").get_json()["editions"]]
    assert progress[0] == FRIEREN_DE
    upcoming = [row["id"] for row in client.get("/api/editions?sort=next").get_json()["editions"]]
    assert upcoming[0] == FRIEREN_DE, "the only one with a coming volume"


def test_editions_in_groups_by_series_author_and_language(client):
    own(client, 1)
    by_series = client.get("/api/editions?group=series").get_json()
    assert "editions" not in by_series and by_series["group"] == "series"
    aot = next(group for group in by_series["groups"] if group["name"] == "Attack on Titan")
    assert (aot["count"], aot["owned"], aot["volumes"]) == (2, 1, 1) and len(aot["samples"]) == 2
    authors = {group["name"]: group["count"] for group in client.get("/api/editions?group=author").get_json()["groups"]}
    assert authors["Kanehito Yamada"] == 2 and authors["Tsukasa Abe"] == 2, "an edition with two authors is in both groups"
    by_count = [group["name"] for group in client.get("/api/editions?group=language&group_sort=count").get_json()["groups"]]
    assert by_count[0] == "de"
    owned_first = client.get("/api/editions?group=series&group_sort=owned").get_json()["groups"][0]
    assert owned_first["name"] == "Attack on Titan"
    assert "editions" in client.get("/api/editions?group=unknown").get_json()


def test_the_volume_grid_has_its_own_modes(client):
    own(client, 1)
    client.put("/api/volumes/2/read")
    ids = lambda **args: [row["id"] for row in client.get("/api/volumes", query_string=args).get_json()["volumes"]]
    assert ids(mode="owned") == [1]
    assert ids(mode="read") == [2]
    assert ids(mode="unread") == [1]
    assert ids(mode="upcoming") == [11]
    assert ids(q="9783551799050") == [5]
    assert ids(series="Spy x Family", sort="title") == [12, 13, 14], "the special volume last"
    first = client.get("/api/volumes?mode=owned").get_json()["volumes"][0]
    assert first["edition_name"] == "Attack on Titan" and first["number_label"] == "1" and first["released"] is True
    assert client.get("/api/volumes").get_json()["total"] == 15


def test_another_account_does_not_see_these_copies(client):
    own(client, 1)
    assert login(ADMIN).get("/api/collection").get_json()["editions"] == []
    assert next(item for item in client.get(f"/api/series/{AOT}").get_json()["editions"])["owned"] == 1
