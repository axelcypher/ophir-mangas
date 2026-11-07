"""The page shell, what the app loads first (bootstrap) and the dashboard's data."""

from flask import jsonify, render_template

from . import config
from .auth import resolve_oauth_config
from .catalog import DEMOGRAPHICS, FORMATS, LANGUAGES, STATUSES
from .collection import CONDITIONS, dashboard_collection
from .config import CURRENCY, jload
from .planning import dashboard_planning
from .preorders import STATUSES as PREORDER_STATUSES, dashboard_preorders
from .reading import READING_STATUSES, reading_overview
from .shared_auth import auth_base
from .watchlists import lists_of
from .web import app, db, login_required, user_id


@app.get("/")
@login_required
def index():
    return render_template("index.html")


def counts(uid):
    connection = db()
    return {
        "collection": connection.execute(
            """SELECT COUNT(*) FROM (SELECT v.edition_id FROM collection_entries c JOIN volumes v ON v.id=c.volume_id
               WHERE c.user_id=?1 GROUP BY v.edition_id UNION SELECT edition_id FROM collected_editions WHERE user_id=?1)""", (uid,)).fetchone()[0],
        "volumes": connection.execute("SELECT COUNT(DISTINCT volume_id) FROM collection_entries WHERE user_id=?", (uid,)).fetchone()[0],
        "wished": connection.execute(
            "SELECT COUNT(*) FROM watchlist_entries we JOIN watchlists w ON w.id=we.list_id WHERE w.user_id=?", (uid,)).fetchone()[0],
        "preorders": connection.execute(
            "SELECT COUNT(*) FROM preorders WHERE user_id=? AND status IN ('ordered','paid','shipped')", (uid,)).fetchone()[0],
        "reading": connection.execute("SELECT COUNT(*) FROM series_reading WHERE user_id=? AND status='reading'", (uid,)).fetchone()[0],
        "collecting": connection.execute("SELECT COUNT(*) FROM collected_editions WHERE user_id=?", (uid,)).fetchone()[0],
        "catalog": connection.execute("SELECT COUNT(*) FROM editions").fetchone()[0],
    }


@app.get("/api/bootstrap")
@login_required
def bootstrap():
    uid = user_id()
    current = db().execute("SELECT id,username,display_name,role,email,oauth_subject,password_hash FROM users WHERE id=?", (uid,)).fetchone()
    settings = {row["key"]: jload(row["value"], row["value"]) for row in db().execute("SELECT key,value FROM user_settings WHERE user_id=?", (uid,))}
    user_payload = {key: current[key] for key in ("id", "username", "display_name", "role", "email")}
    user_payload["oauth_linked"] = bool(current["oauth_subject"])
    user_payload["password_set"] = bool(current["password_hash"])
    oauth_config = resolve_oauth_config()
    imports = [dict(row) for row in db().execute("SELECT id,created_at,undone_at FROM import_operations WHERE user_id=? ORDER BY id DESC LIMIT 4", (uid,))]
    return jsonify({
        "user": user_payload, "settings": settings, "counts": counts(uid), "watchlists": lists_of(uid), "imports": imports,
        "oauth": {"enabled": oauth_config["enabled"], "provider_name": oauth_config["provider_name"]},
        # Shared sign-in of the Ophir apps: in slave mode accounts, passwords and SSO are the master's.
        "auth": {"mode": config.AUTH_MODE, "base": auth_base()},
        "conditions": CONDITIONS, "statuses": PREORDER_STATUSES, "reading_statuses": READING_STATUSES, "languages": LANGUAGES,
        "series_statuses": STATUSES, "demographics": DEMOGRAPHICS, "formats": list(FORMATS), "currency": CURRENCY,
    })


@app.get("/api/dashboard")
@login_required
def dashboard():
    uid = user_id()
    reading = [item for item in reading_overview(db(), uid) if item["status"] == "reading"][:8]
    return jsonify({"collection": dashboard_collection(uid), "preorders": dashboard_preorders(uid), "planning": dashboard_planning(uid),
                    "reading": reading, "counts": counts(uid)})
