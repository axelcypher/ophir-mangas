"""Reading: read marks on volumes and each account's reading status per series.

A read mark belongs to a volume and does not depend on owning it (borrowed, from the library).
The reading status belongs to the series, the story, whichever edition it is read in: planned,
reading, paused, dropped, finished. Two things follow from read marks, and only these: the first
read volume of a series that is planned (or has no status) makes it "reading", and reading the last
volume of a completed edition makes a series that is being read "finished". Everything else is the
account's own choice.
"""

from flask import jsonify, request

from .catalog import number_label
from .config import now_iso, today_iso
from .listing import Account, edition_items, volume_order
from .web import app, db, login_required, user_id

READING_STATUSES = {"reading": "Lese ich", "planned": "Geplant", "paused": "Pausiert", "finished": "Fertig", "dropped": "Abgebrochen"}


def set_reading_status(connection, uid, series_id, status):
    if status:
        connection.execute(
            """INSERT INTO series_reading(user_id,series_id,status,updated_at) VALUES(?,?,?,?)
               ON CONFLICT(user_id,series_id) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at""",
            (uid, series_id, status, now_iso()))
    else:
        connection.execute("DELETE FROM series_reading WHERE user_id=? AND series_id=?", (uid, series_id))


def status_of(connection, uid, series_id):
    row = connection.execute("SELECT status FROM series_reading WHERE user_id=? AND series_id=?", (uid, series_id)).fetchone()
    return row["status"] if row else ""


def follow_read_marks(connection, uid, edition_id):
    """The status changes read marks bring about (see the module docstring); returns the new status."""
    edition = connection.execute("SELECT id, series_id, status, volume_count FROM editions WHERE id=?", (edition_id,)).fetchone()
    status = status_of(connection, uid, edition["series_id"])
    reads = connection.execute(
        "SELECT COUNT(*) FROM volume_reads r JOIN volumes v ON v.id=r.volume_id WHERE r.user_id=? AND v.edition_id=?", (uid, edition_id)).fetchone()[0]
    if reads and status in ("", "planned"):
        status = "reading"
        set_reading_status(connection, uid, edition["series_id"], status)
    if status == "reading" and edition["status"] == "completed" and edition["volume_count"]:
        read_numbers = {row[0] for row in connection.execute(
            """SELECT DISTINCT CAST(v.number AS INTEGER) FROM volume_reads r JOIN volumes v ON v.id=r.volume_id
               WHERE r.user_id=? AND v.edition_id=? AND v.number IS NOT NULL""", (uid, edition_id))}
        if set(range(1, edition["volume_count"] + 1)) <= read_numbers:
            status = "finished"
            set_reading_status(connection, uid, edition["series_id"], status)
    return status


@app.put("/api/volumes/<int:volume_id>/read")
@login_required
def mark_read(volume_id):
    uid, connection = user_id(), db()
    volume = connection.execute("SELECT id, edition_id FROM volumes WHERE id=?", (volume_id,)).fetchone()
    if not volume:
        return jsonify({"error": "Band nicht gefunden."}), 404
    payload = request.get_json(silent=True) or {}
    read_at = str(payload.get("read_at") or today_iso())[:10]
    connection.execute("INSERT OR IGNORE INTO volume_reads(user_id,volume_id,read_at) VALUES(?,?,?)", (uid, volume_id, read_at))
    status = follow_read_marks(connection, uid, volume["edition_id"])
    connection.commit()
    return jsonify({"read": True, "reading_status": status})


@app.delete("/api/volumes/<int:volume_id>/read")
@login_required
def unmark_read(volume_id):
    uid, connection = user_id(), db()
    connection.execute("DELETE FROM volume_reads WHERE user_id=? AND volume_id=?", (uid, volume_id))
    connection.commit()
    return jsonify({"read": False})


@app.post("/api/editions/<int:edition_id>/read")
@login_required
def mark_read_through(edition_id):
    """{through: n}: every numbered volume up to n (variants included) counts as read, the ones after
    it as unread; n = 0 clears the edition's read marks. Special volumes keep theirs."""
    uid, connection = user_id(), db()
    if not connection.execute("SELECT 1 FROM editions WHERE id=?", (edition_id,)).fetchone():
        return jsonify({"error": "Ausgabe nicht gefunden."}), 404
    try:
        through = float(str((request.get_json(force=True) or {}).get("through", "")).replace(",", "."))
    except ValueError:
        return jsonify({"error": "Bis zu welchem Band? Bitte eine Zahl."}), 400
    stamp = today_iso()
    connection.execute(
        """DELETE FROM volume_reads WHERE user_id=? AND volume_id IN
           (SELECT id FROM volumes WHERE edition_id=? AND number IS NOT NULL AND number>?)""", (uid, edition_id, through))
    connection.execute(
        """INSERT OR IGNORE INTO volume_reads(user_id,volume_id,read_at)
           SELECT ?, id, ? FROM volumes WHERE edition_id=? AND number IS NOT NULL AND number<=?""", (uid, stamp, edition_id, through))
    status = follow_read_marks(connection, uid, edition_id)
    connection.commit()
    return jsonify({"through": number_label(through), "reading_status": status})


@app.put("/api/series/<int:series_id>/reading")
@login_required
def put_reading_status(series_id):
    """{status}: one of READING_STATUSES, or empty to have none."""
    connection = db()
    if not connection.execute("SELECT 1 FROM series WHERE id=?", (series_id,)).fetchone():
        return jsonify({"error": "Reihe nicht gefunden."}), 404
    status = str((request.get_json(force=True) or {}).get("status") or "")
    if status and status not in READING_STATUSES:
        return jsonify({"error": "Unbekannter Lesestatus."}), 400
    set_reading_status(connection, user_id(), series_id, status)
    connection.commit()
    return jsonify({"reading_status": status})


def reading_overview(connection, uid):
    """Every series the account has a reading status for or has read a volume of, with the edition
    it reads (most read marks, then collected, then most owned), how far it is and the next volume."""
    account = Account(connection, uid)
    series_ids = set(account.reading)
    if account.read:
        ids = list(account.read)
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            series_ids |= {row[0] for row in connection.execute(
                f"SELECT DISTINCT e.series_id FROM volumes v JOIN editions e ON e.id=v.edition_id WHERE v.id IN ({','.join('?' for _ in chunk)})",
                chunk)}
    if not series_ids:
        return []
    ids = sorted(series_ids)
    editions = edition_items(connection, account, f"e.series_id IN ({','.join('?' for _ in ids)})", ids, with_volumes=True)
    by_series = {}
    for edition in editions:
        by_series.setdefault(edition["series_id"], []).append(edition)
    result = []
    for series_id, items in by_series.items():
        main = max(items, key=lambda item: (item["read"], item["collecting"], item["owned"], -item["id"]))
        numbered = [volume for volume in main["volumes"] if volume["number"] is not None]
        unread = sorted((volume for volume in numbered if not volume["read"] and volume["released"]), key=volume_order)
        last_read = max((volume["read_at"] or "" for volume in main["volumes"] if volume["read"]), default="")
        next_volume = unread[0] if unread else None
        result.append({
            "series_id": series_id, "series_title": main["series_title"], "status": account.reading.get(series_id, ""),
            "edition": {key: main[key] for key in ("id", "name", "publisher", "language", "total", "read", "read_numbers", "owned",
                                                   "released_through", "cover", "status")},
            "editions": len(items),
            "next": {"id": next_volume["id"], "number_label": next_volume["number_label"], "owned": next_volume["owned"],
                     "has_image": next_volume["has_image"], "image_version": next_volume["image_version"]} if next_volume else None,
            "unread_owned": sum(item["unread_owned"] for item in items),
            "last_read": last_read,
        })
    # In passes, each stable: by title, then the latest read first, then by status.
    order = list(READING_STATUSES)
    result.sort(key=lambda item: item["series_title"].lower())
    result.sort(key=lambda item: item["last_read"], reverse=True)
    result.sort(key=lambda item: order.index(item["status"]) if item["status"] in order else len(order))
    return result


@app.get("/api/reading")
@login_required
def get_reading():
    items = reading_overview(db(), user_id())
    counts = {status: sum(1 for item in items if item["status"] == status) for status in READING_STATUSES}
    counts["none"] = sum(1 for item in items if not item["status"])
    return jsonify({"series": items, "counts": counts, "statuses": READING_STATUSES})
