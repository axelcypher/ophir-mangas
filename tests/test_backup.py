"""Backup, restore (also onto another instance), undo, and CSV exports."""
import copy

from conftest import AOT, AOT_DE, FRIEREN, SPY_DE, default_list, fresh_database, own, query  # noqa: F401


def fill(client):
    own(client, 1, purchase_price=7, shop="Thalia", condition="very_good", first_printing=True)
    own(client, 6, purchase_price=14)
    client.post(f"/api/watchlists/{default_list(client)}/volumes", json={"volume_id": 9, "target_price": 6, "note": "billig"})
    client.post(f"/api/watchlists/{default_list(client)}/editions", json={"edition_id": SPY_DE, "note": "anfangen"})
    preorder = client.post("/api/preorders", json={"volume_id": 11, "shop": "Amazon", "price": 7, "order_number": "A-1"}).get_json()
    client.patch(f"/api/preorders/{preorder['id']}", json={"expected_release": "2099-03"})
    client.put("/api/volumes/1/read")
    client.put(f"/api/series/{FRIEREN}/reading", json={"status": "planned"})
    client.put(f"/api/editions/{AOT_DE}/collecting")


def test_the_backup_carries_everything_the_account_entered_and_the_catalogue_it_needs(client):
    fill(client)
    data = client.get("/api/export.json").get_json()
    assert data["format"] == "ophir-mangas-backup" and data["user"]["username"] == "demo"
    assert {item["ref"] for item in data["series"]} == {AOT, FRIEREN, 3}
    aot_de = next(item for item in data["editions"] if item["ref"] == AOT_DE)
    assert aot_de["publisher"] == "Carlsen" and aot_de["series_ref"] == AOT
    assert len([item for item in data["volumes"] if item["edition_ref"] == AOT_DE]) == 6, "an edition with all its volumes"
    assert data["collection"][0]["first_printing"] == 1 and data["reads"] == [{"volume_ref": 1, "read_at": data["reads"][0]["read_at"]}]
    assert {(item["series_ref"], item["status"]) for item in data["reading"]} == {(AOT, "reading"), (FRIEREN, "planned")}
    assert data["collecting"][0]["edition_ref"] == AOT_DE
    entries = data["watchlists"][0]["entries"]
    assert {(entry["volume_ref"], entry["edition_ref"]) for entry in entries} == {(9, None), (None, SPY_DE)}
    assert [event["kind"] for event in data["preorders"][0]["events"]] == ["created", "release"]


def test_a_backup_restores_onto_an_empty_instance(client):
    fill(client)
    data = client.get("/api/export.json").get_json()
    for table in ("collection_entries", "watchlist_entries", "preorder_events", "preorders", "volume_reads", "series_reading", "collected_editions",
                  "volumes", "editions", "series"):
        query(f"DELETE FROM {table}")
    preview = client.post("/api/import/json/preview", json={"data": data}).get_json()
    assert (preview["series_new"], preview["editions_new"], preview["volumes_new"]) == (3, 3, len(data["volumes"]))
    result = client.post("/api/import/json/apply", json={"data": data}).get_json()
    assert result["series_created"] == 3 and result["collection"] == 2 and result["preorders"] == 1 and result["reads"] == 1
    aot = next(item for item in client.get("/api/collection").get_json()["editions"] if item["series_title"] == "Attack on Titan")
    assert aot["owned"] == 2 and aot["collecting"] is True and aot["read"] == 1
    assert client.get("/api/reading").get_json()["counts"] == {"reading": 1, "planned": 1, "paused": 0, "finished": 0, "dropped": 0, "none": 0}


def test_restoring_onto_the_same_catalogue_matches_and_skips_what_is_there(client):
    fill(client)
    data = client.get("/api/export.json").get_json()
    preview = client.post("/api/import/json/preview", json={"data": data}).get_json()
    assert (preview["series_new"], preview["editions_new"], preview["volumes_new"]) == (0, 0, 0)
    result = client.post("/api/import/json/apply", json={"data": data, "strategy": "replace"}).get_json()
    assert result["preorders_skipped"] == 1 and result["replaced"] == 2 and result["collection"] == 2
    assert result["reads"] == 0 and result["reading"] == 0, "what the account has stays as it is"
    assert query("SELECT COUNT(*) n FROM collection_entries")[0]["n"] == 2


def test_the_latest_restore_can_be_taken_back(client):
    fill(client)
    data = copy.deepcopy(client.get("/api/export.json").get_json())
    data["series"].append({"ref": 99, "title": "Neue Reihe"})
    data["editions"].append({"ref": 99, "series_ref": 99, "publisher": "Neu", "language": "de"})
    data["volumes"].append({"ref": 99, "edition_ref": 99, "number": 1})
    data["collection"].append({"volume_ref": 99, "quantity": 1})
    operation = client.post("/api/import/json/apply", json={"data": data}).get_json()["operation_id"]
    assert query("SELECT COUNT(*) n FROM series WHERE title='Neue Reihe'")[0]["n"] == 1
    assert client.post(f"/api/import/{operation}/undo").get_json() == {"undone": True}
    assert query("SELECT COUNT(*) n FROM series WHERE title='Neue Reihe'")[0]["n"] == 0, "what it created and nothing uses goes"
    assert query("SELECT COUNT(*) n FROM collection_entries")[0]["n"] == 2
    assert client.post(f"/api/import/{operation}/undo").status_code == 400


def test_a_broken_backup_is_refused(client):
    assert client.post("/api/import/json/preview", json={"data": {"format": "other"}}).status_code == 400
    data = {"format": "ophir-mangas-backup", "series": [], "editions": [{"ref": 1, "series_ref": 5}], "volumes": []}
    assert "Reihe" in client.post("/api/import/json/preview", json={"data": data}).get_json()["error"]
    data = {"format": "ophir-mangas-backup", "series": [{"ref": 1, "title": ""}], "editions": [], "volumes": []}
    assert client.post("/api/import/json/apply", json={"data": data}).status_code == 400


def test_csv_tables_for_spreadsheets(client):
    fill(client)
    table = client.get("/api/export.csv").get_data(as_text=True)
    assert table.startswith("﻿Reihe;Ausgabe;") and "Attack on Titan;Attack on Titan;Hajime Isayama;Carlsen;de" in table
    assert "Sehr gut;ja;" in table and "Limited Edition" in table
    preorders = client.get("/api/export/preorders.csv").get_data(as_text=True)
    assert "Frieren;4;" in preorders and "Bestellt;Amazon;A-1" in preorders
