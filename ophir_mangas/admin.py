"""Admin API: accounts, SSO settings and a look over the shared catalogue (duplicates, merging)."""

import json
import re
from pathlib import Path

from flask import jsonify, request
from werkzeug.security import generate_password_hash

from .catalog import (edition_in_use, edition_name, find_edition_duplicate, find_volume_duplicate, fold_key, number_label, series_in_use,
                      volume_in_use)
from .config import OAUTH_CONFIG_DEFAULTS, OAUTH_CONFIG_PATH, jload, now_iso
from .web import admin_required, app, db, user_id
from .schema import ensure_user_lists
from .auth import resolve_oauth_config
from .shared_auth import refuse_when_slave


# ---- User management (admin) -------------------------------------------------------------------
USERNAME_PATTERN = r"[a-zA-Z0-9._-]{3,32}"
EMAIL_PATTERN = r"[^@\s]+@[^@\s]+\.[^@\s]+"
USER_ROLES = ("user", "admin")


def user_fields_error(connection, payload, user_id_to_skip=0, require=()):
    """Validates the account fields present in `payload`; returns an error text or None."""
    for field in require:
        if not str(payload.get(field) or "").strip():
            return {"username": "Benutzername ist erforderlich.", "password": "Passwort ist erforderlich."}[field]
    if "username" in payload:
        username = str(payload["username"] or "").strip()
        if not re.fullmatch(USERNAME_PATTERN, username):
            return "Benutzername muss 3-32 Zeichen lang sein (Buchstaben, Zahlen, . _ -)."
        if connection.execute("SELECT 1 FROM users WHERE lower(username)=lower(?) AND id!=?", (username, user_id_to_skip)).fetchone():
            return "Benutzername ist bereits vergeben."
    if payload.get("email"):
        email = str(payload["email"]).strip()
        if not re.fullmatch(EMAIL_PATTERN, email):
            return "E-Mail-Adresse ist ungültig."
        if connection.execute("SELECT 1 FROM users WHERE email!='' AND lower(email)=lower(?) AND id!=?", (email, user_id_to_skip)).fetchone():
            return "E-Mail-Adresse wird bereits von einem anderen Konto verwendet."
    if payload.get("password") and len(str(payload["password"])) < 8:
        return "Das Passwort muss mindestens 8 Zeichen lang sein."
    if "role" in payload and payload["role"] not in USER_ROLES:
        return "Unbekannte Rolle."
    return None


def other_admins(connection, uid):
    return connection.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND id!=?", (uid,)).fetchone()[0]


@app.get("/api/admin/users")
@admin_required
def admin_list_users():
    rows = db().execute(
        """SELECT u.id,u.username,u.display_name,u.email,u.role,u.created_at,
                  u.oauth_subject!='' oauth_linked, u.password_hash!='' password_set,
                  (SELECT COALESCE(SUM(quantity),0) FROM collection_entries c WHERE c.user_id=u.id) copies,
                  (SELECT COUNT(*) FROM preorders p WHERE p.user_id=u.id AND p.status IN ('ordered','paid','shipped')) preorders
           FROM users u ORDER BY lower(u.username)"""
    ).fetchall()
    return jsonify([{**dict(row), "is_self": row["id"] == user_id()} for row in rows])


@app.post("/api/admin/users")
@admin_required
def admin_create_user():
    if refused := refuse_when_slave():
        return refused
    p = request.get_json(force=True)
    if not isinstance(p, dict):
        return jsonify({"error": "Ungültige Anfrage."}), 400
    error = user_fields_error(db(), p, require=("username", "password"))
    if error:
        return jsonify({"error": error}), 400
    username = str(p["username"]).strip()
    cur = db().execute(
        "INSERT INTO users(username,display_name,password_hash,role,created_at,email) VALUES(?,?,?,?,?,?)",
        (username, str(p.get("display_name") or "").strip() or username, generate_password_hash(str(p["password"])),
         p.get("role") or "user", now_iso(), str(p.get("email") or "").strip()),
    )
    ensure_user_lists(db(), cur.lastrowid)
    db().commit()
    return jsonify({"id": cur.lastrowid}), 201


@app.patch("/api/admin/users/<int:target_id>")
@admin_required
def admin_update_user(target_id):
    if refused := refuse_when_slave():
        return refused
    target = db().execute("SELECT * FROM users WHERE id=?", (target_id,)).fetchone()
    if not target:
        return jsonify({"error": "Konto nicht gefunden."}), 404
    p = request.get_json(force=True)
    if not isinstance(p, dict):
        return jsonify({"error": "Ungültige Anfrage."}), 400
    error = user_fields_error(db(), p, user_id_to_skip=target_id)
    if error:
        return jsonify({"error": error}), 400
    if p.get("role") == "user" and target["role"] == "admin" and not other_admins(db(), target_id):
        return jsonify({"error": "Das letzte Admin-Konto kann nicht herabgestuft werden."}), 400
    fields, values = [], []
    for key in ("username", "display_name", "email", "role"):
        if key in p:
            value = str(p[key] or "").strip()
            if key == "display_name" and not value:
                continue
            fields.append(f"{key}=?")
            values.append(value)
    if p.get("password"):
        fields.append("password_hash=?")
        values.append(generate_password_hash(str(p["password"])))
    if p.get("unlink_oauth"):
        fields += ["oauth_provider=''", "oauth_subject=''"]
    if not fields:
        return jsonify({"error": "Keine Änderungen übermittelt."}), 400
    db().execute(f"UPDATE users SET {','.join(fields)} WHERE id=?", (*values, target_id))
    db().commit()
    return jsonify({"saved": True})


@app.delete("/api/admin/users/<int:target_id>")
@admin_required
def admin_delete_user(target_id):
    # A slave's accounts follow the master's; one deleted here would come back at the next visit.
    if refused := refuse_when_slave():
        return refused
    target = db().execute("SELECT role FROM users WHERE id=?", (target_id,)).fetchone()
    if not target:
        return jsonify({"error": "Konto nicht gefunden."}), 404
    if target_id == user_id():
        return jsonify({"error": "Das eigene Konto kann hier nicht gelöscht werden."}), 400
    if target["role"] == "admin" and not other_admins(db(), target_id):
        return jsonify({"error": "Das letzte Admin-Konto kann nicht gelöscht werden."}), 400
    # Everything the account entered goes with it (ON DELETE CASCADE on user_id); the catalogue
    # and market values are shared and stay, only no longer credited to the account.
    db().execute("DELETE FROM users WHERE id=?", (target_id,))
    db().commit()
    return jsonify({"deleted": True})


# ---- Catalogue overview (admin) ----------------------------------------------------------------

def duplicate_groups(rows, keys_of):
    groups = {}
    for row in rows:
        for key in keys_of(row):
            groups.setdefault(key, []).append(row["id"])
    return sorted({tuple(ids) for ids in groups.values() if len(ids) > 1})


@app.get("/api/admin/catalog")
@admin_required
def admin_catalog_overview():
    """Every series and edition with how many accounts use it, the volumes that look like the same
    book, and the groups of entries that look like duplicates at each level, so they can be merged."""
    connection = db()
    series = [dict(row) for row in connection.execute(
        """SELECT s.id,s.title,s.original_title,s.authors,s.anilist_id,s.created_at,u.display_name created_by_name,
                  (SELECT COUNT(*) FROM editions e WHERE e.series_id=s.id) editions,
                  (SELECT COUNT(DISTINCT c.user_id) FROM collection_entries c JOIN volumes v ON v.id=c.volume_id JOIN editions e ON e.id=v.edition_id
                   WHERE e.series_id=s.id) owners
           FROM series s LEFT JOIN users u ON u.id=s.created_by ORDER BY lower(s.title)""")]
    editions = []
    for row in connection.execute(
            """SELECT e.*, s.title series_title, u.display_name created_by_name,
                      (SELECT COUNT(*) FROM volumes v WHERE v.edition_id=e.id) volumes,
                      (SELECT COUNT(DISTINCT c.user_id) FROM collection_entries c JOIN volumes v ON v.id=c.volume_id WHERE v.edition_id=e.id) owners
               FROM editions e JOIN series s ON s.id=e.series_id LEFT JOIN users u ON u.id=e.created_by ORDER BY lower(s.title), e.id"""):
        editions.append({**{key: row[key] for key in ("id", "series_id", "series_title", "publisher", "language", "format", "label", "volumes",
                                                      "owners", "created_by_name")}, "name": edition_name(row, row["series_title"])})
    volume_rows = [dict(row) for row in connection.execute(
        """SELECT v.id,v.edition_id,v.number,v.title,v.variant,v.isbn,v.release_date,
                  (SELECT COUNT(DISTINCT user_id) FROM collection_entries c WHERE c.volume_id=v.id) owners
           FROM volumes v""")]
    volume_groups = duplicate_groups(volume_rows, lambda row: ([f"isbn:{row['isbn']}"] if row["isbn"] else [])
                                     + ([f"number:{row['edition_id']}:{row['number']}:{fold_key(row['variant'])}"] if row["number"] is not None else []))
    in_groups = {volume_id for group in volume_groups for volume_id in group}
    edition_names = {edition["id"]: edition["name"] for edition in editions}
    volumes = [{**row, "number_label": number_label(row["number"]), "edition_name": edition_names.get(row["edition_id"], "")}
               for row in volume_rows if row["id"] in in_groups]
    return jsonify({
        "series": series, "editions": editions, "volumes": volumes,
        "duplicates": {
            "series": duplicate_groups(series, lambda row: [f"title:{fold_key(row['title'])}"]
                                       + ([f"anilist:{row['anilist_id']}"] if row["anilist_id"] else [])
                                       + ([f"title:{fold_key(row['original_title'])}"] if row["original_title"] else [])),
            "editions": duplicate_groups(editions, lambda row: [
                f"{row['series_id']}:{fold_key(row['language'], row['publisher'], row['label'], row['format'])}"]),
            "volumes": volume_groups,
        },
        "unused": {"series": [row["id"] for row in series if not row["editions"]],
                   "editions": [row["id"] for row in editions if not row["volumes"] and not row["owners"]]},
    })


def merge_volumes(connection, source, target):
    """Moves everything that refers to volume `source` over to `target` and deletes `source`."""
    for table in ("collection_entries", "preorders", "price_observations"):
        connection.execute(f"UPDATE {table} SET volume_id=? WHERE volume_id=?", (target, source))
    # A list or an account that has both keeps the target's row.
    connection.execute("""DELETE FROM watchlist_entries WHERE volume_id=?1
                          AND list_id IN (SELECT list_id FROM watchlist_entries WHERE volume_id=?2)""", (source, target))
    connection.execute("UPDATE watchlist_entries SET volume_id=? WHERE volume_id=?", (target, source))
    connection.execute("DELETE FROM volume_reads WHERE volume_id=?1 AND user_id IN (SELECT user_id FROM volume_reads WHERE volume_id=?2)",
                       (source, target))
    connection.execute("UPDATE volume_reads SET volume_id=? WHERE volume_id=?", (target, source))
    connection.execute("DELETE FROM volumes WHERE id=?", (source,))


def merge_editions(connection, source, target):
    """Moves the volumes of edition `source` into `target` (a volume the target already has is
    merged into it), then what refers to the edition itself; deletes `source`."""
    for row in connection.execute("SELECT * FROM volumes WHERE edition_id=?", (source,)).fetchall():
        duplicate = find_volume_duplicate(connection, target, dict(row), exclude_id=row["id"])
        if duplicate and connection.execute("SELECT edition_id FROM volumes WHERE id=?", (duplicate[0],)).fetchone()[0] == target:
            merge_volumes(connection, row["id"], duplicate[0])
        else:
            connection.execute("UPDATE volumes SET edition_id=? WHERE id=?", (target, row["id"]))
    connection.execute("""DELETE FROM watchlist_entries WHERE edition_id=?1
                          AND list_id IN (SELECT list_id FROM watchlist_entries WHERE edition_id=?2)""", (source, target))
    connection.execute("UPDATE watchlist_entries SET edition_id=? WHERE edition_id=?", (target, source))
    connection.execute("""DELETE FROM collected_editions WHERE edition_id=?1
                          AND user_id IN (SELECT user_id FROM collected_editions WHERE edition_id=?2)""", (source, target))
    connection.execute("UPDATE collected_editions SET edition_id=? WHERE edition_id=?", (target, source))
    connection.execute("DELETE FROM editions WHERE id=?", (source,))


def merge_series(connection, source, target):
    """Moves the editions of series `source` to `target` (an edition the target already has is
    merged into it) and the reading statuses (an account's status of the target stays)."""
    for row in connection.execute("SELECT * FROM editions WHERE series_id=?", (source,)).fetchall():
        duplicate = find_edition_duplicate(connection, target, dict(row), exclude_id=row["id"])
        if duplicate:
            merge_editions(connection, row["id"], duplicate[0])
        else:
            connection.execute("UPDATE editions SET series_id=? WHERE id=?", (target, row["id"]))
    connection.execute("""DELETE FROM series_reading WHERE series_id=?1
                          AND user_id IN (SELECT user_id FROM series_reading WHERE series_id=?2)""", (source, target))
    connection.execute("UPDATE series_reading SET series_id=? WHERE series_id=?", (target, source))
    connection.execute("DELETE FROM series WHERE id=?", (source,))


MERGES = {"series": merge_series, "editions": merge_editions, "volumes": merge_volumes}
KIND_NAMES = {"series": "Reihe", "editions": "Ausgabe", "volumes": "Band"}
IN_USE = {"series": series_in_use, "editions": edition_in_use, "volumes": volume_in_use}


@app.post("/api/admin/catalog/merge")
@admin_required
def admin_merge():
    """{kind: series|editions|volumes, source, target}: `source` is merged into `target`."""
    payload = request.get_json(force=True) or {}
    kind = payload.get("kind")
    if kind not in MERGES:
        return jsonify({"error": "Unbekannte Art (series, editions oder volumes)."}), 400
    try:
        source, target = int(payload.get("source")), int(payload.get("target"))
    except (TypeError, ValueError):
        return jsonify({"error": "Quelle und Ziel fehlen."}), 400
    if source == target:
        return jsonify({"error": "Quelle und Ziel sind derselbe Eintrag."}), 400
    connection = db()
    if connection.execute(f"SELECT COUNT(*) FROM {kind} WHERE id IN (?,?)", (source, target)).fetchone()[0] != 2:
        return jsonify({"error": f"{KIND_NAMES[kind]} nicht gefunden."}), 404
    MERGES[kind](connection, source, target)
    connection.commit()
    return jsonify({"merged": True})


@app.delete("/api/admin/catalog/<any(series, editions, volumes):kind>/<int:entry_id>")
@admin_required
def admin_delete_entry(kind, entry_id):
    """An entry nobody uses, with what is under it."""
    connection = db()
    if not connection.execute(f"SELECT 1 FROM {kind} WHERE id=?", (entry_id,)).fetchone():
        return jsonify({"error": f"{KIND_NAMES[kind]} nicht gefunden."}), 404
    if IN_USE[kind](connection, entry_id):
        return jsonify({"error": "Der Eintrag wird noch verwendet; erst zusammenführen."}), 409
    if kind == "series":
        for (edition_id,) in connection.execute("SELECT id FROM editions WHERE series_id=?", (entry_id,)).fetchall():
            connection.execute("DELETE FROM volumes WHERE edition_id=?", (edition_id,))
        connection.execute("DELETE FROM editions WHERE series_id=?", (entry_id,))
    elif kind == "editions":
        connection.execute("DELETE FROM volumes WHERE edition_id=?", (entry_id,))
    connection.execute(f"DELETE FROM {kind} WHERE id=?", (entry_id,))
    connection.commit()
    return jsonify({"deleted": True})


@app.get("/api/admin/oauth")
@admin_required
def admin_get_oauth():
    config = resolve_oauth_config()
    response = {key: value for key, value in config.items() if key != "client_secret"}
    response["client_secret_set"] = bool(config.get("client_secret"))
    response["config_path"] = OAUTH_CONFIG_PATH
    return jsonify(response)


@app.post("/api/admin/oauth")
@admin_required
def admin_save_oauth():
    if Path(OAUTH_CONFIG_PATH).is_file():
        return jsonify({"error": f"OAuth wird über die Config-Datei {OAUTH_CONFIG_PATH} verwaltet und kann hier nicht bearbeitet werden."}), 400
    if resolve_oauth_config()["source"] == "environment":
        return jsonify({"error": "OAuth wird über die Umgebungsvariablen OAUTH_* verwaltet und kann hier nicht bearbeitet werden."}), 400
    p = request.get_json(force=True) or {}
    if p.get("account_matching") not in ("manual", "email", "auto_provision"):
        return jsonify({"error": "Ungültiger Wert für account_matching."}), 400
    row = db().execute("SELECT value FROM app_settings WHERE key='oauth_config'").fetchone()
    current = jload(row["value"], {}) if row else {}
    config = {**OAUTH_CONFIG_DEFAULTS, **current}
    for key in ("enabled",):
        config[key] = bool(p.get(key))
    for key in ("provider_name", "client_id", "discovery_url", "authorize_url", "token_url", "userinfo_url",
                "scopes", "username_claim", "email_claim", "subject_claim", "account_matching"):
        if key in p:
            config[key] = str(p[key] or "").strip()
    # Blank client_secret in the payload means "leave the stored secret unchanged" -- the GET
    # response above never sends the real secret back, so the form field is blank by default
    # and a save that doesn't touch it must not wipe it out.
    if p.get("client_secret"):
        config["client_secret"] = p["client_secret"]
    db().execute(
        "INSERT INTO app_settings(key,value) VALUES('oauth_config',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (json.dumps(config),),
    )
    db().commit()
    return jsonify({"saved": True})
