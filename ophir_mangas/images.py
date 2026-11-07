"""Covers of volumes and pictures of series: downloaded from the link an entry names, or uploaded;
thumbnails made from them.

Every picture is stored once under the SHA-256 of its bytes (image_key = "<hash>.<ext>" in the
series and volumes tables) in IMAGE_DIR; thumbnails are WebP files in THUMB_DIR made on first use.
An entry with an image_url but no image_key yet has its picture fetched on first view; a failed
fetch is not tried again for MISS_RETRY_SECONDS, so a grid of entries with dead links does not
hang on every visit.

Which pictures are taken is up to Pillow: what it opens as one of FORMATS. AVIF needs a Pillow
built with libavif; the wheels of the pinned version have it.
"""

import hashlib
import io
import os
import time

from flask import Response, jsonify, request, send_file
from PIL import Image, ImageOps, UnidentifiedImageError

from .config import IMAGE_DIR, THUMB_DIR, now_iso
from .fetch import FetchError, fetch
from .web import app, db, login_required

MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 60_000_000
THUMB_WIDTH = 480
MISS_RETRY_SECONDS = 600
FORMATS = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp"), "GIF": ("gif", "image/gif"),
           "AVIF": ("avif", "image/avif")}
FORMAT_NAMES = "JPEG, PNG, WebP, GIF oder AVIF"
MIME_OF_EXTENSION = {extension: mime for extension, mime in FORMATS.values()}
_misses = {}

# An entry without a picture: a small closed book in a grey that reads on the light and the dark
# appearance, on a transparent ground (the tile's own surface shows through), in the middle of the
# frame, so cropping it into a wider one (a group's mosaic) keeps it whole.
PLACEHOLDER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="300" height="430" viewBox="0 0 300 430">
<g fill="none" stroke="#8c8679" stroke-opacity=".5" stroke-width="11" stroke-linecap="round" stroke-linejoin="round" transform="translate(150 215) scale(.55) translate(-150 -215)">
<path d="M78 70h134a12 12 0 0 1 12 12v278H90a12 12 0 0 1-12-12z"/><path d="M78 348a12 12 0 0 1 12-12h134"/><path d="M112 70v266"/><path d="M140 128h56M140 158h40"/></g></svg>"""
# Which tables have pictures, by the word in their addresses.
TABLES = {"series": "series", "volumes": "volumes"}
NOT_FOUND = {"series": "Reihe nicht gefunden.", "volumes": "Band nicht gefunden."}


class ImageError(Exception):
    pass


def store_image(payload):
    """Checks that the bytes are a picture and stores them; returns the image key."""
    if len(payload) > MAX_IMAGE_BYTES:
        raise ImageError("Das Bild ist größer als 15 MB.")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image_format = image.format
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError, ValueError):
        raise ImageError(f"Die Datei ist kein lesbares Bild ({FORMAT_NAMES}).")
    if image_format not in FORMATS:
        raise ImageError(f"Bilder bitte als {FORMAT_NAMES}.")
    key = f"{hashlib.sha256(payload).hexdigest()}.{FORMATS[image_format][0]}"
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    target = IMAGE_DIR / key
    if not target.exists():
        temporary = target.with_name(f"{key}.{os.getpid()}.tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, target)
    return key


def download_image(url):
    """Fetches a picture from a link and stores it; returns the image key. Raises ImageError."""
    try:
        _, _, payload = fetch(url, MAX_IMAGE_BYTES, accept="image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8")
    except FetchError as error:
        raise ImageError(str(error))
    return store_image(payload)


def ensure_image(connection, table, entry):
    """The entry's image key, fetching its image_url first if that has not happened yet."""
    if entry["image_key"] and (IMAGE_DIR / entry["image_key"]).exists():
        return entry["image_key"]
    url = entry["image_url"]
    if not url:
        return None
    if time.time() - _misses.get(url, 0) < MISS_RETRY_SECONDS:
        return None
    try:
        key = download_image(url)
    except ImageError:
        _misses[url] = time.time()
        return None
    connection.execute(f"UPDATE {TABLES[table]} SET image_key=? WHERE id=?", (key, entry["id"]))
    connection.commit()
    return key


def thumbnail_path(key):
    target = THUMB_DIR / f"{key.rsplit('.', 1)[0]}-{THUMB_WIDTH}.webp"
    if target.exists():
        return target
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    with Image.open(IMAGE_DIR / key) as image:
        image = ImageOps.exif_transpose(image)
        image.thumbnail((THUMB_WIDTH, THUMB_WIDTH * 2))
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "transparency" in image.info or image.mode in ("LA", "P") else "RGB")
        buffer = io.BytesIO()
        image.save(buffer, "WEBP", quality=82, method=4)
    temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    temporary.write_bytes(buffer.getvalue())
    os.replace(temporary, target)
    return target


def placeholder():
    response = Response(PLACEHOLDER_SVG, mimetype="image/svg+xml")
    response.cache_control.max_age = 300
    return response


def serve_image(table, entry_id, size):
    """The picture of a series or volume (`table` as in TABLES), its thumbnail with size "thumb";
    the placeholder without one."""
    entry = db().execute(f"SELECT id,image_key,image_url FROM {TABLES[table]} WHERE id=?", (entry_id,)).fetchone()
    if not entry:
        return Response(status=404)
    key = ensure_image(db(), table, entry)
    if not key:
        return placeholder()
    try:
        path = thumbnail_path(key) if size == "thumb" else IMAGE_DIR / key
    except (OSError, Image.DecompressionBombError):
        return placeholder()
    mimetype = "image/webp" if size == "thumb" else MIME_OF_EXTENSION.get(key.rsplit(".", 1)[-1], "application/octet-stream")
    response = send_file(path, mimetype=mimetype, conditional=True, etag=True, max_age=0)
    # The URL carries the key (?v=), so a changed picture is a new URL: kept for a year.
    if request.args.get("v") == key[:12]:
        response.cache_control.public = True
        response.cache_control.max_age = 31_536_000
        response.cache_control.immutable = True
    return response


@app.get("/images/<any(series, volumes):table>/<int:entry_id>")
@login_required
def entry_image(table, entry_id):
    return serve_image(table, entry_id, "full")


@app.get("/images/<any(series, volumes):table>/<int:entry_id>/thumb")
@login_required
def entry_thumbnail(table, entry_id):
    return serve_image(table, entry_id, "thumb")


@app.post("/api/<any(series, volumes):table>/<int:entry_id>/image")
@login_required
def upload_entry_image(table, entry_id):
    if not db().execute(f"SELECT 1 FROM {TABLES[table]} WHERE id=?", (entry_id,)).fetchone():
        return jsonify({"error": NOT_FOUND[table]}), 404
    file = request.files.get("file")
    try:
        if file and file.filename:
            key = store_image(file.read(MAX_IMAGE_BYTES + 1))
        else:
            url = str((request.get_json(silent=True) or {}).get("url") or "").strip()
            if not url:
                return jsonify({"error": "Kein Bild übermittelt."}), 400
            key = download_image(url)
            db().execute(f"UPDATE {TABLES[table]} SET image_url=? WHERE id=?", (url, entry_id))
    except ImageError as error:
        return jsonify({"error": str(error)}), 400
    db().execute(f"UPDATE {TABLES[table]} SET image_key=?, updated_at=? WHERE id=?", (key, now_iso(), entry_id))
    db().commit()
    return jsonify({"image_key": key, "image_version": key[:12]})


@app.delete("/api/<any(series, volumes):table>/<int:entry_id>/image")
@login_required
def remove_entry_image(table, entry_id):
    if not db().execute(f"UPDATE {TABLES[table]} SET image_key='', image_url='', updated_at=? WHERE id=?", (now_iso(), entry_id)).rowcount:
        return jsonify({"error": NOT_FOUND[table]}), 404
    db().commit()
    return jsonify({"removed": True})


def try_image(connection, table, entry_id, url):
    """Fetches the picture of a newly given image link; a failure is reported (German), not fatal."""
    if not url:
        return None
    try:
        key = download_image(url)
    except ImageError as error:
        return str(error)
    connection.execute(f"UPDATE {TABLES[table]} SET image_key=? WHERE id=?", (key, entry_id))
    return None
