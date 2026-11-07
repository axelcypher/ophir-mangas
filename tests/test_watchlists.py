"""Wishlists of volumes and whole editions."""
from conftest import ADMIN, AOT_DE, FRIEREN_DE, SPY_DE, default_list, login, own, query


def test_every_account_has_a_default_list_that_stays(client):
    lists = client.get("/api/watchlists").get_json()
    assert [(item["name"], item["is_default"]) for item in lists] == [("Wunschliste", 1)]
    assert client.delete(f"/api/watchlists/{lists[0]['id']}").status_code == 400


def test_lists_are_named_uniquely_renamed_and_deleted(client):
    created = client.post("/api/watchlists", json={"name": "Geburtstag"}).get_json()
    assert client.post("/api/watchlists", json={"name": "geburtstag"}).status_code == 400
    assert client.patch(f"/api/watchlists/{created['id']}", json={"name": "Weihnachten"}).get_json() == {"saved": True}
    assert client.delete(f"/api/watchlists/{created['id']}").get_json() == {"deleted": True}
    assert login(ADMIN).patch(f"/api/watchlists/{default_list(client)}", json={"name": "X"}).status_code == 404


def test_a_list_holds_volumes_with_a_target_price_and_whole_editions(client):
    list_id = default_list(client)
    assert client.post(f"/api/watchlists/{list_id}/volumes", json={"volume_id": 6, "target_price": "10", "note": "Limited"}).status_code == 201
    assert client.post(f"/api/watchlists/{list_id}/editions", json={"edition_id": SPY_DE, "target_price": 5, "note": "anfangen"}).status_code == 201
    assert query("SELECT target_price FROM watchlist_entries WHERE edition_id IS NOT NULL") == [{"target_price": None}], "no target for an edition"
    answer = client.get(f"/api/watchlists/{list_id}/entries").get_json()
    editions = {item["id"]: item for item in answer["editions"]}
    assert editions[SPY_DE]["whole"] is True and editions[SPY_DE]["note"] == "anfangen"
    assert editions[AOT_DE]["whole"] is False and editions[AOT_DE]["wished_volumes"] == ["5"]
    assert answer["list_stats"] == {"editions": 2, "whole": 1, "volumes": 1, "owned": 0, "target_reached": 0, "estimate": 10}
    volumes = client.get(f"/api/watchlists/{list_id}/entries?level=volumes").get_json()["volumes"]
    assert [(item["id"], item["target_price"], item["note"]) for item in volumes] == [(6, 10, "Limited")]


def test_a_volume_whose_market_value_fell_to_the_target_is_marked(client):
    list_id = default_list(client)
    client.post(f"/api/watchlists/{list_id}/volumes", json={"volume_id": 6, "target_price": 20})
    client.post("/api/volumes/6/prices", json={"amount": 25})
    assert client.get(f"/api/watchlists/{list_id}/entries?level=volumes").get_json()["volumes"][0]["target_reached"] is False
    client.post("/api/volumes/6/prices", json={"amount": 19})
    answer = client.get(f"/api/watchlists/{list_id}/entries").get_json()
    assert answer["list_stats"]["target_reached"] == 1 and answer["editions"][0]["target_reached"] == 1


def test_adding_again_updates_and_removing_returns_the_entry(client):
    list_id = default_list(client)
    client.post(f"/api/watchlists/{list_id}/volumes", json={"volume_id": 8, "target_price": 6})
    client.post(f"/api/watchlists/{list_id}/volumes", json={"volume_id": 8, "note": "gebraucht"})
    assert query("SELECT target_price, note FROM watchlist_entries") == [{"target_price": 6, "note": "gebraucht"}]
    assert client.patch(f"/api/watchlists/{list_id}/volumes/8", json={"target_price": ""}).get_json() == {"saved": True}
    removed = client.delete(f"/api/watchlists/{list_id}/volumes/8").get_json()
    assert removed["removed"] == {"volume_id": 8, "target_price": None, "note": "gebraucht"} and removed["lists"][0]["count"] == 0
    assert client.delete(f"/api/watchlists/{list_id}/volumes/8").status_code == 404
    assert client.post(f"/api/watchlists/{list_id}/editions", json={"edition_id": 999}).status_code == 404


def test_the_wish_marks_reach_the_catalogue(client):
    list_id = default_list(client)
    client.post(f"/api/watchlists/{list_id}/editions", json={"edition_id": FRIEREN_DE})
    client.post(f"/api/watchlists/{list_id}/volumes", json={"volume_id": 1})
    rows = {item["id"]: item for item in client.get("/api/editions?mode=wished").get_json()["editions"]}
    assert set(rows) == {FRIEREN_DE, AOT_DE} and rows[FRIEREN_DE]["edition_wished"] is True and rows[AOT_DE]["edition_wished"] is False
    assert client.get("/api/volumes/1").get_json()["wished"] is True


def test_the_missing_mode_hides_owned_volumes(client):
    list_id = default_list(client)
    client.post(f"/api/watchlists/{list_id}/volumes", json={"volume_id": 1})
    client.post(f"/api/watchlists/{list_id}/volumes", json={"volume_id": 2})
    own(client, 1)
    ids = [item["id"] for item in client.get(f"/api/watchlists/{list_id}/entries?level=volumes&mode=missing").get_json()["volumes"]]
    assert ids == [2]


def test_lists_are_private(client):
    list_id = default_list(client)
    other = login(ADMIN)
    assert other.get(f"/api/watchlists/{list_id}/entries").status_code == 404
    assert other.post(f"/api/watchlists/{list_id}/volumes", json={"volume_id": 1}).status_code == 404
