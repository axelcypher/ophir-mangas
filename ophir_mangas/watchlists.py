"""Wishlists: named lists of what an account wants -- single volumes (with an optional target price)
or whole editions (to start collecting) -- each entry with a note. Every account has a default list
("Wunschliste", schema.ensure_user_lists) that cannot be deleted; further lists are its own.

A list shows the editions it touches as tiles, like the catalogue (a whole edition, or an edition
with wished volumes), or with `level=volumes` the wished volumes. A volume whose market value has
fallen to its target price or below is marked (target_reached).
"""

from flask import jsonify, request

from .config import now_iso
from .editions import grid_answer
from .listing import Account, edition_items, volume_items
from .prices import parse_amount
from .volumes import volume_grid_answer
from .web import app, db, login_required, user_id

NAME_LIMIT = 60
KINDS = {"volumes": "volume_id", "editions": "edition_id"}
TABLE_OF = {"volumes": "volumes", "editions": "editions"}
NOT_ON_LIST = {"volumes": "Der Band steht nicht auf dieser Liste.", "editions": "Die Ausgabe steht nicht auf dieser Liste."}


def own_list(list_id, uid):
    return db().execute("SELECT * FROM watchlists WHERE id=? AND user_id=?", (list_id, uid)).fetchone()


def lists_of(uid):
    return [dict(row) for row in db().execute(
        """SELECT w.id, w.name, w.is_default, w.created_at, COUNT(we.id) count
           FROM watchlists w LEFT JOIN watchlist_entries we ON we.list_id=w.id
           WHERE w.user_id=? GROUP BY w.id ORDER BY w.is_default DESC, lower(w.name)""", (uid,))]


@app.get("/api/watchlists")
@login_required
def get_watchlists():
    return jsonify(lists_of(user_id()))


def clean_name(payload, uid, list_id=0):
    name = " ".join(str(payload.get("name") or "").split())[:NAME_LIMIT]
    if not name:
        return None, "Der Name fehlt."
    if db().execute("SELECT 1 FROM watchlists WHERE user_id=? AND lower(name)=lower(?) AND id!=?", (uid, name, list_id)).fetchone():
        return None, "Eine Liste mit diesem Namen gibt es schon."
    return name, None


@app.post("/api/watchlists")
@login_required
def create_watchlist():
    uid = user_id()
    name, error = clean_name(request.get_json(force=True) or {}, uid)
    if error:
        return jsonify({"error": error}), 400
    cursor = db().execute("INSERT INTO watchlists(user_id,name,is_default,created_at) VALUES(?,?,0,?)", (uid, name, now_iso()))
    db().commit()
    return jsonify({"id": cursor.lastrowid, "name": name, "is_default": 0, "count": 0}), 201


@app.patch("/api/watchlists/<int:list_id>")
@login_required
def rename_watchlist(list_id):
    uid = user_id()
    if not own_list(list_id, uid):
        return jsonify({"error": "Liste nicht gefunden."}), 404
    name, error = clean_name(request.get_json(force=True) or {}, uid, list_id)
    if error:
        return jsonify({"error": error}), 400
    db().execute("UPDATE watchlists SET name=? WHERE id=?", (name, list_id))
    db().commit()
    return jsonify({"saved": True})


@app.delete("/api/watchlists/<int:list_id>")
@login_required
def delete_watchlist(list_id):
    row = own_list(list_id, user_id())
    if not row:
        return jsonify({"error": "Liste nicht gefunden."}), 404
    if row["is_default"]:
        return jsonify({"error": "Die Standardliste kann nicht gelöscht werden."}), 400
    db().execute("DELETE FROM watchlists WHERE id=?", (list_id,))  # its entries go with it (ON DELETE CASCADE)
    db().commit()
    return jsonify({"deleted": True})


def list_volumes(connection, account, list_id):
    entries = {row["volume_id"]: row for row in connection.execute(
        "SELECT * FROM watchlist_entries WHERE list_id=? AND volume_id IS NOT NULL", (list_id,))}
    items = volume_items(connection, account, "v.id IN (SELECT volume_id FROM watchlist_entries WHERE list_id=?)", (list_id,)) if entries else []
    for item in items:
        entry = entries[item["id"]]
        item.update({"target_price": entry["target_price"], "note": entry["note"], "wished_at": entry["created_at"],
                     "target_reached": entry["target_price"] is not None and item["market_value"] is not None
                     and item["market_value"] <= entry["target_price"],
                     "reading_status": account.reading.get(item["series_id"], "")})
    return items


def list_editions(connection, account, list_id, volumes):
    whole = {row["edition_id"]: row for row in connection.execute(
        "SELECT * FROM watchlist_entries WHERE list_id=? AND edition_id IS NOT NULL", (list_id,))}
    wished_volumes = {}
    for volume in volumes:
        wished_volumes.setdefault(volume["edition_id"], []).append(volume)
    ids = sorted(set(whole) | set(wished_volumes))
    if not ids:
        return []
    items = edition_items(connection, account, f"e.id IN ({','.join('?' for _ in ids)})", ids)
    for item in items:
        entry = whole.get(item["id"])
        own = wished_volumes.get(item["id"], [])
        item.update({"whole": bool(entry), "note": entry["note"] if entry else "",
                     "wished_at": max(([entry["created_at"]] if entry else []) + [volume["wished_at"] for volume in own] or [""]),
                     "wished_volumes": [volume["number_label"] or volume["title"] for volume in own],
                     "target_reached": sum(1 for volume in own if volume["target_reached"])})
    return items


@app.get("/api/watchlists/<int:list_id>/entries")
@login_required
def watchlist_entries(list_id):
    uid, connection = user_id(), db()
    row = own_list(list_id, uid)
    if not row:
        return jsonify({"error": "Liste nicht gefunden."}), 404
    account = Account(connection, uid)
    args = request.args
    volumes = list_volumes(connection, account, list_id)
    editions = list_editions(connection, account, list_id, volumes)
    estimate = sum(item["market_value"] if item["market_value"] is not None else (item["target_price"] or item["list_price"] or 0)
                   for item in volumes if not item["owned"])
    stats = {"editions": len(editions), "whole": sum(1 for item in editions if item["whole"]), "volumes": len(volumes),
             "owned": sum(1 for item in volumes if item["owned"]), "target_reached": sum(1 for item in volumes if item["target_reached"]),
             "estimate": round(estimate, 2)}
    # "wished" (the default): the latest wish first; any other sort as the grids have it.
    by_wish = args.get("sort", "wished") == "wished"
    if args.get("level") == "volumes":
        items = [item for item in volumes if not (args.get("mode") == "missing" and item["owned"])]
        answer = volume_grid_answer(items, volumes, args, default_sort="title")
        grid = answer["volumes"]
    else:
        answer = grid_answer(editions, editions, args, default_sort="title")
        grid = answer.get("editions", [])
    if by_wish:
        grid.sort(key=lambda item: (item["wished_at"], item["id"]), reverse=args.get("direction", "desc") == "desc")
    return jsonify({**answer, "list": dict(row), "list_stats": stats})


def clean_entry(payload):
    fields = {}
    if "target_price" in payload:
        fields["target_price"], error = parse_amount(payload["target_price"], "Zielpreis")
        if error:
            return None, error
    if "note" in payload:
        fields["note"] = str(payload["note"] or "").strip()[:500]
    return fields, None


@app.post("/api/watchlists/<int:list_id>/<any(volumes, editions):kind>")
@login_required
def add_to_watchlist(list_id, kind):
    """{volume_id | edition_id, target_price, note}; adding again only updates the given fields."""
    if not own_list(list_id, user_id()):
        return jsonify({"error": "Liste nicht gefunden."}), 404
    payload = request.get_json(force=True) or {}
    column = KINDS[kind]
    try:
        entry_id = int(payload.get(column))
    except (TypeError, ValueError):
        return jsonify({"error": "Nichts angegeben, was auf die Liste soll."}), 400
    if not db().execute(f"SELECT 1 FROM {TABLE_OF[kind]} WHERE id=?", (entry_id,)).fetchone():
        return jsonify({"error": "Band nicht gefunden." if kind == "volumes" else "Ausgabe nicht gefunden."}), 404
    fields, error = clean_entry(payload)
    if error:
        return jsonify({"error": error}), 400
    if kind == "editions":
        fields.pop("target_price", None)
    db().execute(f"INSERT OR IGNORE INTO watchlist_entries(list_id,{column},created_at) VALUES(?,?,?)", (list_id, entry_id, now_iso()))
    if fields:
        db().execute(f"UPDATE watchlist_entries SET {','.join(f'{key}=?' for key in fields)} WHERE list_id=? AND {column}=?",
                     (*fields.values(), list_id, entry_id))
    db().commit()
    return jsonify({"added": True, "lists": lists_of(user_id())}), 201


@app.patch("/api/watchlists/<int:list_id>/<any(volumes, editions):kind>/<int:entry_id>")
@login_required
def update_watchlist_entry(list_id, kind, entry_id):
    if not own_list(list_id, user_id()):
        return jsonify({"error": "Liste nicht gefunden."}), 404
    fields, error = clean_entry(request.get_json(force=True) or {})
    if error:
        return jsonify({"error": error}), 400
    if kind == "editions":
        fields.pop("target_price", None)
    if not fields:
        return jsonify({"error": "Keine Änderungen übermittelt."}), 400
    updated = db().execute(f"UPDATE watchlist_entries SET {','.join(f'{key}=?' for key in fields)} WHERE list_id=? AND {KINDS[kind]}=?",
                           (*fields.values(), list_id, entry_id)).rowcount
    if not updated:
        return jsonify({"error": NOT_ON_LIST[kind]}), 404
    db().commit()
    return jsonify({"saved": True})


@app.delete("/api/watchlists/<int:list_id>/<any(volumes, editions):kind>/<int:entry_id>")
@login_required
def remove_from_watchlist(list_id, kind, entry_id):
    if not own_list(list_id, user_id()):
        return jsonify({"error": "Liste nicht gefunden."}), 404
    column = KINDS[kind]
    entry = db().execute(f"SELECT {column},target_price,note FROM watchlist_entries WHERE list_id=? AND {column}=?", (list_id, entry_id)).fetchone()
    if not entry:
        return jsonify({"error": NOT_ON_LIST[kind]}), 404
    db().execute(f"DELETE FROM watchlist_entries WHERE list_id=? AND {column}=?", (list_id, entry_id))
    db().commit()
    return jsonify({"removed": dict(entry), "lists": lists_of(user_id())})
