"""Read marks on volumes and the reading status of series."""
from conftest import AOT, AOT_DE, FRIEREN, FRIEREN_DE, query


def status(client, series_id):
    return client.get(f"/api/series/{series_id}").get_json()["reading_status"]


def test_a_volume_can_be_read_without_owning_it(client):
    assert client.put("/api/volumes/8/read").get_json() == {"read": True, "reading_status": "reading"}
    volume = client.get("/api/volumes/8").get_json()
    assert volume["read"] is True and volume["owned"] == 0 and volume["read_at"]
    assert client.delete("/api/volumes/8/read").get_json() == {"read": False}
    assert client.get("/api/volumes/8").get_json()["read"] is False
    assert client.put("/api/volumes/999/read").status_code == 404


def test_the_first_read_volume_starts_a_planned_series_but_leaves_a_chosen_status(client):
    client.put(f"/api/series/{FRIEREN}/reading", json={"status": "planned"})
    client.put("/api/volumes/8/read")
    assert status(client, FRIEREN) == "reading"
    client.put(f"/api/series/{FRIEREN}/reading", json={"status": "paused"})
    client.put("/api/volumes/9/read")
    assert status(client, FRIEREN) == "paused", "a status the account chose stays"


def test_reading_through_a_number_marks_the_ones_before_and_unmarks_the_ones_after(client):
    response = client.post(f"/api/editions/{AOT_DE}/read", json={"through": 4}).get_json()
    assert response == {"through": "4", "reading_status": "reading"}
    read = {row["volume_id"] for row in query("SELECT volume_id FROM volume_reads")}
    assert read == {1, 2, 3, 4}
    client.post(f"/api/editions/{AOT_DE}/read", json={"through": 5})
    assert {row["volume_id"] for row in query("SELECT volume_id FROM volume_reads")} == {1, 2, 3, 4, 5, 6}, "variants of 5 too"
    client.post(f"/api/editions/{AOT_DE}/read", json={"through": 2})
    assert {row["volume_id"] for row in query("SELECT volume_id FROM volume_reads")} == {1, 2}
    client.post(f"/api/editions/{AOT_DE}/read", json={"through": 0})
    assert query("SELECT COUNT(*) n FROM volume_reads")[0]["n"] == 0
    assert client.post(f"/api/editions/{AOT_DE}/read", json={"through": "fünf"}).status_code == 400


def test_reading_the_last_volume_of_a_completed_edition_finishes_the_series(client):
    client.post(f"/api/editions/{AOT_DE}/volumes", json={"from": 6, "to": 34})
    client.post(f"/api/editions/{AOT_DE}/read", json={"through": 33})
    assert status(client, AOT) == "reading"
    last = query("SELECT id FROM volumes WHERE edition_id=? AND number=34", (AOT_DE,))[0]["id"]
    assert client.put(f"/api/volumes/{last}/read").get_json()["reading_status"] == "finished"


def test_a_status_is_one_of_five_or_none(client):
    for value in ("planned", "reading", "paused", "dropped", "finished", ""):
        assert client.put(f"/api/series/{AOT}/reading", json={"status": value}).get_json() == {"reading_status": value}
    assert client.put(f"/api/series/{AOT}/reading", json={"status": "gelesen"}).status_code == 400
    assert client.put("/api/series/999/reading", json={"status": "reading"}).status_code == 404


def test_the_reading_overview_names_the_edition_read_and_the_next_volume(client):
    client.post("/api/collection", json={"volume_ids": [8, 9, 10]})
    client.post(f"/api/editions/{FRIEREN_DE}/read", json={"through": 1})
    client.put(f"/api/series/{AOT}/reading", json={"status": "planned"})
    answer = client.get("/api/reading").get_json()
    assert [item["series_id"] for item in answer["series"]] == [FRIEREN, AOT], "reading before planned"
    frieren = answer["series"][0]
    assert frieren["edition"]["id"] == FRIEREN_DE and frieren["edition"]["read"] == 1
    assert frieren["next"]["number_label"] == "2" and frieren["next"]["owned"] == 1
    assert frieren["unread_owned"] == 2 and frieren["editions"] == 2
    assert answer["counts"]["reading"] == 1 and answer["counts"]["planned"] == 1


def test_the_next_volume_is_never_one_that_is_not_out_yet(client):
    client.post(f"/api/editions/{FRIEREN_DE}/read", json={"through": 3})
    frieren = client.get("/api/reading").get_json()["series"][0]
    assert frieren["next"] is None, "volume 4 comes out in 2099"


def test_read_marks_are_per_account(client, admin):
    client.put("/api/volumes/1/read")
    assert admin.get("/api/volumes/1").get_json()["read"] is False
    assert admin.get("/api/reading").get_json()["series"] == []
