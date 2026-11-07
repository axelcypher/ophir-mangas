"""Editions: the tiles of the catalogue and the collection, and the dialog behind each with its
volumes in order -- what the account owns, has read, misses and can expect.

"Sammle ich" (collected_editions) is the account's own statement that it collects an edition; only
those editions have gaps and appear in the release calendar. It is never set automatically.
"""

from flask import jsonify, request

from .catalog import (FieldError, clean_edition_fields, edition_in_use, find_edition_duplicate, insert_row, is_admin, number_label,
                      update_row)
from .config import now_iso
from .listing import (EDITION_MODES, EDITION_SORTS, Account, apply_filters, by_mode, edition_items, edition_stats, facets, grouped,
                      sort_items)
from .web import app, db, login_required, user_id

MAX_SLOTS = 600


def grid_answer(items, all_items, args, default_sort="title"):
    """The answer every edition grid gives: filtered, sorted, as editions or in groups."""
    items = sort_items(apply_filters(items, args), args.get("sort", default_sort), args.get("direction"), EDITION_SORTS, default_sort)
    answer = {"total": len(all_items), "shown": len(items), "facets": facets(all_items), "stats": edition_stats(all_items),
              "shown_stats": edition_stats(items)}
    return {**answer, **(grouped(args, items) or {"editions": items})}


@app.get("/api/editions")
@login_required
def list_editions():
    """The catalogue: every edition as a tile. `mode` (EDITION_MODES), the value filters, `reading`,
    `q`, `sort`/`direction`, and `group`/`group_sort`."""
    connection = db()
    all_items = edition_items(connection, Account(connection, user_id()))
    items = by_mode(all_items, request.args.get("mode", "all"), EDITION_MODES)
    return jsonify(grid_answer(items, all_items, request.args))


def slots_of(edition):
    """The edition's numbers in order, each with its volumes (standard first, then variants), and
    the numbers it should have but the catalogue lacks; special volumes after."""
    by_number = {}
    for volume in edition["volumes"]:
        if volume["number"] is not None:
            by_number.setdefault(volume["number"], []).append(volume["id"])
    top = min(MAX_SLOTS, max(edition["total"] or 0, edition["highest"], edition["released_through"]))
    numbers = sorted(set(range(1, top + 1)) | set(by_number))
    gaps = set(edition["gaps"])
    slots = [{"number": number, "number_label": number_label(number), "volumes": by_number.get(number, []),
              "released": number <= edition["released_through"] or any(volume["released"] for volume in edition["volumes"]
                                                                       if volume["number"] == number),
              "gap": number_label(number) in gaps} for number in numbers]
    specials = [volume["id"] for volume in edition["volumes"] if volume["number"] is None]
    return slots, specials


def edition_detail(edition_id, uid):
    connection = db()
    account = Account(connection, uid)
    found = edition_items(connection, account, "e.id=?", (edition_id,), with_volumes=True)
    if not found:
        return None
    edition = found[0]
    edition["slots"], edition["special_ids"] = slots_of(edition)
    row = connection.execute("SELECT created_by FROM editions WHERE id=?", (edition_id,)).fetchone()
    creator = connection.execute("SELECT display_name FROM users WHERE id=?", (row["created_by"],)).fetchone() if row["created_by"] else None
    edition["created_by_name"] = creator["display_name"] if creator else ""
    edition["can_delete"] = (is_admin(connection, uid) or row["created_by"] == uid) and not edition_in_use(connection, edition_id)
    series = connection.execute("SELECT * FROM series WHERE id=?", (edition["series_id"],)).fetchone()
    edition["series"] = {key: series[key] for key in ("id", "title", "original_title", "alt_titles", "authors", "genres", "demographic",
                                                         "status", "original_volumes", "start_year", "description", "source_url", "anilist_id")}
    edition["series"]["has_image"] = bool(series["image_key"] or series["image_url"])
    edition["series"]["image_version"] = (series["image_key"] or "")[:12]
    edition["other_editions"] = [{key: item[key] for key in ("id", "name", "publisher", "language", "format", "owned", "total", "cover")}
                                 for item in edition_items(connection, account, "e.series_id=? AND e.id!=?", (edition["series_id"], edition_id))]
    edition["lists"] = [dict(entry) for entry in connection.execute(
        """SELECT w.id list_id, w.name, w.is_default, we.note, we.created_at FROM watchlist_entries we
           JOIN watchlists w ON w.id=we.list_id WHERE w.user_id=? AND we.edition_id=? ORDER BY w.is_default DESC, w.name""", (uid, edition_id))]
    edition["owners"] = connection.execute(
        "SELECT COUNT(DISTINCT c.user_id) FROM collection_entries c JOIN volumes v ON v.id=c.volume_id WHERE v.edition_id=?", (edition_id,)).fetchone()[0]
    return edition


@app.get("/api/editions/<int:edition_id>")
@login_required
def get_edition(edition_id):
    edition = edition_detail(edition_id, user_id())
    if not edition:
        return jsonify({"error": "Ausgabe nicht gefunden."}), 404
    return jsonify(edition)


def series_id_of(payload):
    try:
        return int(payload.get("series_id"))
    except (TypeError, ValueError):
        return None


def create_edition_row(connection, series_id, fields, uid):
    stamp = now_iso()
    return insert_row(connection, "editions", {**fields, "series_id": series_id, "created_by": uid, "created_at": stamp, "updated_at": stamp})


@app.post("/api/editions")
@login_required
def create_edition():
    payload = request.get_json(force=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Ungültige Anfrage."}), 400
    connection = db()
    series_id = series_id_of(payload)
    if not series_id or not connection.execute("SELECT 1 FROM series WHERE id=?", (series_id,)).fetchone():
        return jsonify({"error": "Die Reihe der Ausgabe fehlt oder gibt es nicht."}), 400
    try:
        fields = clean_edition_fields(payload)
    except FieldError as error:
        return jsonify({"error": str(error)}), 400
    duplicate = find_edition_duplicate(connection, series_id, fields)
    if duplicate and not payload.get("force"):
        return jsonify({"error": f"Diese Ausgabe gibt es schon ({duplicate[1]}).", "duplicate_id": duplicate[0]}), 409
    edition_id = create_edition_row(connection, series_id, fields, user_id())
    if payload.get("collect"):
        connection.execute("INSERT OR IGNORE INTO collected_editions(user_id,edition_id,created_at) VALUES(?,?,?)", (user_id(), edition_id, now_iso()))
    connection.commit()
    return jsonify(edition_detail(edition_id, user_id())), 201


@app.patch("/api/editions/<int:edition_id>")
@login_required
def update_edition(edition_id):
    connection = db()
    current = connection.execute("SELECT * FROM editions WHERE id=?", (edition_id,)).fetchone()
    if not current:
        return jsonify({"error": "Ausgabe nicht gefunden."}), 404
    payload = request.get_json(force=True) or {}
    try:
        fields = clean_edition_fields(payload, partial=True)
    except FieldError as error:
        return jsonify({"error": str(error)}), 400
    if "series_id" in payload:
        series_id = series_id_of(payload)
        if not series_id or not connection.execute("SELECT 1 FROM series WHERE id=?", (series_id,)).fetchone():
            return jsonify({"error": "Diese Reihe gibt es nicht."}), 400
        fields["series_id"] = series_id
    if not fields:
        return jsonify({"error": "Keine Änderungen übermittelt."}), 400
    merged = {**dict(current), **fields}
    duplicate = find_edition_duplicate(connection, merged["series_id"], merged, exclude_id=edition_id)
    if duplicate and not payload.get("force"):
        return jsonify({"error": f"Diese Ausgabe gibt es schon ({duplicate[1]}).", "duplicate_id": duplicate[0]}), 409
    update_row(connection, "editions", edition_id, fields, now_iso())
    connection.commit()
    return jsonify(edition_detail(edition_id, user_id()))


@app.delete("/api/editions/<int:edition_id>")
@login_required
def delete_edition(edition_id):
    """With every volume of it; only while no account uses any of them, by its creator or an admin."""
    connection = db()
    row = connection.execute("SELECT * FROM editions WHERE id=?", (edition_id,)).fetchone()
    if not row:
        return jsonify({"error": "Ausgabe nicht gefunden."}), 404
    if edition_in_use(connection, edition_id):
        return jsonify({"error": "Die Ausgabe oder einer ihrer Bände wird noch verwendet (Sammlung, Wunschliste, Vorbestellung oder gelesen)."}), 409
    if not (is_admin(connection, user_id()) or row["created_by"] == user_id()):
        return jsonify({"error": "Nur wer die Ausgabe angelegt hat oder ein Admin kann sie löschen."}), 403
    connection.execute("DELETE FROM volumes WHERE edition_id=?", (edition_id,))
    connection.execute("DELETE FROM editions WHERE id=?", (edition_id,))
    connection.commit()
    return jsonify({"deleted": True})


@app.put("/api/editions/<int:edition_id>/collecting")
@login_required
def collect_edition(edition_id):
    connection = db()
    if not connection.execute("SELECT 1 FROM editions WHERE id=?", (edition_id,)).fetchone():
        return jsonify({"error": "Ausgabe nicht gefunden."}), 404
    connection.execute("INSERT OR IGNORE INTO collected_editions(user_id,edition_id,created_at) VALUES(?,?,?)", (user_id(), edition_id, now_iso()))
    connection.commit()
    return jsonify({"collecting": True})


@app.delete("/api/editions/<int:edition_id>/collecting")
@login_required
def stop_collecting_edition(edition_id):
    db().execute("DELETE FROM collected_editions WHERE user_id=? AND edition_id=?", (user_id(), edition_id))
    db().commit()
    return jsonify({"collecting": False})


@app.get("/api/editions/<int:edition_id>/next-volume")
@login_required
def next_volume(edition_id):
    """What the form for the edition's next volume starts with: the number after the highest, the
    edition's list price, and the previous volume's ISBN prefix is left to the user."""
    connection = db()
    edition = connection.execute("SELECT * FROM editions WHERE id=?", (edition_id,)).fetchone()
    if not edition:
        return jsonify({"error": "Ausgabe nicht gefunden."}), 404
    highest = connection.execute("SELECT MAX(number) FROM volumes WHERE edition_id=?", (edition_id,)).fetchone()[0]
    number = int(highest) + 1 if highest is not None else 1
    if request.args.get("number"):
        number = request.args.get("number")
    return jsonify({"edition_id": edition_id, "number": number_label(float(number)) if str(number).replace(".", "", 1).isdigit() else number,
                    "list_price": edition["list_price"], "currency": edition["currency"]})
