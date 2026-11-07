"""Admin: duplicates at every level of the catalogue, merging them, deleting unused entries."""
from conftest import AOT, AOT_DE, AOT_JA, FRIEREN_DE, default_list, login, own, query


def make_duplicates(client):
    """A second Attack on Titan (series), a second Carlsen edition under it, and a volume 1 twice."""
    series = client.post("/api/series", json={"title": "Attack on Titan", "force": True}).get_json()["id"]
    edition = client.post("/api/editions", json={"series_id": series, "publisher": "Carlsen", "language": "de", "format": "Taschenbuch"}).get_json()["id"]
    volume = client.post("/api/volumes", json={"edition_id": edition, "number": 1}).get_json()["id"]
    return series, edition, volume


def test_the_overview_finds_duplicates_at_every_level(admin):
    series, edition, _ = make_duplicates(admin)
    twin = admin.post("/api/volumes", json={"edition_id": AOT_DE, "number": 2, "variant": "x", "force": True}).get_json()["id"]
    admin.patch(f"/api/volumes/{twin}", json={"variant": ""})   # now 2 twice in one edition... refused as a duplicate
    overview = admin.get("/api/admin/catalog").get_json()
    assert [AOT, series] in overview["duplicates"]["series"]
    assert overview["duplicates"]["editions"] == [], "editions of different series are not duplicates"
    assert any(set(group) == {2, twin} for group in overview["duplicates"]["volumes"]) is False
    assert series not in overview["unused"]["series"] and edition in [row["id"] for row in overview["editions"]]


def test_merging_series_moves_editions_and_merges_the_same_edition(admin, client):
    series, edition, volume = make_duplicates(admin)
    own(client, volume, purchase_price=3)
    client.put(f"/api/series/{series}/reading", json={"status": "reading"})
    client.put(f"/api/series/{AOT}/reading", json={"status": "planned"})
    client.put(f"/api/editions/{edition}/collecting")
    assert admin.post("/api/admin/catalog/merge", json={"kind": "series", "source": series, "target": AOT}).get_json() == {"merged": True}
    assert query("SELECT COUNT(*) n FROM series WHERE id=?", (series,))[0]["n"] == 0
    assert query("SELECT COUNT(*) n FROM editions WHERE id=?", (edition,))[0]["n"] == 0, "the same Carlsen edition was merged"
    assert query("SELECT volume_id FROM collection_entries") == [{"volume_id": 1}], "its volume 1 became the catalogue's volume 1"
    assert query("SELECT status FROM series_reading") == [{"status": "planned"}], "the target's status stays"
    assert query("SELECT edition_id FROM collected_editions") == [{"edition_id": AOT_DE}]


def test_merging_volumes_keeps_one_wish_and_one_read_mark(admin, client):
    list_id = default_list(client)
    for volume_id in (5, 6):
        client.post(f"/api/watchlists/{list_id}/volumes", json={"volume_id": volume_id})
        client.put(f"/api/volumes/{volume_id}/read")
    own(client, 6)
    client.post("/api/volumes/6/prices", json={"amount": 20})
    admin.post("/api/admin/catalog/merge", json={"kind": "volumes", "source": 6, "target": 5})
    assert query("SELECT volume_id FROM watchlist_entries") == [{"volume_id": 5}]
    assert query("SELECT volume_id FROM volume_reads") == [{"volume_id": 5}]
    assert query("SELECT volume_id FROM collection_entries") == [{"volume_id": 5}]
    assert query("SELECT volume_id FROM price_observations") == [{"volume_id": 5}]


def test_merging_editions_moves_volumes_the_target_lacks(admin):
    admin.post("/api/admin/catalog/merge", json={"kind": "editions", "source": AOT_JA, "target": AOT_DE})
    assert query("SELECT COUNT(*) n FROM volumes WHERE edition_id=?", (AOT_DE,))[0]["n"] == 6, "the Japanese volume 1 merged into 1"


def test_merge_input_is_checked(admin, client):
    assert admin.post("/api/admin/catalog/merge", json={"kind": "figures", "source": 1, "target": 2}).status_code == 400
    assert admin.post("/api/admin/catalog/merge", json={"kind": "volumes", "source": 1, "target": 1}).status_code == 400
    assert admin.post("/api/admin/catalog/merge", json={"kind": "volumes", "source": 1, "target": 999}).status_code == 404
    assert client.post("/api/admin/catalog/merge", json={"kind": "volumes", "source": 6, "target": 5}).status_code == 403


def test_only_unused_entries_are_deleted_by_an_admin(admin, client):
    own(client, 8)
    assert admin.delete(f"/api/admin/catalog/editions/{FRIEREN_DE}").status_code == 409
    assert admin.delete(f"/api/admin/catalog/editions/{AOT_JA}").get_json() == {"deleted": True}
    assert query("SELECT COUNT(*) n FROM volumes WHERE edition_id=?", (AOT_JA,))[0]["n"] == 0
    assert admin.delete("/api/admin/catalog/series/3").get_json() == {"deleted": True}
    assert admin.delete("/api/admin/catalog/volumes/999").status_code == 404
    assert login(("demo", "mangas-1234")).delete("/api/admin/catalog/volumes/1").status_code == 403
