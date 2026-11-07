"""The public profile: what visitors see, and what they never see."""
import io

from conftest import AOT_DE, FRIEREN, SPY_DE, default_list, login, own, png_bytes


def share(client, **settings):
    response = client.put("/api/account/public-profile", json={"enabled": True, "slug": "alex", **settings})
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def test_the_profile_shows_owned_editions_without_prices_or_private_data(client, anonymous):
    own(client, 1, purchase_price=7, shop="Thalia", location="Regal", notes="geheim")
    own(client, 6)
    client.post("/api/volumes/6/prices", json={"amount": 40})
    settings = share(client, name="Alex' Mangas")
    assert settings["url"] == "http://localhost/u/alex"
    data = anonymous.get("/api/public/alex").get_json()
    assert data["name"] == "Alex' Mangas" and data["stats"] == {"editions": 1, "series": 1, "volumes": 2}
    edition = data["collection"][0]
    assert edition["id"] == AOT_DE and [volume["number_label"] for volume in edition["volumes"]] == ["1", "5"]
    text = str(data)
    for secret in ("Thalia", "Regal", "geheim", "40", "purchase", "value", "price", "read_at"):
        assert secret not in text, secret
    assert "read" not in edition and "read" not in edition["volumes"][0], "reading only when shared"
    assert "wishlist" not in data


def test_wishlist_and_reading_are_shown_only_when_shared(client, anonymous):
    own(client, 8)
    client.put("/api/volumes/8/read")
    client.post(f"/api/watchlists/{default_list(client)}/editions", json={"edition_id": SPY_DE})
    share(client, show_wishlist=True, show_reading=True)
    data = anonymous.get("/api/public/alex").get_json()
    assert [item["id"] for item in data["wishlist"]] == [SPY_DE] and data["wishlist"][0]["volumes"] == []
    frieren = data["collection"][0]
    assert frieren["reading_status"] == "reading" and frieren["volumes"][0]["read"] is True and data["stats"]["read"] == 1


def test_an_off_or_unknown_profile_is_the_same_404(client, anonymous):
    own(client, 1)
    share(client)
    client.put("/api/account/public-profile", json={"enabled": False})
    assert anonymous.get("/api/public/alex").status_code == 404
    assert anonymous.get("/api/public/nobody").status_code == 404
    assert anonymous.get("/u/alex").status_code == 404


def test_addresses_are_checked_and_unique(client, admin):
    assert client.put("/api/account/public-profile", json={"enabled": True}).status_code == 400
    for slug in ("ab", "-alex", "Alex!", "a" * 40):
        assert client.put("/api/account/public-profile", json={"slug": slug}).status_code == 400, slug
    share(client)
    assert admin.put("/api/account/public-profile", json={"slug": "alex"}).status_code == 400


def test_only_shown_pictures_are_served_to_visitors(client, anonymous):
    own(client, 1)
    client.post("/api/volumes/1/image", data={"file": (io.BytesIO(png_bytes()), "c.png")}, content_type="multipart/form-data")
    client.post("/api/volumes/2/image", data={"file": (io.BytesIO(png_bytes((1, 1, 1))), "c.png")}, content_type="multipart/form-data")
    client.post(f"/api/series/{FRIEREN}/image", data={"file": (io.BytesIO(png_bytes((9, 9, 9))), "c.png")}, content_type="multipart/form-data")
    share(client)
    assert anonymous.get("/u/alex/images/volumes/1").mimetype == "image/webp"
    assert anonymous.get("/u/alex/images/volumes/2").status_code == 404, "not owned"
    assert anonymous.get(f"/u/alex/images/series/{FRIEREN}").status_code == 404
    assert anonymous.get("/u/nobody/images/volumes/1").status_code == 404


def test_the_page_renders_for_visitors(client, anonymous):
    own(client, 1)
    share(client, theme="dark")
    page = anonymous.get("/u/alex").get_data(as_text=True)
    assert "Ophir Mangas" in page and 'data-theme="dark"' in page or "dark" in page
    assert login(None).get("/u/alex").status_code == 200
