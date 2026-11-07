"""Market values with their history, and pictures of volumes and series: upload, download, thumbnails, caching."""
import io

import pytest

from conftest import AOT, avif_bytes, own, picture_bytes, png_bytes, query

MIKU, FRIEREN, REM, MIKASA = 5, 8, 12, 13   # volumes: Attack on Titan 5, Frieren 1, Spy x Family 1 and 2


def test_market_values_are_a_shared_history(client, admin):
    assert client.post(f"/api/volumes/{MIKU}/prices", json={"amount": "199,00", "note": "eBay"}).status_code == 201
    history = admin.post(f"/api/volumes/{MIKU}/prices", json={"amount": 215}).get_json()
    assert [(row["amount"], row["author"]) for row in history] == [(215, "Ophir Mangas Admin"), (199, "Alex Morgan")]
    assert client.get(f"/api/volumes/{MIKU}").get_json()["market_value"] == 215
    newest = history[0]["id"]
    assert client.delete(f"/api/volumes/{MIKU}/prices/{newest}").get_json()[0]["amount"] == 199
    assert client.delete(f"/api/volumes/{FRIEREN}/prices/{history[1]['id']}").status_code == 404, "the value belongs to another volume"


def test_a_market_value_needs_a_sensible_amount(client):
    for amount in ("", "abc", -1, 5_000_000):
        assert client.post(f"/api/volumes/{MIKU}/prices", json={"amount": amount}).status_code == 400, amount
    assert client.post("/api/volumes/999/prices", json={"amount": 5}).status_code == 404


def upload(client, volume_id, payload, name="bild.png"):
    return client.post(f"/api/volumes/{volume_id}/image", data={"file": (io.BytesIO(payload), name)}, content_type="multipart/form-data")


def test_an_uploaded_picture_is_served_with_a_thumbnail(client):
    key = upload(client, MIKU, png_bytes(size=(1200, 1600))).get_json()["image_key"]
    full = client.get(f"/images/volumes/{MIKU}?v={key[:12]}")
    assert full.mimetype == "image/png" and "immutable" in full.headers["Cache-Control"]
    thumb = client.get(f"/images/volumes/{MIKU}/thumb")
    from PIL import Image
    image = Image.open(io.BytesIO(thumb.data))
    assert thumb.mimetype == "image/webp" and image.width == 480
    assert "immutable" not in thumb.headers.get("Cache-Control", ""), "only a URL with the picture's version is kept for good"


def test_the_same_picture_is_stored_once(client):
    payload = png_bytes()
    assert upload(client, MIKU, payload).get_json()["image_key"] == upload(client, FRIEREN, payload).get_json()["image_key"]
    from ophir_mangas.config import IMAGE_DIR
    assert len([path for path in IMAGE_DIR.iterdir() if path.name.startswith(query("SELECT image_key k FROM volumes WHERE id=?", (MIKU,))[0]["k"][:12])]) == 1


def test_a_picture_link_is_fetched_on_first_view_and_a_dead_one_not_again_at_once(client, fake_fetch):
    query("UPDATE volumes SET image_url='https://cdn.example.com/miku.png' WHERE id=?", (MIKU,))
    query("UPDATE volumes SET image_url='https://cdn.example.com/dead.png' WHERE id=?", (FRIEREN,))
    fake_fetch.pages["https://cdn.example.com/miku.png"] = ("image/png", png_bytes())
    assert client.get(f"/images/volumes/{MIKU}/thumb").mimetype == "image/webp"
    assert query("SELECT image_key FROM volumes WHERE id=?", (MIKU,))[0]["image_key"].endswith(".png")
    for _ in range(3):
        assert client.get(f"/images/volumes/{FRIEREN}").mimetype == "image/svg+xml"
    assert fake_fetch.requested.count("https://cdn.example.com/dead.png") == 1


def test_a_picture_can_be_set_by_link_and_removed(client, fake_fetch):
    fake_fetch.pages["https://cdn.example.com/rem.png"] = ("image/png", png_bytes((10, 10, 200)))
    assert client.post(f"/api/volumes/{MIKU}/image", json={"url": "https://cdn.example.com/rem.png"}).status_code == 200
    assert client.post(f"/api/volumes/{MIKU}/image", json={"url": "https://cdn.example.com/missing.png"}).status_code == 400
    assert client.delete(f"/api/volumes/{MIKU}/image").get_json() == {"removed": True}
    assert client.get(f"/api/volumes/{MIKU}").get_json()["has_image"] is False


def test_a_new_picture_link_on_save_is_fetched_and_a_failure_reported(client, fake_fetch):
    response = client.patch(f"/api/volumes/{MIKU}", json={"image_url": "https://cdn.example.com/kaputt.png"}).get_json()
    assert "404" in response["image_error"] and response["has_image"] is True, "the link is kept to be tried again later"


def test_an_uploaded_avif_is_kept_as_it_is_and_gets_a_webp_thumbnail(client):
    payload = avif_bytes(size=(960, 1280))
    response = upload(client, MIKU, payload, "bild.avif")
    assert response.status_code == 200
    key = response.get_json()["image_key"]
    from ophir_mangas.config import IMAGE_DIR
    assert key.endswith(".avif") and (IMAGE_DIR / key).read_bytes() == payload, "the original is stored, not converted"
    full = client.get(f"/images/volumes/{MIKU}?v={key[:12]}")
    assert full.mimetype == "image/avif" and full.data == payload
    thumb = client.get(f"/images/volumes/{MIKU}/thumb")
    from PIL import Image
    image = Image.open(io.BytesIO(thumb.data))
    assert thumb.mimetype == "image/webp" and image.format == "WEBP" and image.size == (480, 640)


def test_an_avif_link_is_downloaded_by_hand_on_save_and_on_first_view(client, fake_fetch):
    for name in ("rem", "frieren", "mikasa"):
        fake_fetch.pages[f"https://cdn.example.com/{name}.avif"] = ("image/avif", avif_bytes())
    assert client.post(f"/api/volumes/{REM}/image", json={"url": "https://cdn.example.com/rem.avif"}).get_json()["image_key"].endswith(".avif")
    saved = client.patch(f"/api/volumes/{FRIEREN}", json={"image_url": "https://cdn.example.com/frieren.avif"}).get_json()
    assert saved["image_error"] is None and saved["image_version"]
    query("UPDATE volumes SET image_url='https://cdn.example.com/mikasa.avif' WHERE id=?", (MIKASA,))
    for volume_id in (REM, FRIEREN, MIKASA):
        assert client.get(f"/images/volumes/{volume_id}").mimetype == "image/avif", volume_id
        assert client.get(f"/images/volumes/{volume_id}/thumb").mimetype == "image/webp", volume_id


@pytest.mark.parametrize("payload, name", [(b"%PDF-1.7 no picture", "bild.pdf"), (picture_bytes("BMP"), "bild.bmp")], ids=["unreadable", "bmp"])
def test_anything_else_is_refused_with_the_formats_that_work(client, payload, name):
    response = upload(client, MIKU, payload, name)
    assert response.status_code == 400 and "AVIF" in response.get_json()["error"]


def test_a_series_has_a_picture_of_its_own_that_covers_its_editions_without_one(client):
    response = client.post(f"/api/series/{AOT}/image", data={"file": (io.BytesIO(png_bytes()), "reihe.png")}, content_type="multipart/form-data")
    assert response.status_code == 200
    assert client.get(f"/images/series/{AOT}").mimetype == "image/png"
    japanese = next(item for item in client.get("/api/editions").get_json()["editions"] if item["id"] == 2)
    assert japanese["cover"]["kind"] == "series", "an edition without volume covers shows the series' picture"
    upload(client, 7, png_bytes((1, 2, 3)))
    japanese = next(item for item in client.get("/api/editions").get_json()["editions"] if item["id"] == 2)
    assert japanese["cover"] == {"kind": "volumes", "id": 7, "version": japanese["cover"]["version"]}


def test_a_copy_is_worth_its_market_value_else_what_it_cost_else_its_list_price(client):
    own(client, 1)                              # list price 7.50 EUR
    own(client, 2, purchase_price="4,00")
    own(client, 3, purchase_price=5)
    client.post("/api/volumes/3/prices", json={"amount": 30})
    own(client, 7)                              # 429 JPY: no value in euros
    stats = client.get("/api/collection").get_json()["stats"]
    assert stats["value"] == 7.5 + 4 + 30 and stats["spent"] == 9
