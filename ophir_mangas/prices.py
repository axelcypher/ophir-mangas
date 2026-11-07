"""Market values of volumes: entered by hand for the volumes where it matters (out of print, a
Limited Edition), shared by every account, kept as a history. The newest value is the current one.

A copy in a collection is worth its volume's current market value; without one, what was paid
for it; without that, the volume's list price when it is in euros (collection_value_sql).
"""

import re

from flask import jsonify, request

from .config import CURRENCY, now_iso
from .web import app, db, login_required, user_id

PRICE_LIMIT = 1_000_000


def market_value_sql(volume_column="v.id"):
    """The current market value of the volume in `volume_column`, as a correlated subquery."""
    return (f"(SELECT po.amount FROM price_observations po WHERE po.volume_id={volume_column} "
            "ORDER BY po.observed_at DESC, po.id DESC LIMIT 1)")


def collection_value_sql(entry="c", volume="v"):
    """What one collection row is worth: copies times the market value, else times the purchase
    price, else times the list price in euros. `volume` is the joined volumes row."""
    return (f"({entry}.quantity * COALESCE({market_value_sql(f'{volume}.id')}, {entry}.purchase_price, "
            f"CASE WHEN {volume}.currency='{CURRENCY}' THEN {volume}.list_price END, 0))")


def parse_amount(value, field="Betrag", allow_none=True):
    """A money amount from a form, typed as Germans and others do: 189,90 / 189.90 / 1.299,00 /
    1,299.00 / 19.800 (thousands, as yen prices are written). (value, error)."""
    if value in (None, ""):
        return (None, None) if allow_none else (None, f"{field} fehlt.")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        text = repr(float(value))
    else:
        text = re.sub(r"[\s€¥$£]|EUR|JPY|USD", "", str(value), flags=re.I)
        if re.fullmatch(r"-?\d{1,3}([.,]\d{3})+", text):                  # 19.800 / 1,299: groups of thousands
            text = re.sub(r"[.,]", "", text)
        elif "," in text and "." in text:                                   # the last mark is the decimal one
            text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
        else:
            text = text.replace(",", ".")
    try:
        amount = round(float(text), 2)
    except ValueError:
        return None, f"{field} ist keine Zahl."
    if amount != amount or amount in (float("inf"), float("-inf")):
        return None, f"{field} ist keine Zahl."
    if amount < 0 or amount > PRICE_LIMIT:
        return None, f"{field} liegt außerhalb des erlaubten Bereichs."
    return amount, None


def price_history(volume_id):
    return [dict(row) for row in db().execute(
        """SELECT po.id,po.amount,po.currency,po.source,po.note,po.observed_at,u.display_name author
           FROM price_observations po LEFT JOIN users u ON u.id=po.user_id
           WHERE po.volume_id=? ORDER BY po.observed_at DESC, po.id DESC""", (volume_id,))]


def record_price(connection, volume_id, amount, source="manual", note="", uid=None, observed_at=None):
    connection.execute(
        "INSERT INTO price_observations(volume_id,amount,currency,source,note,user_id,observed_at) VALUES(?,?,?,?,?,?,?)",
        (volume_id, amount, CURRENCY, source, note, uid, observed_at or now_iso()),
    )


def volume_exists(volume_id):
    return db().execute("SELECT 1 FROM volumes WHERE id=?", (volume_id,)).fetchone() is not None


@app.get("/api/volumes/<int:volume_id>/prices")
@login_required
def volume_prices(volume_id):
    if not volume_exists(volume_id):
        return jsonify({"error": "Band nicht gefunden."}), 404
    return jsonify(price_history(volume_id))


@app.post("/api/volumes/<int:volume_id>/prices")
@login_required
def add_volume_price(volume_id):
    if not volume_exists(volume_id):
        return jsonify({"error": "Band nicht gefunden."}), 404
    payload = request.get_json(force=True) or {}
    amount, error = parse_amount(payload.get("amount"), "Marktwert", allow_none=False)
    if error:
        return jsonify({"error": error}), 400
    note = str(payload.get("note") or "").strip()[:200]
    record_price(db(), volume_id, amount, "manual", note, user_id())
    db().commit()
    return jsonify(price_history(volume_id)), 201


@app.delete("/api/volumes/<int:volume_id>/prices/<int:price_id>")
@login_required
def delete_volume_price(volume_id, price_id):
    deleted = db().execute("DELETE FROM price_observations WHERE id=? AND volume_id=?", (price_id, volume_id)).rowcount
    if not deleted:
        return jsonify({"error": "Wert nicht gefunden."}), 404
    db().commit()
    return jsonify(price_history(volume_id))
