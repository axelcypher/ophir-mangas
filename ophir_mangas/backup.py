"""Export, backup and restore of what an account entered.

- GET /api/export.json: a backup of the account -- copies, preorders (with their history),
  wishlists, read marks, reading statuses and the editions it collects -- carrying every series,
  edition and volume it refers to (an edition with all its volumes), so it can be restored on
  another instance whose catalogue does not have them yet. Pictures are not part of it; their
  links are.
- GET /api/export.csv and /api/export/preorders.csv: tables for spreadsheets.
- POST /api/import/json/preview and /apply: restore such a backup. Series, editions and volumes are
  matched to the catalogue by the rules that keep it free of duplicates (catalog.find_*_duplicate)
  and created where missing. "add" adds the copies to the current ones, "replace" replaces the
  collection. Preorders already present (same volume, shop, order date and order number) are
  skipped, wishlists are merged by name, and a reading status the account already has stays.
- POST /api/import/<id>/undo takes the latest restore back: what it added goes, a replaced
  collection comes back, catalogue entries it created go when nothing uses them any more.
"""

import csv
import io
import json

from flask import Response, jsonify, request

from .catalog import (FieldError, clean_edition_fields, clean_series_fields, clean_volume_fields, edition_in_use, edition_name,
                      find_edition_duplicate, find_series_duplicate, find_volume_duplicate, insert_row, number_label, series_in_use,
                      volume_in_use)
from .collection import CONDITIONS, clean_entry_fields
from .config import APP_NAME, jload, now_iso
from .preorders import STATUSES, clean_preorder_fields
from .prices import market_value_sql
from .reading import READING_STATUSES
from .schema import ensure_user_lists
from .web import app, db, login_required, user_id

FORMAT = "ophir-mangas-backup"
SERIES_FIELDS = ("title", "original_title", "alt_titles", "authors", "genres", "demographic", "status", "original_volumes", "start_year",
                 "description", "source_url", "image_url", "anilist_id")
EDITION_FIELDS = ("title", "label", "publisher", "language", "format", "status", "volume_count", "list_price", "currency", "description",
                  "source_url")
VOLUME_FIELDS = ("number", "title", "variant", "isbn", "release_date", "list_price", "currency", "pages", "description", "source_url", "image_url")
ENTRY_FIELDS = ("quantity", "condition", "first_printing", "extras", "purchase_price", "purchased_at", "shop", "location", "notes")
PREORDER_FIELDS = ("status", "shop", "order_number", "ordered_at", "quantity", "price", "shipping", "paid", "expected_release",
                   "tracking", "notes", "delivered_at")


def in_list(column, ids):
    ids = sorted(ids)
    return f"{column} IN ({','.join('?' for _ in ids)})", ids


def build_backup(uid):
    connection = db()
    user = connection.execute("SELECT username,display_name FROM users WHERE id=?", (uid,)).fetchone()
    entries = [dict(row) for row in connection.execute("SELECT * FROM collection_entries WHERE user_id=? ORDER BY id", (uid,))]
    preorders = [dict(row) for row in connection.execute("SELECT * FROM preorders WHERE user_id=? ORDER BY id", (uid,))]
    lists = [dict(row) for row in connection.execute("SELECT * FROM watchlists WHERE user_id=? ORDER BY is_default DESC, id", (uid,))]
    list_entries = {}
    for row in connection.execute(
            "SELECT we.* FROM watchlist_entries we JOIN watchlists w ON w.id=we.list_id WHERE w.user_id=? ORDER BY we.id", (uid,)):
        list_entries.setdefault(row["list_id"], []).append(dict(row))
    reads = [dict(row) for row in connection.execute("SELECT volume_id, read_at FROM volume_reads WHERE user_id=? ORDER BY volume_id", (uid,))]
    reading = [dict(row) for row in connection.execute("SELECT series_id, status, updated_at FROM series_reading WHERE user_id=?", (uid,))]
    collecting = [dict(row) for row in connection.execute("SELECT edition_id, created_at FROM collected_editions WHERE user_id=?", (uid,))]

    volume_ids = ({row["volume_id"] for row in entries} | {row["volume_id"] for row in preorders} | {row["volume_id"] for row in reads}
                  | {entry["volume_id"] for rows in list_entries.values() for entry in rows if entry["volume_id"]})
    edition_ids = {row["edition_id"] for row in collecting} | {entry["edition_id"] for rows in list_entries.values() for entry in rows if entry["edition_id"]}
    if volume_ids:
        where, params = in_list("id", volume_ids)
        edition_ids |= {row[0] for row in connection.execute(f"SELECT DISTINCT edition_id FROM volumes WHERE {where}", params)}
    editions, volumes, series = [], [], []
    series_ids = {row["series_id"] for row in reading}
    if edition_ids:
        where, params = in_list("id", edition_ids)
        for row in connection.execute(f"SELECT * FROM editions WHERE {where} ORDER BY id", params):
            editions.append({"ref": row["id"], "series_ref": row["series_id"], **{key: row[key] for key in EDITION_FIELDS}})
            series_ids.add(row["series_id"])
        where, params = in_list("v.edition_id", edition_ids)
        for row in connection.execute(f"SELECT v.*, {market_value_sql('v.id')} market_value FROM volumes v WHERE {where} ORDER BY v.id", params):
            volumes.append({"ref": row["id"], "edition_ref": row["edition_id"], **{key: row[key] for key in VOLUME_FIELDS},
                            "attributes": jload(row["attributes"], {}) or {}, "market_value": row["market_value"]})
    if series_ids:
        where, params = in_list("id", series_ids)
        for row in connection.execute(f"SELECT * FROM series WHERE {where} ORDER BY id", params):
            series.append({"ref": row["id"], **{key: row[key] for key in SERIES_FIELDS}, "attributes": jload(row["attributes"], {}) or {}})

    preorder_index = {row["id"]: index for index, row in enumerate(preorders)}
    events = {}
    if preorders:
        where, params = in_list("preorder_id", [row["id"] for row in preorders])
        for event in connection.execute(f"SELECT * FROM preorder_events WHERE {where} ORDER BY id", params):
            events.setdefault(event["preorder_id"], []).append({key: event[key] for key in ("kind", "old_value", "new_value", "created_at")})
    return {
        "format": FORMAT, "version": 1, "app": APP_NAME, "exported_at": now_iso(),
        "user": {"username": user["username"], "display_name": user["display_name"]},
        "series": series, "editions": editions, "volumes": volumes,
        "collection": [{"volume_ref": row["volume_id"], **{key: row[key] for key in ENTRY_FIELDS},
                        "preorder_index": preorder_index.get(row["preorder_id"]), "created_at": row["created_at"]} for row in entries],
        "preorders": [{"volume_ref": row["volume_id"], **{key: row[key] for key in PREORDER_FIELDS}, "created_at": row["created_at"],
                       "events": events.get(row["id"], [])} for row in preorders],
        "watchlists": [{"name": row["name"], "is_default": bool(row["is_default"]),
                        "entries": [{"volume_ref": entry["volume_id"], "edition_ref": entry["edition_id"], "target_price": entry["target_price"],
                                     "note": entry["note"], "created_at": entry["created_at"]} for entry in list_entries.get(row["id"], [])]}
                       for row in lists],
        "reads": [{"volume_ref": row["volume_id"], "read_at": row["read_at"]} for row in reads],
        "reading": [{"series_ref": row["series_id"], "status": row["status"], "updated_at": row["updated_at"]} for row in reading],
        "collecting": [{"edition_ref": row["edition_id"], "created_at": row["created_at"]} for row in collecting],
    }


@app.get("/api/export.json")
@login_required
def export_json():
    payload = json.dumps(build_backup(user_id()), ensure_ascii=False, indent=1)
    return Response(payload, mimetype="application/json",
                    headers={"Content-Disposition": f"attachment; filename=ophir-mangas-backup-{now_iso()[:10]}.json"})


def csv_response(rows, header, filename):
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(header)
    writer.writerows(rows)
    # A BOM, so Excel reads the umlauts as UTF-8.
    return Response("﻿" + buffer.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})


def money_cell(value):
    return "" if value is None else f"{value:.2f}".replace(".", ",")


CATALOGUE_JOIN = """JOIN volumes v ON v.id={column} JOIN editions e ON e.id=v.edition_id JOIN series s ON s.id=e.series_id"""


@app.get("/api/export.csv")
@login_required
def export_csv():
    uid = user_id()
    rows = db().execute(
        f"""SELECT s.title series_title, s.authors, e.title edition_title, e.label, e.publisher, e.language, e.format, v.number, v.title,
                   v.variant, v.isbn, v.release_date, c.*, {market_value_sql('v.id')} market_value,
                   EXISTS(SELECT 1 FROM volume_reads r WHERE r.user_id=c.user_id AND r.volume_id=v.id) is_read
            FROM collection_entries c {CATALOGUE_JOIN.format(column='c.volume_id')}
            WHERE c.user_id=? ORDER BY s.title, e.id, v.number, c.id""", (uid,))
    header = ["Reihe", "Ausgabe", "Autor:innen", "Verlag", "Sprache", "Format", "Band", "Titel", "Variante", "ISBN", "Erscheinung", "Anzahl",
              "Zustand", "Erstauflage", "Extras", "Kaufpreis (EUR)", "Kaufdatum", "Shop", "Aufbewahrung", "Notizen", "Gelesen", "Marktwert (EUR)"]
    return csv_response(
        ([row["series_title"], edition_name({"title": row["edition_title"], "label": row["label"]}, row["series_title"]), row["authors"],
          row["publisher"], row["language"], row["format"], number_label(row["number"]), row["title"], row["variant"], row["isbn"],
          row["release_date"], row["quantity"], CONDITIONS.get(row["condition"], row["condition"]), "ja" if row["first_printing"] else "",
          row["extras"], money_cell(row["purchase_price"]), row["purchased_at"], row["shop"], row["location"], row["notes"],
          "ja" if row["is_read"] else "", money_cell(row["market_value"])] for row in rows),
        header, f"ophir-mangas-sammlung-{now_iso()[:10]}.csv")


@app.get("/api/export/preorders.csv")
@login_required
def export_preorders_csv():
    rows = db().execute(
        f"""SELECT s.title series_title, e.title edition_title, e.label, e.publisher, v.number, v.variant, v.isbn, p.*
            FROM preorders p {CATALOGUE_JOIN.format(column='p.volume_id')} WHERE p.user_id=?
            ORDER BY COALESCE(NULLIF(p.expected_release,''),'9999'), p.id""", (user_id(),))
    header = ["Ausgabe", "Band", "Variante", "ISBN", "Verlag", "Status", "Shop", "Bestellnummer", "Bestellt am", "Anzahl", "Preis (EUR)",
              "Versand (EUR)", "Bezahlt (EUR)", "Erwartet", "Angekommen", "Sendungsnummer", "Notizen"]
    return csv_response(
        ([edition_name({"title": row["edition_title"], "label": row["label"]}, row["series_title"]), number_label(row["number"]), row["variant"],
          row["isbn"], row["publisher"], STATUSES.get(row["status"], row["status"]), row["shop"], row["order_number"], row["ordered_at"],
          row["quantity"], money_cell(row["price"]), money_cell(row["shipping"]), money_cell(row["paid"]), row["expected_release"],
          row["delivered_at"] or "", row["tracking"], row["notes"]] for row in rows),
        header, f"ophir-mangas-vorbestellungen-{now_iso()[:10]}.csv")


class BackupError(Exception):
    pass


def cleaned(raws, what, clean, keys, refs=()):
    """{ref: (fields, raw)} of a backup's catalogue list, every entry checked like a form."""
    result = {}
    if not isinstance(raws, list):
        raise BackupError(f"Die Sicherung enthält keine Liste der {what}.")
    for raw in raws:
        if not isinstance(raw, dict) or "ref" not in raw or any(ref not in raw for ref in refs):
            raise BackupError(f"Ein Eintrag der {what} hat keine Kennung.")
        try:
            fields = clean({key: raw.get(key) for key in (*keys, "attributes") if key in raw})
        except FieldError as error:
            raise BackupError(f"{what} „{raw.get('title') or raw.get('number') or raw['ref']}“: {error}")
        result[raw["ref"]] = (fields, raw)
    return result


def read_backup(payload):
    data = payload.get("data")
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise BackupError("Das ist keine Sicherung von Ophir Mangas.")
    series = cleaned(data.get("series") or [], "Reihen", clean_series_fields, SERIES_FIELDS)
    editions = cleaned(data.get("editions") or [], "Ausgaben", clean_edition_fields, EDITION_FIELDS, ("series_ref",))
    volumes = cleaned(data.get("volumes") or [], "Bände", clean_volume_fields, VOLUME_FIELDS, ("edition_ref",))
    for ref, (_, raw) in editions.items():
        if raw["series_ref"] not in series:
            raise BackupError("Eine Ausgabe der Sicherung verweist auf eine Reihe, die nicht darin steht.")
    for ref, (_, raw) in volumes.items():
        if raw["edition_ref"] not in editions:
            raise BackupError("Ein Band der Sicherung verweist auf eine Ausgabe, die nicht darin steht.")
    return data, series, editions, volumes


def match_catalogue(connection, series, editions, volumes):
    """{ref: existing id or None} for each level; an entry under a new parent is new too."""
    series_ids = {ref: (found[0] if (found := find_series_duplicate(connection, fields)) else None) for ref, (fields, _) in series.items()}
    edition_ids = {}
    for ref, (fields, raw) in editions.items():
        parent = series_ids[raw["series_ref"]]
        edition_ids[ref] = (found[0] if parent and (found := find_edition_duplicate(connection, parent, fields)) else None)
    volume_ids = {}
    for ref, (fields, raw) in volumes.items():
        parent = edition_ids[raw["edition_ref"]]
        found = find_volume_duplicate(connection, parent or 0, fields)
        volume_ids[ref] = found[0] if found and (parent or found[1] == "gleiche ISBN") else None
    return series_ids, edition_ids, volume_ids


@app.post("/api/import/json/preview")
@login_required
def preview_backup():
    try:
        data, series, editions, volumes = read_backup(request.get_json(force=True) or {})
    except BackupError as error:
        return jsonify({"error": str(error)}), 400
    series_ids, edition_ids, volume_ids = match_catalogue(db(), series, editions, volumes)
    return jsonify({
        "series": len(series), "series_new": sum(1 for value in series_ids.values() if value is None),
        "editions": len(editions), "editions_new": sum(1 for value in edition_ids.values() if value is None),
        "volumes": len(volumes), "volumes_new": sum(1 for value in volume_ids.values() if value is None),
        "collection": len(data.get("collection") or []), "preorders": len(data.get("preorders") or []),
        "watchlists": len(data.get("watchlists") or []),
        "watchlist_entries": sum(len(item.get("entries") or []) for item in data.get("watchlists") or [] if isinstance(item, dict)),
        "reads": len(data.get("reads") or []), "reading": len(data.get("reading") or []), "collecting": len(data.get("collecting") or []),
        "exported_at": data.get("exported_at"), "user": (data.get("user") or {}).get("display_name"),
    })


@app.post("/api/import/json/apply")
@login_required
def apply_backup():
    payload = request.get_json(force=True) or {}
    strategy = payload.get("strategy") if payload.get("strategy") in ("add", "replace") else "add"
    uid, connection = user_id(), db()
    try:
        changes = restore(connection, uid, *read_backup(payload), strategy)
    except BackupError as error:
        connection.rollback()
        return jsonify({"error": str(error)}), 400
    cursor = connection.execute("INSERT INTO import_operations(user_id,created_at,changes) VALUES(?,?,?)", (uid, now_iso(), json.dumps(changes)))
    connection.commit()
    return jsonify({"operation_id": cursor.lastrowid, "series_created": len(changes["series"]), "editions_created": len(changes["editions"]),
                    "volumes_created": len(changes["volumes"]), "collection": len(changes["entries"]), "preorders": len(changes["preorders"]),
                    "preorders_skipped": changes["preorders_skipped"], "watchlist_entries": len(changes["watchlist_entries"]),
                    "reads": len(changes["reads"]), "reading": len(changes["reading"]), "collecting": len(changes["collecting"]),
                    "replaced": len(changes["replaced"])})


def restore(connection, uid, data, series, editions, volumes, strategy):
    stamp = now_iso()
    changes = {"series": [], "editions": [], "volumes": [], "entries": [], "preorders": [], "preorders_skipped": 0, "watchlists": [],
               "watchlist_entries": [], "reads": [], "reading": [], "collecting": [], "replaced": []}
    series_ids, edition_ids, volume_ids = match_catalogue(connection, series, editions, volumes)
    owner = {"created_by": uid, "created_at": stamp, "updated_at": stamp}
    for ref, (fields, _) in series.items():
        if series_ids[ref] is None:
            series_ids[ref] = insert_row(connection, "series", {**fields, **owner})
            changes["series"].append(series_ids[ref])
    for ref, (fields, raw) in editions.items():
        if edition_ids[ref] is None:
            edition_ids[ref] = insert_row(connection, "editions", {**fields, "series_id": series_ids[raw["series_ref"]], **owner})
            changes["editions"].append(edition_ids[ref])
    for ref, (fields, raw) in volumes.items():
        if volume_ids[ref] is None:
            volume_ids[ref] = insert_row(connection, "volumes", {**fields, "edition_id": edition_ids[raw["edition_ref"]], **owner})
            changes["volumes"].append(volume_ids[ref])

    def ref_of(item, key, ids, what):
        if not isinstance(item, dict) or item.get(key) not in ids:
            raise BackupError(f"{what} verweist auf etwas, das nicht in der Sicherung steht.")
        return ids[item[key]]

    preorder_ids = []
    for item in data.get("preorders") or []:
        volume_id = ref_of(item, "volume_ref", volume_ids, "Eine Vorbestellung")
        fields, error = clean_preorder_fields({key: item.get(key) for key in PREORDER_FIELDS if key in item})
        if error:
            raise BackupError(f"Vorbestellung: {error}")
        existing = connection.execute(
            "SELECT id FROM preorders WHERE user_id=? AND volume_id=? AND shop=? AND ordered_at=? AND order_number=?",
            (uid, volume_id, fields.get("shop", ""), fields.get("ordered_at", ""), fields.get("order_number", ""))).fetchone()
        if existing:
            preorder_ids.append(existing["id"])
            changes["preorders_skipped"] += 1
            continue
        preorder_id = insert_row(connection, "preorders", {**fields, "user_id": uid, "volume_id": volume_id,
                                                            "created_at": item.get("created_at") or stamp, "updated_at": stamp})
        for event in item.get("events") or []:
            if isinstance(event, dict) and event.get("kind"):
                connection.execute("INSERT INTO preorder_events(preorder_id,kind,old_value,new_value,created_at) VALUES(?,?,?,?,?)",
                                   (preorder_id, str(event["kind"])[:20], str(event.get("old_value") or "")[:40],
                                    str(event.get("new_value") or "")[:40], str(event.get("created_at") or stamp)[:40]))
        preorder_ids.append(preorder_id)
        changes["preorders"].append(preorder_id)

    if strategy == "replace":
        for row in connection.execute("SELECT * FROM collection_entries WHERE user_id=?", (uid,)):
            changes["replaced"].append(dict(row))
        connection.execute("DELETE FROM collection_entries WHERE user_id=?", (uid,))
    for item in data.get("collection") or []:
        volume_id = ref_of(item, "volume_ref", volume_ids, "Ein Sammlungseintrag")
        fields, error = clean_entry_fields({key: item.get(key) for key in ENTRY_FIELDS if key in item})
        if error:
            raise BackupError(f"Sammlungseintrag: {error}")
        index = item.get("preorder_index")
        preorder_id = preorder_ids[index] if isinstance(index, int) and 0 <= index < len(preorder_ids) else None
        changes["entries"].append(insert_row(connection, "collection_entries", {
            **fields, "user_id": uid, "volume_id": volume_id, "preorder_id": preorder_id, "created_at": item.get("created_at") or stamp,
            "updated_at": stamp}))

    for item in data.get("reads") or []:
        volume_id = ref_of(item, "volume_ref", volume_ids, "Eine Lesemarke")
        if connection.execute("INSERT OR IGNORE INTO volume_reads(user_id,volume_id,read_at) VALUES(?,?,?)",
                              (uid, volume_id, str(item.get("read_at") or stamp)[:10])).rowcount:
            changes["reads"].append(volume_id)
    for item in data.get("reading") or []:
        series_id = ref_of(item, "series_ref", series_ids, "Ein Lesestatus")
        if item.get("status") in READING_STATUSES and connection.execute(
                "INSERT OR IGNORE INTO series_reading(user_id,series_id,status,updated_at) VALUES(?,?,?,?)",
                (uid, series_id, item["status"], str(item.get("updated_at") or stamp)[:40])).rowcount:
            changes["reading"].append(series_id)
    for item in data.get("collecting") or []:
        edition_id = ref_of(item, "edition_ref", edition_ids, "Eine gesammelte Ausgabe")
        if connection.execute("INSERT OR IGNORE INTO collected_editions(user_id,edition_id,created_at) VALUES(?,?,?)",
                              (uid, edition_id, str(item.get("created_at") or stamp)[:40])).rowcount:
            changes["collecting"].append(edition_id)

    ensure_user_lists(connection, uid)
    for item in data.get("watchlists") or []:
        if not isinstance(item, dict):
            continue
        name = " ".join(str(item.get("name") or "").split())[:60]
        if item.get("is_default"):
            row = connection.execute("SELECT id FROM watchlists WHERE user_id=? AND is_default=1", (uid,)).fetchone()
        else:
            row = connection.execute("SELECT id FROM watchlists WHERE user_id=? AND lower(name)=lower(?)", (uid, name)).fetchone() if name else None
        if row:
            list_id = row["id"]
        elif name:
            list_id = connection.execute("INSERT INTO watchlists(user_id,name,is_default,created_at) VALUES(?,?,0,?)", (uid, name, stamp)).lastrowid
            changes["watchlists"].append(list_id)
        else:
            continue
        for entry in item.get("entries") or []:
            if isinstance(entry, dict) and entry.get("edition_ref") is not None:
                column, target = "edition_id", ref_of(entry, "edition_ref", edition_ids, "Ein Wunschlisteneintrag")
            else:
                column, target = "volume_id", ref_of(entry, "volume_ref", volume_ids, "Ein Wunschlisteneintrag")
            cursor = connection.execute(
                f"INSERT OR IGNORE INTO watchlist_entries(list_id,{column},target_price,note,created_at) VALUES(?,?,?,?,?)",
                (list_id, target, entry.get("target_price") if isinstance(entry.get("target_price"), (int, float)) and column == "volume_id" else None,
                 str(entry.get("note") or "")[:500], entry.get("created_at") or stamp))
            if cursor.rowcount:
                changes["watchlist_entries"].append(cursor.lastrowid)
    return changes


@app.post("/api/import/<int:operation_id>/undo")
@login_required
def undo_import(operation_id):
    uid, connection = user_id(), db()
    operation = connection.execute("SELECT * FROM import_operations WHERE id=? AND user_id=?", (operation_id, uid)).fetchone()
    if not operation:
        return jsonify({"error": "Diesen Import gibt es nicht."}), 404
    if operation["undone_at"]:
        return jsonify({"error": "Der Import wurde schon rückgängig gemacht."}), 400
    latest = connection.execute("SELECT MAX(id) FROM import_operations WHERE user_id=? AND undone_at IS NULL", (uid,)).fetchone()[0]
    if latest != operation_id:
        return jsonify({"error": "Nur der letzte Import kann rückgängig gemacht werden."}), 400
    changes = jload(operation["changes"], {}) or {}

    def delete(table, row_ids, owner_check, column="id"):
        for row_id in row_ids or []:
            connection.execute(f"DELETE FROM {table} WHERE {column}=? AND {owner_check}", (row_id, uid))

    delete("watchlist_entries", changes.get("watchlist_entries"), "list_id IN (SELECT id FROM watchlists WHERE user_id=?)")
    delete("watchlists", changes.get("watchlists"), "user_id=? AND is_default=0")
    delete("collection_entries", changes.get("entries"), "user_id=?")
    delete("preorders", changes.get("preorders"), "user_id=?")
    delete("volume_reads", changes.get("reads"), "user_id=?", "volume_id")
    delete("series_reading", changes.get("reading"), "user_id=?", "series_id")
    delete("collected_editions", changes.get("collecting"), "user_id=?", "edition_id")
    for row in changes.get("replaced") or []:
        if row.get("preorder_id") and not connection.execute("SELECT 1 FROM preorders WHERE id=?", (row["preorder_id"],)).fetchone():
            row["preorder_id"] = None   # deleted since; the copies stay
        columns = [key for key in row if key != "id"]
        connection.execute(f"INSERT INTO collection_entries({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                           [row[key] for key in columns])
    for volume_id in changes.get("volumes") or []:
        if not volume_in_use(connection, volume_id):
            connection.execute("DELETE FROM volumes WHERE id=? AND created_by=?", (volume_id, uid))
    for edition_id in changes.get("editions") or []:
        if not edition_in_use(connection, edition_id) and not connection.execute("SELECT 1 FROM volumes WHERE edition_id=?", (edition_id,)).fetchone():
            connection.execute("DELETE FROM editions WHERE id=? AND created_by=?", (edition_id, uid))
    for series_id in changes.get("series") or []:
        if not series_in_use(connection, series_id) and not connection.execute("SELECT 1 FROM editions WHERE series_id=?", (series_id,)).fetchone():
            connection.execute("DELETE FROM series WHERE id=? AND created_by=?", (series_id, uid))
    connection.execute("UPDATE import_operations SET undone_at=? WHERE id=?", (now_iso(), operation_id))
    connection.commit()
    return jsonify({"undone": True})
