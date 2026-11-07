"""A public, shareable view of an account's collection: /u/<slug>, readable without signing in.

The account switches it on in Settings and decides whether the wishlist and the reading status
are shown too. A visitor sees the editions of the collection with the volumes owned, covers and
catalogue facts -- no prices or values, no purchase data, conditions, storage places, notes or
preorders, nothing else of the app. Everything public goes through this module, so what leaves the
server is decided here (public_edition, public_volume); a profile that is off or unknown is a 404,
the same answer either way.

The setting lives in user_settings under PROFILE_KEY and is only written through
/api/account/public-profile, which checks the address (slug) and keeps it unique.
"""
import json
import os
import re

from flask import Response, jsonify, render_template, request

from .config import jload
from .listing import EDITION_SORTS, Account, edition_items, sort_items
from .web import app, db, login_required, user_id

PROFILE_KEY = "publicProfile"
THEMES = ("auto", "light", "dark")   # auto: as the visitor's system asks
SLUG = re.compile(r"[a-z0-9](?:[a-z0-9-]{1,30}[a-z0-9])")
NAME_LIMIT = 60
# Where profiles are shared from, e.g. https://mangas.example.org (with the path the app is served
# under, if any: https://example.org/mangas) -- the app itself may run under a private address.
# Without it the link uses the address the settings were opened on.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_PROFILE_URL", "").strip().rstrip("/")
EDITION_FIELDS = ("id", "series_id", "name", "series_title", "original_title", "authors", "genres", "demographic", "publisher", "language", "format",
                  "status", "total", "owned", "latest_release")
VOLUME_FIELDS = ("id", "number_label", "title", "variant", "release_date", "has_image", "image_version")


def load_profile(connection, uid):
    row = connection.execute("SELECT value FROM user_settings WHERE user_id=? AND key=?", (uid, PROFILE_KEY)).fetchone()
    stored = jload(row["value"], {}) if row else {}
    stored = stored if isinstance(stored, dict) else {}
    return {"enabled": bool(stored.get("enabled")), "slug": str(stored.get("slug") or ""), "name": str(stored.get("name") or ""),
            "show_wishlist": bool(stored.get("show_wishlist")), "show_reading": bool(stored.get("show_reading")),
            "theme": stored.get("theme") if stored.get("theme") in THEMES else "auto"}


def profile_url(slug):
    return f"{PUBLIC_BASE_URL or request.url_root.rstrip('/')}/u/{slug}" if slug else ""


def public_owner(slug):
    """(user id, profile, display name) of the switched-on profile at this address, else None."""
    row = db().execute(
        "SELECT s.user_id,u.display_name FROM user_settings s JOIN users u ON u.id=s.user_id WHERE s.key=? AND json_extract(s.value,'$.slug')=?",
        (PROFILE_KEY, slug.lower())).fetchone()
    if not row:
        return None
    profile = load_profile(db(), row["user_id"])
    if not profile["enabled"]:
        return None
    return row["user_id"], profile, profile["name"] or row["display_name"]


def not_found():
    return jsonify({"error": "Dieses Profil gibt es nicht oder es ist nicht öffentlich."}), 404


def public_volume(volume, profile):
    """What a visitor may see of a volume: catalogue facts, whether it is owned (and read)."""
    shown = {key: volume.get(key) for key in VOLUME_FIELDS}
    shown["owned"] = bool(volume.get("owned"))
    if profile["show_reading"]:
        shown["read"] = bool(volume.get("read"))
    return shown


def public_edition(edition, profile, volumes="owned"):
    """What a visitor may see of an edition: catalogue facts, the cover, how many volumes are
    owned, and the owned volumes themselves (`volumes`: "owned" or "none")."""
    shown = {key: edition.get(key) for key in EDITION_FIELDS}
    shown["cover"] = edition["cover"]
    shown["volumes"] = [public_volume(volume, profile) for volume in edition.get("volumes", []) if volumes == "owned" and volume["owned"]]
    if profile["show_reading"]:
        shown["reading_status"] = edition.get("reading_status") or ""
        shown["read"] = edition.get("read", 0)
    return shown


def shared_editions(uid, profile):
    """(owned editions, wished editions) as list items with their volumes."""
    connection = db()
    items = edition_items(connection, Account(connection, uid), with_volumes=True)
    owned = [item for item in items if item["owned"]]
    wished = [item for item in items if item["wished"] and not item["owned"]] if profile["show_wishlist"] else []
    return owned, wished


def shared_image(uid, profile, table, entry_id):
    """Whether the picture is one the profile shows: an owned volume, the cover of a shown edition,
    or the series picture (a placeholder, if it has none) of a shown edition without a cover."""
    owned, wished = shared_editions(uid, profile)
    for edition in owned + wished:
        cover = edition["cover"]
        if cover and cover["kind"] == table and cover["id"] == entry_id:
            return True
        if not cover and table == "series" and edition["series_id"] == entry_id:
            return True
        if table == "volumes" and edition in owned and any(volume["id"] == entry_id and volume["owned"] for volume in edition["volumes"]):
            return True
    return False


# ---- The owner's setting ------------------------------------------------------------------------

@app.get("/api/account/public-profile")
@login_required
def get_public_profile():
    profile = load_profile(db(), user_id())
    return jsonify({**profile, "url": profile_url(profile["slug"])})


@app.put("/api/account/public-profile")
@login_required
def save_public_profile():
    uid, payload = user_id(), request.get_json(force=True) or {}
    profile = load_profile(db(), uid)
    if "slug" in payload:
        slug = str(payload["slug"] or "").strip().lower()
        if slug and not SLUG.fullmatch(slug):
            return jsonify({"error": "Die Adresse darf nur Kleinbuchstaben, Ziffern und Bindestriche enthalten (3 bis 32 Zeichen, kein Bindestrich am Anfang oder Ende)."}), 400
        taken = db().execute("SELECT 1 FROM user_settings WHERE key=? AND user_id!=? AND json_extract(value,'$.slug')=?", (PROFILE_KEY, uid, slug)).fetchone()
        if slug and taken:
            return jsonify({"error": "Diese Adresse ist schon vergeben."}), 400
        profile["slug"] = slug
    if "name" in payload:
        profile["name"] = str(payload["name"] or "").strip()[:NAME_LIMIT]
    for key in ("show_wishlist", "show_reading"):
        if key in payload:
            profile[key] = bool(payload[key])
    if payload.get("theme") in THEMES:
        profile["theme"] = payload["theme"]
    if "enabled" in payload:
        profile["enabled"] = bool(payload["enabled"])
    if profile["enabled"] and not profile["slug"]:
        return jsonify({"error": "Wähle eine Adresse für dein Profil."}), 400
    db().execute("INSERT INTO user_settings(user_id,key,value) VALUES(?,?,?) ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value",
                 (uid, PROFILE_KEY, json.dumps(profile)))
    db().commit()
    return jsonify({**profile, "url": profile_url(profile["slug"])})


# ---- What visitors see --------------------------------------------------------------------------

@app.get("/u/<slug>")
def public_profile_page(slug):
    owner = public_owner(slug)
    if not owner:
        return render_template("public.html", slug=slug, name="", missing=True, theme="auto"), 404
    return render_template("public.html", slug=slug.lower(), name=owner[2], missing=False, theme=owner[1]["theme"])


@app.get("/api/public/<slug>")
def public_profile_data(slug):
    owner = public_owner(slug)
    if not owner:
        return not_found()
    uid, profile, name = owner
    owned, wished = shared_editions(uid, profile)
    owned = sort_items(owned, request.args.get("sort", "title"), None, EDITION_SORTS, "title")
    result = {"name": name, "slug": profile["slug"], "collection": [public_edition(item, profile) for item in owned],
              "stats": {"editions": len(owned), "series": len({item["series_id"] for item in owned}),
                        "volumes": sum(item["owned"] for item in owned)},
              "facets": {"language": sorted({item["language"] for item in owned}),
                         "publisher": sorted({item["publisher"] for item in owned if item["publisher"]})},
              "show_reading": profile["show_reading"]}
    if profile["show_reading"]:
        result["stats"]["read"] = sum(item["read"] for item in owned)
    if profile["show_wishlist"]:
        result["wishlist"] = [public_edition(item, profile, volumes="none") for item in sort_items(wished, "title", None, EDITION_SORTS, "title")]
    return jsonify(result)


@app.get("/u/<slug>/images/<any(series, volumes):table>/<int:entry_id>")
def public_image(slug, table, entry_id):
    from .images import serve_image
    owner = public_owner(slug)
    if not owner or not shared_image(owner[0], owner[1], table, entry_id):
        return Response(status=404)
    return serve_image(table, entry_id, "full" if request.args.get("size") == "full" else "thumb")
