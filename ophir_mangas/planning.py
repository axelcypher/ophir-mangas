"""Gaps and the release calendar of the editions an account collects ("Sammle ich").

- A gap is a number of a collected edition that has been released and that the account owns in no
  variant (listing.summarize). The catalogue may lack the volume itself (a number between two that
  are there, or below the count of a completed edition); such a gap has no volume to open.
- The calendar lists the volumes due from the start of last month on, of the collected editions
  and of what is on the account's wishlists, by month, and what came out lately and is not owned.
"""

from datetime import date, timedelta

from flask import jsonify, request

from .config import today_iso
from .listing import Account, edition_items, volume_items, volume_order
from .web import app, db, login_required, user_id

RECENT_DAYS = 45


def gap_overview(connection, uid):
    account = Account(connection, uid)
    if not account.collected:
        return []
    ids = sorted(account.collected)
    editions = edition_items(connection, account, f"e.id IN ({','.join('?' for _ in ids)})", ids, with_volumes=True)
    result = []
    for edition in editions:
        if not edition["gap_count"]:
            continue
        volumes_by_number = {}
        for volume in sorted(edition["volumes"], key=volume_order):
            if volume["number"] is not None:
                volumes_by_number.setdefault(volume["number_label"], volume)
        gaps = [{"number_label": label, "volume": volumes_by_number.get(label)} for label in edition["gaps"]]
        result.append({key: edition[key] for key in ("id", "name", "series_id", "series_title", "publisher", "language", "format", "status",
                                                     "total", "owned", "owned_numbers", "released_through", "cover", "list_price", "currency")}
                      | {"gaps": gaps, "gap_count": edition["gap_count"]})
    result.sort(key=lambda item: (-item["gap_count"], item["name"].lower()))
    return result


@app.get("/api/gaps")
@login_required
def get_gaps():
    items = gap_overview(db(), user_id())
    estimate = sum((gap["volume"] or {}).get("list_price") or item["list_price"] or 0
                   for item in items for gap in item["gaps"] if (gap["volume"] or {}).get("currency", item["currency"]) == "EUR")
    return jsonify({"editions": items, "stats": {"editions": len(items), "gaps": sum(item["gap_count"] for item in items),
                                                 "uncatalogued": sum(1 for item in items for gap in item["gaps"] if not gap["volume"]),
                                                 "estimate": round(estimate, 2)}})


def month_start(day, months_back=0):
    """The first day of the month `months_back` months before `day` (negative: after)."""
    year, month = divmod(day.year * 12 + day.month - 1 - months_back, 12)
    return date(year, month + 1, 1)


def calendar(connection, uid, months=6):
    account = Account(connection, uid)
    today = date.fromisoformat(today_iso())
    start = month_start(today, 1).isoformat()
    end_month = month_start(today, -months)
    end = end_month.isoformat()[:7]
    recent_from = (today - timedelta(days=RECENT_DAYS)).isoformat()
    edition_ids = sorted(account.collected | set(account.wished_editions))
    conditions, params = [], []
    if edition_ids:
        conditions.append(f"v.edition_id IN ({','.join('?' for _ in edition_ids)})")
        params += edition_ids
    if account.wished_volumes:
        wished = sorted(account.wished_volumes)
        conditions.append(f"v.id IN ({','.join('?' for _ in wished)})")
        params += wished
    if not conditions:
        return {"months": [], "recent": [], "undated": 0}
    items = volume_items(connection, account, f"({' OR '.join(conditions)}) AND v.release_date!='' AND v.release_date>=? AND substr(v.release_date,1,7)<=?",
                         [*params, start, end])
    for item in items:
        item["collecting"] = item["edition_id"] in account.collected
    upcoming = sorted((item for item in items if not item["released"]), key=lambda item: (item["release_date"], item["series_title"].lower(), volume_order(item)))
    recent = sorted((item for item in items if item["released"] and not item["owned"] and item["release_date"] >= recent_from[:len(item["release_date"])]),
                    key=lambda item: item["release_date"], reverse=True)
    months_list = []
    for item in upcoming:
        month = item["release_date"][:7]
        if not months_list or months_list[-1]["month"] != month:
            months_list.append({"month": month, "volumes": []})
        months_list[-1]["volumes"].append(item)
    undated = connection.execute(
        f"SELECT COUNT(*) FROM volumes v WHERE ({' OR '.join(conditions)}) AND v.release_date=''", params).fetchone()[0] if conditions else 0
    return {"months": months_list, "recent": recent, "undated": undated}


@app.get("/api/calendar")
@login_required
def get_calendar():
    months = max(1, min(24, request.args.get("months", 6, type=int)))
    return jsonify(calendar(db(), user_id(), months))


def dashboard_planning(uid):
    connection = db()
    gaps = gap_overview(connection, uid)
    upcoming = calendar(connection, uid, 3)
    return {"gaps": sum(item["gap_count"] for item in gaps), "gap_editions": len(gaps),
            "upcoming": [volume for month in upcoming["months"] for volume in month["volumes"]][:8], "recent": upcoming["recent"][:6]}

