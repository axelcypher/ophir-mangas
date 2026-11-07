"""Series: the works of the catalogue. Listing for the forms' pickers, details with every edition,
creating, correcting and deleting.

A series can be deleted by whoever created it or an admin while no account uses it or anything of
it (reading status, copies, wishes, preorders, read marks); its editions and volumes go with it.
"""

from flask import jsonify, request

from .catalog import FieldError, clean_series_fields, find_series_duplicate, image_fields, insert_row, is_admin, series_in_use, update_row
from .config import jload, now_iso
from .images import try_image
from .listing import Account, edition_items, edition_stats
from .web import app, db, login_required, user_id

SERIES_COLUMNS = ("id", "title", "original_title", "alt_titles", "authors", "genres", "demographic", "status", "original_volumes",
                  "start_year", "description", "source_url", "image_url", "anilist_id", "created_at", "updated_at")


def series_row(connection, series_id):
    return connection.execute("SELECT * FROM series WHERE id=?", (series_id,)).fetchone()


def can_delete_series(connection, row, uid):
    return (is_admin(connection, uid) or row["created_by"] == uid) and not series_in_use(connection, row["id"])


def series_detail(series_id, uid):
    connection = db()
    row = series_row(connection, series_id)
    if not row:
        return None
    account = Account(connection, uid)
    series = {key: row[key] for key in SERIES_COLUMNS}
    series.update(image_fields(row))
    series["attributes"] = jload(row["attributes"], {}) or {}
    creator = connection.execute("SELECT display_name FROM users WHERE id=?", (row["created_by"],)).fetchone() if row["created_by"] else None
    series["created_by_name"] = creator["display_name"] if creator else ""
    series["editions"] = sorted(edition_items(connection, account, "e.series_id=?", (series_id,)),
                                key=lambda item: (-item["owned"], item["language"] != "de", item["name"].lower(), item["id"]))
    series["stats"] = edition_stats(series["editions"])
    series["reading_status"] = account.reading.get(series_id, "")
    series["can_delete"] = can_delete_series(connection, row, uid)
    return series


@app.get("/api/series")
@login_required
def list_series():
    """Every series, briefly, for the pickers of the forms (newest first when there is no query)."""
    from . import search
    rows = db().execute(
        """SELECT s.id,s.title,s.original_title,s.alt_titles,s.authors,s.image_key,s.image_url,s.created_at,
                  (SELECT COUNT(*) FROM editions e WHERE e.series_id=s.id) editions
           FROM series s""").fetchall()
    items = [{**{key: row[key] for key in ("id", "title", "original_title", "alt_titles", "authors", "editions", "created_at")}, **image_fields(row)}
             for row in rows]
    query = request.args.get("q", "").strip()
    if query:
        scored = [(search.query(query).score([(item["title"], search.NAME), (item["original_title"], search.NAME),
                                              (item["alt_titles"], search.NUMBER), (item["authors"], search.SET)]), item) for item in items]
        items = [item for score, item in sorted(scored, key=lambda pair: -pair[0]) if score > 0]
    else:
        items.sort(key=lambda item: search.fold(item["title"]))
    return jsonify(items[:min(500, request.args.get("limit", 500, type=int))])


@app.get("/api/series/<int:series_id>")
@login_required
def get_series(series_id):
    series = series_detail(series_id, user_id())
    if not series:
        return jsonify({"error": "Reihe nicht gefunden."}), 404
    return jsonify(series)


def duplicate_answer(duplicate):
    return jsonify({"error": f"„{duplicate[1]}“ ist schon im Katalog ({duplicate[2]}).", "duplicate_id": duplicate[0]}), 409


def create_series_row(connection, fields, uid):
    """Inserts a series (fields already clean) and fetches its picture; (id, image error)."""
    stamp = now_iso()
    series_id = insert_row(connection, "series", {**fields, "created_by": uid, "created_at": stamp, "updated_at": stamp})
    return series_id, try_image(connection, "series", series_id, fields.get("image_url"))


@app.post("/api/series")
@login_required
def create_series():
    payload = request.get_json(force=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Ungültige Anfrage."}), 400
    try:
        fields = clean_series_fields(payload)
    except FieldError as error:
        return jsonify({"error": str(error)}), 400
    connection = db()
    duplicate = find_series_duplicate(connection, fields)
    if duplicate and not payload.get("force"):
        return duplicate_answer(duplicate)
    series_id, image_error = create_series_row(connection, fields, user_id())
    connection.commit()
    return jsonify({**series_detail(series_id, user_id()), "image_error": image_error}), 201


@app.patch("/api/series/<int:series_id>")
@login_required
def update_series(series_id):
    connection = db()
    current = series_row(connection, series_id)
    if not current:
        return jsonify({"error": "Reihe nicht gefunden."}), 404
    payload = request.get_json(force=True) or {}
    try:
        fields = clean_series_fields(payload, partial=True)
    except FieldError as error:
        return jsonify({"error": str(error)}), 400
    if not fields:
        return jsonify({"error": "Keine Änderungen übermittelt."}), 400
    duplicate = find_series_duplicate(connection, {**dict(current), **fields}, exclude_id=series_id)
    if duplicate and not payload.get("force"):
        return duplicate_answer(duplicate)
    update_row(connection, "series", series_id, fields, now_iso())
    image_error = None
    if "image_url" in fields and fields["image_url"] != current["image_url"]:
        connection.execute("UPDATE series SET image_key='' WHERE id=?", (series_id,))
        image_error = try_image(connection, "series", series_id, fields["image_url"])
    connection.commit()
    return jsonify({**series_detail(series_id, user_id()), "image_error": image_error})


def delete_series_rows(connection, series_id):
    for (edition_id,) in connection.execute("SELECT id FROM editions WHERE series_id=?", (series_id,)).fetchall():
        connection.execute("DELETE FROM volumes WHERE edition_id=?", (edition_id,))
    connection.execute("DELETE FROM editions WHERE series_id=?", (series_id,))
    connection.execute("DELETE FROM series WHERE id=?", (series_id,))


@app.delete("/api/series/<int:series_id>")
@login_required
def delete_series(series_id):
    connection = db()
    row = series_row(connection, series_id)
    if not row:
        return jsonify({"error": "Reihe nicht gefunden."}), 404
    if series_in_use(connection, series_id):
        return jsonify({"error": "Die Reihe oder einer ihrer Bände wird noch verwendet (Sammlung, Lesestatus, Wunschliste oder Vorbestellung)."}), 409
    if not can_delete_series(connection, row, user_id()):
        return jsonify({"error": "Nur wer die Reihe angelegt hat oder ein Admin kann sie löschen."}), 403
    delete_series_rows(connection, series_id)
    connection.commit()
    return jsonify({"deleted": True})
