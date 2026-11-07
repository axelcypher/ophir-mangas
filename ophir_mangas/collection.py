"""An account's collection: its copies, each row a group of copies of one volume with the same
condition and purchase (price, date, shop), first printing, extras, where they are kept and notes.

The collection grid shows the editions the account has volumes of or collects (as the catalogue
does), or with `level=volumes` every owned volume, which also filters by storage place and
condition. A copy is worth its volume's market value, else what was paid, else the list price in
euros (prices.py).
"""

from flask import jsonify, request

from .catalog import normalize_date
from .config import now_iso
from .editions import grid_answer
from .listing import EDITION_MODES, VOLUME_MODES, Account, by_mode, edition_items, volume_items
from .prices import collection_value_sql, parse_amount
from .volumes import volume_grid_answer
from .web import app, db, login_required, user_id

CONDITIONS = {"new": "Neu/OVP", "very_good": "Sehr gut", "reading_marks": "Mit Lesespuren", "damaged": "Beschädigt"}
ENTRY_TEXT = {"shop": 120, "location": 120, "notes": 2000, "extras": 300}
QUANTITY_LIMIT = 999


def clean_entry_fields(payload, partial=False):
    """(fields, error) for a collection row from a request body."""
    fields = {}
    if "quantity" in payload or not partial:
        try:
            quantity = int(payload.get("quantity", 1))
        except (TypeError, ValueError):
            return None, "Die Anzahl ist keine Zahl."
        if not 1 <= quantity <= QUANTITY_LIMIT:
            return None, f"Die Anzahl muss zwischen 1 und {QUANTITY_LIMIT} liegen."
        fields["quantity"] = quantity
    if "condition" in payload or not partial:
        condition = payload.get("condition") or "new"
        if condition not in CONDITIONS:
            return None, "Unbekannter Zustand."
        fields["condition"] = condition
    if "first_printing" in payload:
        fields["first_printing"] = 1 if payload["first_printing"] in (True, 1, "1", "true", "on", "yes") else 0
    if "purchase_price" in payload:
        fields["purchase_price"], error = parse_amount(payload["purchase_price"], "Kaufpreis")
        if error:
            return None, error
    if "purchased_at" in payload:
        fields["purchased_at"], error = normalize_date(payload["purchased_at"], "Kaufdatum")
        if error:
            return None, error
    for key, limit in ENTRY_TEXT.items():
        if key in payload:
            fields[key] = str(payload[key] or "").strip()[:limit]
    return fields, None


def owned_volumes(connection, account):
    items = [item for item in volume_items(connection, account) if item["owned"]]
    for item in items:
        item["reading_status"] = account.reading.get(item["series_id"], "")
    return items


@app.get("/api/collection")
@login_required
def get_collection():
    """The editions the account has volumes of or collects (the catalogue's filters, modes and
    groups), or with level=volumes the owned volumes, also by `location` and `condition`."""
    args = request.args
    connection = db()
    account = Account(connection, user_id())
    if args.get("level") == "volumes":
        all_items = owned_volumes(connection, account)
        items = by_mode(all_items, args.get("mode", "all"), VOLUME_MODES)
        location = str(args.get("location") or "").strip()
        if location:
            items = [item for item in items if location in item.get("locations", [])]
        condition = str(args.get("condition") or "").strip()
        if condition:
            items = [item for item in items if condition in item.get("conditions", [])]
        answer = volume_grid_answer(items, all_items, args, default_sort="added")
        places = {}
        for item in all_items:
            for place in item.get("locations", []):
                places[place] = places.get(place, 0) + 1
        answer["facets"]["location"] = sorted(([place, count] for place, count in places.items()), key=lambda pair: (-pair[1], pair[0]))
        return jsonify({**answer, "conditions": CONDITIONS})
    all_items = [item for item in edition_items(connection, account) if item["owned"] or item["collecting"]]
    items = by_mode(all_items, args.get("mode", "all"), EDITION_MODES)
    return jsonify({**grid_answer(items, all_items, args, default_sort="title"), "conditions": CONDITIONS})


def entry_row(entry_id, uid):
    row = db().execute("SELECT * FROM collection_entries WHERE id=? AND user_id=?", (entry_id, uid)).fetchone()
    return dict(row) if row else None


def insert_entry(connection, uid, volume_id, fields):
    stamp = now_iso()
    columns = ["user_id", "volume_id", "created_at", "updated_at", *fields]
    return connection.execute(f"INSERT INTO collection_entries({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                              (uid, volume_id, stamp, stamp, *fields.values())).lastrowid


@app.post("/api/collection")
@login_required
def add_collection_entry():
    """{volume_id, quantity, condition, first_printing, extras, purchase_price, purchased_at, shop,
    location, notes}; `volume_ids` instead adds the same to each (a run bought at once)."""
    payload = request.get_json(force=True) or {}
    uid, connection = user_id(), db()
    fields, error = clean_entry_fields(payload)
    if error:
        return jsonify({"error": error}), 400
    raw_ids = payload.get("volume_ids") if isinstance(payload.get("volume_ids"), list) else [payload.get("volume_id")]
    try:
        volume_ids = list(dict.fromkeys(int(value) for value in raw_ids))
    except (TypeError, ValueError):
        return jsonify({"error": "Kein Band angegeben."}), 400
    if not volume_ids or len(volume_ids) > 500:
        return jsonify({"error": "Kein Band angegeben."}), 400
    found = {row[0] for row in connection.execute(f"SELECT id FROM volumes WHERE id IN ({','.join('?' for _ in volume_ids)})", volume_ids)}
    if found != set(volume_ids):
        return jsonify({"error": "Band nicht gefunden."}), 404
    entry_ids = [insert_entry(connection, uid, volume_id, fields) for volume_id in volume_ids]
    connection.commit()
    if "volume_ids" in payload:
        return jsonify({"created": entry_ids}), 201
    return jsonify(entry_row(entry_ids[0], uid)), 201


@app.patch("/api/collection/<int:entry_id>")
@login_required
def update_collection_entry(entry_id):
    uid = user_id()
    if not entry_row(entry_id, uid):
        return jsonify({"error": "Eintrag nicht gefunden."}), 404
    fields, error = clean_entry_fields(request.get_json(force=True) or {}, partial=True)
    if error:
        return jsonify({"error": error}), 400
    if not fields:
        return jsonify({"error": "Keine Änderungen übermittelt."}), 400
    db().execute(f"UPDATE collection_entries SET {','.join(f'{key}=?' for key in fields)}, updated_at=? WHERE id=? AND user_id=?",
                 (*fields.values(), now_iso(), entry_id, uid))
    db().commit()
    return jsonify(entry_row(entry_id, uid))


@app.delete("/api/collection/<int:entry_id>")
@login_required
def delete_collection_entry(entry_id):
    """Removes the row and returns it, so the client can offer to put it back (POST it again)."""
    uid = user_id()
    entry = entry_row(entry_id, uid)
    if not entry:
        return jsonify({"error": "Eintrag nicht gefunden."}), 404
    db().execute("DELETE FROM collection_entries WHERE id=? AND user_id=?", (entry_id, uid))
    db().commit()
    return jsonify({"deleted": entry})


def dashboard_collection(uid):
    """Totals, the reading pile and the latest additions for the dashboard."""
    connection = db()
    totals = connection.execute(
        f"""SELECT COUNT(DISTINCT c.volume_id) volumes, COALESCE(SUM(c.quantity),0) copies, COUNT(DISTINCT v.edition_id) editions,
              COALESCE(SUM(c.quantity*COALESCE(c.purchase_price,0)),0) spent, COALESCE(SUM({collection_value_sql()}),0) value
            FROM collection_entries c JOIN volumes v ON v.id=c.volume_id WHERE c.user_id=?""", (uid,)).fetchone()
    unread = connection.execute(
        """SELECT COUNT(DISTINCT c.volume_id) FROM collection_entries c
           WHERE c.user_id=?1 AND NOT EXISTS(SELECT 1 FROM volume_reads r WHERE r.user_id=?1 AND r.volume_id=c.volume_id)""", (uid,)).fetchone()[0]
    read = connection.execute("SELECT COUNT(*) FROM volume_reads WHERE user_id=?", (uid,)).fetchone()[0]
    account = Account(connection, uid)
    recent_ids = [row[0] for row in connection.execute(
        "SELECT volume_id FROM collection_entries WHERE user_id=? GROUP BY volume_id ORDER BY MAX(created_at) DESC, MAX(id) DESC LIMIT 12", (uid,))]
    recent = []
    if recent_ids:
        by_id = {item["id"]: item for item in volume_items(connection, account, f"v.id IN ({','.join('?' for _ in recent_ids)})", recent_ids)}
        recent = [by_id[volume_id] for volume_id in recent_ids if volume_id in by_id]
    by_language = [dict(row) for row in connection.execute(
        """SELECT e.language, SUM(c.quantity) copies FROM collection_entries c JOIN volumes v ON v.id=c.volume_id
           JOIN editions e ON e.id=v.edition_id WHERE c.user_id=? GROUP BY e.language ORDER BY copies DESC""", (uid,))]
    return {"volumes": totals["volumes"], "copies": totals["copies"], "editions": totals["editions"], "spent": round(totals["spent"], 2),
            "value": round(totals["value"], 2), "unread": unread, "read": read, "recent": recent, "by_language": by_language}
