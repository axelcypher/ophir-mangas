"""Preorders: volumes ordered before their release, from order to arrival.

A preorder has a shop, an order date, a price (plus shipping and fees) and what has been paid of
it so far, the release date the shop expects, a status and a tracking number. Release dates move: every
change of the expected release is logged (preorder_events), so a preorder shows how often it was
postponed.

The status books the collection: when a preorder arrives ("delivered") its copies are added to
the collection as new, with the order's price per copy, date and shop; moving it back to an
earlier status takes those rows out again. Deleting a preorder keeps what it booked.
"""

from flask import jsonify, request

from .config import now_iso, today_iso
from .catalog import edition_name, number_label, normalize_date
from .prices import parse_amount
from .web import app, db, login_required, user_id

STATUSES = {"ordered": "Bestellt", "paid": "Bezahlt", "shipped": "Versendet", "delivered": "Angekommen", "cancelled": "Storniert"}
OPEN_STATUSES = ("ordered", "paid", "shipped")
TEXT = {"shop": 120, "order_number": 80, "tracking": 120, "notes": 2000}


def total_of(row):
    if row["price"] is None and row["shipping"] is None:
        return None
    return round((row["price"] or 0) + (row["shipping"] or 0), 2)


def delays_of(events):
    """How often the expected release moved to a later month."""
    return sum(1 for event in events if event["kind"] == "release" and event["old_value"] and event["new_value"]
               and event["new_value"][:7] > event["old_value"][:7])


def preorder_rows(uid, where="1=1", params=()):
    rows = [dict(row) for row in db().execute(
        f"""SELECT p.*, v.number, v.title volume_title, v.variant, v.isbn, v.release_date volume_release, v.image_key, v.image_url,
              v.edition_id, e.title edition_title, e.label, e.publisher, e.language, e.series_id, s.title series_title
            FROM preorders p JOIN volumes v ON v.id=p.volume_id JOIN editions e ON e.id=v.edition_id JOIN series s ON s.id=e.series_id
            WHERE p.user_id=? AND {where}
            ORDER BY CASE WHEN p.status IN ('ordered','paid','shipped') THEN 0 ELSE 1 END,
              COALESCE(NULLIF(p.expected_release,''),'9999'), p.id""", (uid, *params))]
    if not rows:
        return rows
    events = {}
    placeholders = ",".join("?" for _ in rows)
    for event in db().execute(f"SELECT * FROM preorder_events WHERE preorder_id IN ({placeholders}) ORDER BY id", [row["id"] for row in rows]):
        events.setdefault(event["preorder_id"], []).append(dict(event))
    booked = {}
    for entry in db().execute(f"SELECT id,preorder_id FROM collection_entries WHERE preorder_id IN ({placeholders})", [row["id"] for row in rows]):
        booked.setdefault(entry["preorder_id"], []).append(entry["id"])
    for row in rows:
        row["number_label"] = number_label(row["number"])
        row["edition_name"] = edition_name({"title": row.pop("edition_title"), "label": row.pop("label")}, row["series_title"])
        row["has_image"] = bool(row["image_key"] or row["image_url"])
        row["image_version"] = (row.pop("image_key") or "")[:12]
        row.pop("image_url")
        row["total"] = total_of(row)
        row["outstanding"] = max(0.0, round((row["total"] or 0) - (row["paid"] or 0), 2)) if row["status"] in OPEN_STATUSES else 0.0
        row["events"] = events.get(row["id"], [])
        row["delays"] = delays_of(row["events"])
        row["booked_entry_ids"] = booked.get(row["id"], [])
    return rows


def preorder_stats(rows):
    open_rows = [row for row in rows if row["status"] in OPEN_STATUSES]
    this_month = today_iso()[:7]
    upcoming = sorted({row["expected_release"][:7] for row in open_rows if row["expected_release"]})
    return {
        "open": len(open_rows),
        "open_copies": sum(row["quantity"] for row in open_rows),
        "outstanding": round(sum(row["outstanding"] for row in open_rows), 2),
        "open_total": round(sum(row["total"] or 0 for row in open_rows), 2),
        "paid": round(sum(row["paid"] or 0 for row in open_rows), 2),
        "due_this_month": sum(1 for row in open_rows if row["expected_release"][:7] == this_month),
        "overdue": sum(1 for row in open_rows if row["expected_release"] and row["expected_release"][:7] < this_month),
        "next_month": next((month for month in upcoming if month >= this_month), upcoming[-1] if upcoming else ""),
        "delivered": sum(1 for row in rows if row["status"] == "delivered"),
        "cancelled": sum(1 for row in rows if row["status"] == "cancelled"),
        "postponed": sum(1 for row in open_rows if row["delays"]),
    }


@app.get("/api/preorders")
@login_required
def list_preorders():
    rows = preorder_rows(user_id())
    stats = preorder_stats(rows)
    status = request.args.get("status", "open")
    if status == "open":
        rows = [row for row in rows if row["status"] in OPEN_STATUSES]
    elif status in STATUSES:
        rows = [row for row in rows if row["status"] == status]
    return jsonify({"preorders": rows, "stats": stats, "statuses": STATUSES})


def clean_preorder_fields(payload, partial=False):
    fields = {}
    if "status" in payload or not partial:
        status = payload.get("status") or "ordered"
        if status not in STATUSES:
            return None, "Unbekannter Status."
        fields["status"] = status
    if "quantity" in payload or not partial:
        try:
            quantity = int(payload.get("quantity", 1))
        except (TypeError, ValueError):
            return None, "Die Anzahl ist keine Zahl."
        if not 1 <= quantity <= 99:
            return None, "Die Anzahl muss zwischen 1 und 99 liegen."
        fields["quantity"] = quantity
    for key, label in (("price", "Preis"), ("shipping", "Versand"), ("paid", "Bezahlt")):
        if key in payload:
            fields[key], error = parse_amount(payload[key], label)
            if error:
                return None, error
            if key == "paid" and fields[key] is None:
                fields[key] = 0
    for key, label in (("ordered_at", "Bestelldatum"), ("expected_release", "Erscheinungstermin"), ("delivered_at", "Ankunftsdatum")):
        if key in payload:
            fields[key], error = normalize_date(payload[key], label)
            if error:
                return None, error
    if fields.get("delivered_at") == "":
        fields["delivered_at"] = None
    for key, limit in TEXT.items():
        if key in payload:
            fields[key] = str(payload[key] or "").strip()[:limit]
    return fields, None


def book_delivery(connection, preorder, uid):
    """The arrived copies go into the collection, once per preorder."""
    if connection.execute("SELECT 1 FROM collection_entries WHERE preorder_id=?", (preorder["id"],)).fetchone():
        return
    total = total_of(preorder)
    price = round(total / preorder["quantity"], 2) if total is not None else None
    note = " ".join(part for part in ("Vorbestellung", preorder["order_number"]) if part)
    stamp = now_iso()
    connection.execute(
        """INSERT INTO collection_entries(user_id,volume_id,quantity,condition,first_printing,purchase_price,purchased_at,shop,notes,preorder_id,created_at,updated_at)
           VALUES(?,?,?,?,1,?,?,?,?,?,?,?)""",
        (uid, preorder["volume_id"], preorder["quantity"], "new", price, preorder["ordered_at"] or (preorder["delivered_at"] or today_iso()),
         preorder["shop"], note, preorder["id"], stamp, stamp),
    )


def unbook_delivery(connection, preorder_id):
    connection.execute("DELETE FROM collection_entries WHERE preorder_id=?", (preorder_id,))


def log_event(connection, preorder_id, kind, old="", new=""):
    connection.execute("INSERT INTO preorder_events(preorder_id,kind,old_value,new_value,created_at) VALUES(?,?,?,?,?)",
                       (preorder_id, kind, "" if old is None else str(old), "" if new is None else str(new), now_iso()))


def apply_status_side_effects(connection, preorder, old_status, uid):
    """Paid in full when marked paid; booked into the collection on arrival, unbooked when that is
    taken back."""
    if preorder["status"] == "paid" and old_status != "paid":
        total = total_of(preorder)
        if total is not None and (preorder["paid"] or 0) < total:
            connection.execute("UPDATE preorders SET paid=? WHERE id=?", (total, preorder["id"]))
            log_event(connection, preorder["id"], "paid", preorder["paid"], total)
    if preorder["status"] == "delivered" and old_status != "delivered":
        if not preorder["delivered_at"]:
            connection.execute("UPDATE preorders SET delivered_at=? WHERE id=?", (today_iso(), preorder["id"]))
        book_delivery(connection, get_row(connection, preorder["id"], uid), uid)
    if old_status == "delivered" and preorder["status"] != "delivered":
        connection.execute("UPDATE preorders SET delivered_at=NULL WHERE id=?", (preorder["id"],))
        unbook_delivery(connection, preorder["id"])


def get_row(connection, preorder_id, uid):
    return connection.execute("SELECT * FROM preorders WHERE id=? AND user_id=?", (preorder_id, uid)).fetchone()


@app.post("/api/preorders")
@login_required
def create_preorder():
    payload = request.get_json(force=True) or {}
    uid, connection = user_id(), db()
    try:
        volume_id = int(payload.get("volume_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Kein Band angegeben."}), 400
    volume = connection.execute("SELECT id,release_date,list_price,currency FROM volumes WHERE id=?", (volume_id,)).fetchone()
    if not volume:
        return jsonify({"error": "Band nicht gefunden."}), 404
    fields, error = clean_preorder_fields(payload)
    if error:
        return jsonify({"error": error}), 400
    fields.setdefault("expected_release", volume["release_date"])
    fields.setdefault("ordered_at", today_iso())
    if "price" not in fields and volume["currency"] == "EUR" and volume["list_price"] is not None:
        fields["price"] = round(volume["list_price"] * fields["quantity"], 2)
    stamp = now_iso()
    columns = ["user_id", "volume_id", "created_at", "updated_at", *fields]
    cursor = connection.execute(f"INSERT INTO preorders({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                                (uid, volume_id, stamp, stamp, *fields.values()))
    preorder_id = cursor.lastrowid
    log_event(connection, preorder_id, "created", "", fields["status"])
    apply_status_side_effects(connection, get_row(connection, preorder_id, uid), "ordered" if fields["status"] != "ordered" else "", uid)
    if payload.get("remove_from_wishlists"):
        connection.execute("DELETE FROM watchlist_entries WHERE volume_id=? AND list_id IN (SELECT id FROM watchlists WHERE user_id=?)", (volume_id, uid))
    connection.commit()
    return jsonify(preorder_rows(uid, "p.id=?", (preorder_id,))[0]), 201


@app.patch("/api/preorders/<int:preorder_id>")
@login_required
def update_preorder(preorder_id):
    uid, connection = user_id(), db()
    current = get_row(connection, preorder_id, uid)
    if not current:
        return jsonify({"error": "Vorbestellung nicht gefunden."}), 404
    fields, error = clean_preorder_fields(request.get_json(force=True) or {}, partial=True)
    if error:
        return jsonify({"error": error}), 400
    if not fields:
        return jsonify({"error": "Keine Änderungen übermittelt."}), 400
    connection.execute(f"UPDATE preorders SET {','.join(f'{key}=?' for key in fields)}, updated_at=? WHERE id=?",
                       (*fields.values(), now_iso(), preorder_id))
    for key, kind in (("status", "status"), ("expected_release", "release"), ("paid", "paid")):
        if key in fields and fields[key] != current[key]:
            log_event(connection, preorder_id, kind, current[key], fields[key])
    updated = get_row(connection, preorder_id, uid)
    if current["status"] != updated["status"]:
        apply_status_side_effects(connection, updated, current["status"], uid)
    elif updated["status"] == "delivered" and any(key in fields for key in ("quantity", "price", "shipping", "shop", "ordered_at")):
        # What was booked follows corrections of the arrived order.
        unbook_delivery(connection, preorder_id)
        book_delivery(connection, get_row(connection, preorder_id, uid), uid)
    connection.commit()
    return jsonify(preorder_rows(uid, "p.id=?", (preorder_id,))[0])


@app.delete("/api/preorders/<int:preorder_id>")
@login_required
def delete_preorder(preorder_id):
    uid, connection = user_id(), db()
    if not get_row(connection, preorder_id, uid):
        return jsonify({"error": "Vorbestellung nicht gefunden."}), 404
    # Copies it booked stay in the collection; their preorder_id becomes NULL (ON DELETE SET NULL).
    connection.execute("DELETE FROM preorders WHERE id=? AND user_id=?", (preorder_id, uid))
    connection.commit()
    return jsonify({"deleted": True})


def dashboard_preorders(uid):
    rows = preorder_rows(uid)
    open_rows = [row for row in rows if row["status"] in OPEN_STATUSES]
    return {"stats": preorder_stats(rows), "upcoming": open_rows[:8]}
