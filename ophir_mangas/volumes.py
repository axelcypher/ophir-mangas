"""Volumes: the flat grid of single volumes, the volume dialog, creating (one, the next, or a run of
numbers at once), correcting and deleting; the quick search and the forms' suggestions.

A new volume takes what its edition fixes (list price and currency) unless the form says otherwise
(docs/adr/0002). Variants share their number with the standard volume and differ in `variant`.
"""

from flask import jsonify, request

from . import search
from .catalog import (CURRENCIES, FORMATS, GENRES, LANGUAGES, FieldError, clean_volume_fields, edition_name, find_volume_duplicate, insert_row,
                      is_admin, normalize_isbn, number_label, split_list, update_row, volume_in_use)
from .config import now_iso
from .images import try_image
from .listing import (VOLUME_MODES, VOLUME_SORTS, Account, apply_filters, by_mode, edition_items, facets, sort_items, volume_items,
                      volume_order, volume_stats)
from .prices import parse_amount, price_history, record_price
from .web import app, db, login_required, user_id

RUN_LIMIT = 200


def volume_grid_answer(items, all_items, args, default_sort="title"):
    items = sort_items(apply_filters(items, args, kind="volume"), args.get("sort", default_sort), args.get("direction"), VOLUME_SORTS, default_sort)
    return {"volumes": items, "total": len(all_items), "shown": len(items), "facets": facets(all_items), "stats": volume_stats(all_items),
            "shown_stats": volume_stats(items)}


@app.get("/api/volumes")
@login_required
def list_volumes():
    """Every volume of the catalogue as a tile: `mode` (VOLUME_MODES), the value filters, `q`
    (also an ISBN), `sort`/`direction`."""
    connection = db()
    account = Account(connection, user_id())
    all_items = volume_items(connection, account)
    for item in all_items:
        item["reading_status"] = account.reading.get(item["series_id"], "")
    items = by_mode(all_items, request.args.get("mode", "all"), VOLUME_MODES)
    return jsonify(volume_grid_answer(items, all_items, request.args))


def volume_detail(volume_id, uid):
    connection = db()
    account = Account(connection, uid)
    found = volume_items(connection, account, "v.id=?", (volume_id,))
    if not found:
        return None
    volume = found[0]
    row = connection.execute("SELECT * FROM volumes WHERE id=?", (volume_id,)).fetchone()
    volume.update({key: row[key] for key in ("description", "source_url", "image_url", "updated_at")})
    from .config import jload
    volume["attributes"] = jload(row["attributes"], {}) or {}
    creator = connection.execute("SELECT display_name FROM users WHERE id=?", (row["created_by"],)).fetchone() if row["created_by"] else None
    volume["created_by_name"] = creator["display_name"] if creator else ""
    volume["can_delete"] = (is_admin(connection, uid) or row["created_by"] == uid) and not volume_in_use(connection, volume_id)
    volume["entries"] = [dict(entry) for entry in connection.execute(
        "SELECT * FROM collection_entries WHERE user_id=? AND volume_id=? ORDER BY purchased_at DESC, id DESC", (uid, volume_id))]
    from .preorders import preorder_rows
    volume["preorders"] = preorder_rows(uid, "p.volume_id=?", (volume_id,))
    volume["lists"] = [dict(entry) for entry in connection.execute(
        """SELECT w.id list_id, w.name, w.is_default, we.target_price, we.note, we.created_at FROM watchlist_entries we
           JOIN watchlists w ON w.id=we.list_id WHERE w.user_id=? AND we.volume_id=? ORDER BY w.is_default DESC, w.name""", (uid, volume_id))]
    volume["prices"] = price_history(volume_id)
    volume["owners"] = connection.execute("SELECT COUNT(DISTINCT user_id) FROM collection_entries WHERE volume_id=?", (volume_id,)).fetchone()[0]
    siblings = sorted(volume_items(connection, None, "v.edition_id=?", (volume["edition_id"],)), key=volume_order)
    position = next(index for index, item in enumerate(siblings) if item["id"] == volume_id)
    volume["previous_id"] = siblings[position - 1]["id"] if position > 0 else None
    volume["next_id"] = siblings[position + 1]["id"] if position + 1 < len(siblings) else None
    edition = edition_items(connection, account, "e.id=?", (volume["edition_id"],))[0]
    volume["edition"] = {key: edition[key] for key in ("id", "name", "series_id", "series_title", "publisher", "language", "format", "status",
                                                        "volume_count", "list_price", "currency", "collecting", "reading_status", "owned",
                                                        "total", "read")}
    return volume


@app.get("/api/volumes/<int:volume_id>")
@login_required
def get_volume(volume_id):
    volume = volume_detail(volume_id, user_id())
    if not volume:
        return jsonify({"error": "Band nicht gefunden."}), 404
    return jsonify(volume)


@app.get("/api/volumes/by-isbn/<isbn>")
@login_required
def volume_by_isbn(isbn):
    """The catalogue's volume with this ISBN (a scanned barcode), 404 when there is none."""
    try:
        isbn = normalize_isbn(isbn)
    except FieldError as error:
        return jsonify({"error": str(error)}), 400
    row = db().execute("SELECT id FROM volumes WHERE isbn=?", (isbn,)).fetchone() if isbn else None
    if not row:
        return jsonify({"error": "Kein Band mit dieser ISBN im Katalog.", "isbn": isbn}), 404
    return jsonify(volume_detail(row["id"], user_id()))


def edition_of(connection, payload):
    try:
        edition_id = int(payload.get("edition_id"))
    except (TypeError, ValueError):
        return None
    return connection.execute("SELECT * FROM editions WHERE id=?", (edition_id,)).fetchone()


def with_edition_defaults(fields, edition):
    """What the edition fixes, for whatever the form left out."""
    if fields.get("list_price") is None and "currency" not in fields and edition["list_price"] is not None:
        fields["list_price"] = edition["list_price"]
    fields.setdefault("currency", edition["currency"])
    return fields


def duplicate_answer(connection, duplicate):
    row = connection.execute(
        "SELECT v.number, v.title, e.title edition_title, e.label, s.title series_title FROM volumes v JOIN editions e ON e.id=v.edition_id "
        "JOIN series s ON s.id=e.series_id WHERE v.id=?", (duplicate[0],)).fetchone()
    name = f"{edition_name({'title': row['edition_title'], 'label': row['label']}, row['series_title'])} {number_label(row['number']) or row['title']}"
    return jsonify({"error": f"„{name.strip()}“ ist schon im Katalog ({duplicate[1]}).", "duplicate_id": duplicate[0]}), 409


def create_volume_row(connection, edition, fields, uid):
    stamp = now_iso()
    volume_id = insert_row(connection, "volumes", {**with_edition_defaults(fields, edition), "edition_id": edition["id"], "created_by": uid,
                                                   "created_at": stamp, "updated_at": stamp})
    return volume_id, try_image(connection, "volumes", volume_id, fields.get("image_url"))


@app.post("/api/volumes")
@login_required
def create_volume():
    payload = request.get_json(force=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Ungültige Anfrage."}), 400
    connection = db()
    edition = edition_of(connection, payload)
    if not edition:
        return jsonify({"error": "Die Ausgabe des Bands fehlt oder gibt es nicht."}), 400
    try:
        fields = clean_volume_fields(payload)
    except FieldError as error:
        return jsonify({"error": str(error)}), 400
    duplicate = find_volume_duplicate(connection, edition["id"], fields)
    if duplicate and not payload.get("force"):
        return duplicate_answer(connection, duplicate)
    market_value, error = parse_amount(payload.get("market_value"), "Marktwert")
    if error:
        return jsonify({"error": error}), 400
    uid = user_id()
    volume_id, image_error = create_volume_row(connection, edition, fields, uid)
    if market_value is not None:
        record_price(connection, volume_id, market_value, "manual", "", uid)
    connection.commit()
    return jsonify({**volume_detail(volume_id, uid), "image_error": image_error}), 201


@app.post("/api/editions/<int:edition_id>/volumes")
@login_required
def create_volume_run(edition_id):
    """Creates the numbered volumes `from`..`to` of an edition the catalogue does not have yet, with
    the edition's list price: a quick way to fill an edition before scanning or buying."""
    connection = db()
    edition = connection.execute("SELECT * FROM editions WHERE id=?", (edition_id,)).fetchone()
    if not edition:
        return jsonify({"error": "Ausgabe nicht gefunden."}), 404
    payload = request.get_json(force=True) or {}
    try:
        first, last = int(payload.get("from")), int(payload.get("to"))
    except (TypeError, ValueError):
        return jsonify({"error": "Von und bis bitte als ganze Zahlen."}), 400
    if not 0 <= first <= last or last - first >= RUN_LIMIT:
        return jsonify({"error": f"Höchstens {RUN_LIMIT} Bände auf einmal, von einer Zahl bis zu einer größeren."}), 400
    existing = {row[0] for row in connection.execute("SELECT number FROM volumes WHERE edition_id=? AND number IS NOT NULL", (edition_id,))}
    created = []
    for number in range(first, last + 1):
        if float(number) not in existing:
            created.append(create_volume_row(connection, edition, {"number": float(number)}, user_id())[0])
    connection.commit()
    return jsonify({"created": created}), 201


@app.patch("/api/volumes/<int:volume_id>")
@login_required
def update_volume(volume_id):
    connection = db()
    current = connection.execute("SELECT * FROM volumes WHERE id=?", (volume_id,)).fetchone()
    if not current:
        return jsonify({"error": "Band nicht gefunden."}), 404
    payload = request.get_json(force=True) or {}
    try:
        fields = clean_volume_fields(payload, partial=True)
    except FieldError as error:
        return jsonify({"error": str(error)}), 400
    if "edition_id" in payload:
        edition = edition_of(connection, payload)
        if not edition:
            return jsonify({"error": "Diese Ausgabe gibt es nicht."}), 400
        fields["edition_id"] = edition["id"]
    if not fields:
        return jsonify({"error": "Keine Änderungen übermittelt."}), 400
    merged = {**dict(current), **fields}
    if merged["number"] is None and not merged["title"]:
        return jsonify({"error": "Ein Band braucht eine Nummer, ein Sonderband einen Titel."}), 400
    duplicate = find_volume_duplicate(connection, merged["edition_id"], merged, exclude_id=volume_id)
    if duplicate and not payload.get("force"):
        return duplicate_answer(connection, duplicate)
    update_row(connection, "volumes", volume_id, fields, now_iso())
    image_error = None
    if "image_url" in fields and fields["image_url"] != current["image_url"]:
        connection.execute("UPDATE volumes SET image_key='' WHERE id=?", (volume_id,))
        image_error = try_image(connection, "volumes", volume_id, fields["image_url"])
    connection.commit()
    return jsonify({**volume_detail(volume_id, user_id()), "image_error": image_error})


@app.delete("/api/volumes/<int:volume_id>")
@login_required
def delete_volume(volume_id):
    connection = db()
    row = connection.execute("SELECT * FROM volumes WHERE id=?", (volume_id,)).fetchone()
    if not row:
        return jsonify({"error": "Band nicht gefunden."}), 404
    if volume_in_use(connection, volume_id):
        return jsonify({"error": "Der Band steht noch in einer Sammlung, Vorbestellung oder Wunschliste oder ist als gelesen markiert."}), 409
    if not (is_admin(connection, user_id()) or row["created_by"] == user_id()):
        return jsonify({"error": "Nur wer den Band angelegt hat oder ein Admin kann ihn löschen."}), 403
    connection.execute("DELETE FROM volumes WHERE id=?", (volume_id,))
    connection.commit()
    return jsonify({"deleted": True})


@app.get("/api/search")
@login_required
def global_search():
    """The quick search (Ctrl+K): the best-matching editions, and volumes for an ISBN or a number."""
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"editions": [], "volumes": []})
    limit = min(60, max(1, request.args.get("limit", 20, type=int)))
    connection = db()
    account = Account(connection, user_id())
    query = search.query(q)
    editions = [(query.score(search.edition_fields(item)), item) for item in edition_items(connection, account)]
    editions = [item for score, item in sorted(editions, key=lambda pair: (-pair[0], pair[1]["name"].lower())) if score > 0][:limit]
    volumes = []
    digits = "".join(char for char in q if char.isdigit() or char in "Xx")
    if len(digits) >= 10 or any(char.isdigit() for char in q):
        scored = [(query.score(search.volume_fields(item)), item) for item in volume_items(connection, account)]
        exact = [item for item in (item for _, item in scored) if digits and item["isbn"] and item["isbn"].endswith(digits[-10:])]
        volumes = exact or [item for score, item in sorted(scored, key=lambda pair: -pair[0]) if score > 0][:limit]
    return jsonify({"editions": editions, "volumes": volumes[:limit]})


@app.get("/api/catalog/suggestions")
@login_required
def suggestions():
    """Values for the forms' autocomplete: what the catalogue already uses, and the account's own
    shops and storage places."""
    uid, connection = user_id(), db()

    def distinct(table, column, limit=400):
        return [row[0] for row in connection.execute(
            f"SELECT {column} FROM {table} WHERE {column}!='' GROUP BY {column} ORDER BY COUNT(*) DESC, {column} LIMIT {limit}")]

    def listed(column):
        counts = {}
        for (value,) in connection.execute(f"SELECT {column} FROM series WHERE {column}!=''"):
            for part in split_list(value):
                counts[part] = counts.get(part, 0) + 1
        return sorted(counts, key=lambda name: (-counts[name], search.fold(name)))[:600]
    shops = [row[0] for row in connection.execute(
        """SELECT shop FROM (SELECT shop FROM collection_entries WHERE user_id=?1 UNION ALL SELECT shop FROM preorders WHERE user_id=?1)
           WHERE shop!='' GROUP BY shop ORDER BY COUNT(*) DESC LIMIT 100""", (uid,))]
    locations = [row[0] for row in connection.execute(
        "SELECT location FROM collection_entries WHERE user_id=? AND location!='' GROUP BY location ORDER BY COUNT(*) DESC LIMIT 100", (uid,))]
    return jsonify({
        "publisher": distinct("editions", "publisher"), "format": list(dict.fromkeys([*FORMATS, *distinct("editions", "format")])),
        "label": distinct("editions", "label"), "variant": distinct("volumes", "variant"),
        "author": listed("authors"), "genre": list(dict.fromkeys([*GENRES, *listed("genres")])),
        "shop": shops, "location": locations, "currencies": list(CURRENCIES), "languages": LANGUAGES,
    })
