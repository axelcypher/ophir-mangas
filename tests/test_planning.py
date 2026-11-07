"""Collecting an edition by hand, its gaps, and the release calendar."""
import pytest

from conftest import AOT_DE, FRIEREN_DE, SPY_DE, default_list, own, query

import ophir_mangas


@pytest.fixture
def today(monkeypatch):
    """Sets the date the app thinks it is (listing and planning ask config.today_iso)."""
    def set_today(value):
        for module in (ophir_mangas.listing, ophir_mangas.planning, ophir_mangas.reading):
            monkeypatch.setattr(module, "today_iso", lambda: value)
    return set_today


def test_collecting_is_only_ever_set_by_hand(client):
    own(client, 8)
    assert client.get(f"/api/editions/{FRIEREN_DE}").get_json()["collecting"] is False, "a first volume does not make it collected"
    assert client.get("/api/gaps").get_json()["editions"] == []
    assert client.put(f"/api/editions/{FRIEREN_DE}/collecting").get_json() == {"collecting": True}
    assert client.get(f"/api/editions/{FRIEREN_DE}").get_json()["collecting"] is True
    assert client.delete(f"/api/editions/{FRIEREN_DE}/collecting").get_json() == {"collecting": False}
    assert client.put("/api/editions/999/collecting").status_code == 404


def test_a_gap_is_a_released_number_owned_in_no_variant(client):
    own(client, 1)
    own(client, 6)            # Limited Edition of 5
    client.put(f"/api/editions/{AOT_DE}/collecting")
    gaps = client.get("/api/gaps").get_json()
    edition = gaps["editions"][0]
    assert edition["id"] == AOT_DE and edition["gap_count"] == 32, "2-4 and 6-34 of a completed edition of 34"
    assert [gap["number_label"] for gap in edition["gaps"][:4]] == ["2", "3", "4", "6"]
    assert edition["gaps"][0]["volume"]["id"] == 2 and edition["gaps"][3]["volume"] is None, "6 is not in the catalogue"
    assert gaps["stats"] == {"editions": 1, "gaps": 32, "uncatalogued": 29, "estimate": 7.5 * 32}


def test_an_ongoing_edition_has_gaps_only_up_to_its_latest_release(client):
    own(client, 9)
    client.put(f"/api/editions/{FRIEREN_DE}/collecting")
    edition = client.get("/api/gaps").get_json()["editions"][0]
    assert [gap["number_label"] for gap in edition["gaps"]] == ["1", "3"], "4 is not out yet"


def test_a_special_volume_is_never_a_gap(client):
    own(client, 12)
    own(client, 13)
    client.put(f"/api/editions/{SPY_DE}/collecting")
    assert client.get("/api/gaps").get_json()["editions"] == []
    spy = client.get(f"/api/editions/{SPY_DE}").get_json()
    assert spy["special_ids"] == [14] and spy["owned"] == 2


def test_the_collection_grid_filters_by_gaps_and_completeness(client):
    own(client, 12)
    own(client, 13)
    own(client, 8)
    client.put(f"/api/editions/{SPY_DE}/collecting")
    client.put(f"/api/editions/{FRIEREN_DE}/collecting")
    ids = lambda mode: [item["id"] for item in client.get(f"/api/collection?mode={mode}").get_json()["editions"]]
    assert ids("gaps") == [FRIEREN_DE]
    assert ids("collecting") == [FRIEREN_DE, SPY_DE]


def test_the_calendar_lists_coming_volumes_of_collected_and_wished_editions(client, today):
    today("2099-01-15")
    client.put(f"/api/editions/{FRIEREN_DE}/collecting")
    calendar = client.get("/api/calendar").get_json()
    assert [month["month"] for month in calendar["months"]] == ["2099-02"]
    volume = calendar["months"][0]["volumes"][0]
    assert volume["id"] == 11 and volume["collecting"] is True and volume["released"] is False


def test_the_calendar_shows_what_came_out_lately_and_is_not_owned(client, today):
    today("2022-03-20")
    client.post(f"/api/watchlists/{default_list(client)}/volumes", json={"volume_id": 9})
    calendar = client.get("/api/calendar").get_json()
    assert [item["id"] for item in calendar["recent"]] == [9], "wished, out on 2022-03-01, not owned"
    assert calendar["months"] == [], "volume 3 (May) is neither wished nor of a collected edition"
    own(client, 9)
    assert client.get("/api/calendar").get_json()["recent"] == []


def test_without_anything_collected_or_wished_the_calendar_is_empty(client):
    assert client.get("/api/calendar").get_json() == {"months": [], "recent": [], "undated": 0}


def test_the_dashboard_sums_up_reading_planning_and_the_collection(client, today):
    today("2099-01-15")
    own(client, 8, purchase_price=7)
    own(client, 9)
    client.put("/api/volumes/8/read")
    client.put(f"/api/editions/{FRIEREN_DE}/collecting")
    dashboard = client.get("/api/dashboard").get_json()
    assert dashboard["collection"]["volumes"] == 2 and dashboard["collection"]["unread"] == 1 and dashboard["collection"]["read"] == 1
    assert dashboard["planning"]["gaps"] == 1 and [item["id"] for item in dashboard["planning"]["upcoming"]] == [11]
    assert dashboard["reading"][0]["series_id"] == 2 and dashboard["reading"][0]["next"]["number_label"] == "2"
    assert query("SELECT COUNT(*) n FROM collected_editions")[0]["n"] == 1
