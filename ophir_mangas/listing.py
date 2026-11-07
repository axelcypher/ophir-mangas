"""What the grids show: editions and volumes as list items, seen by one account, with their filters,
sorts, facets and groups.

An edition's item sums up its volumes for the account: how many numbers it owns (any variant counts
for its number), how many it has read, the gaps when it collects the edition, what comes next and
which cover to show. A volume's item carries its edition's and series' facts, so a flat grid of
volumes filters and searches like the edition grid.

Everything is worked out in Python from a few queries (all editions, their volumes, the account's
rows): a catalogue of some thousand volumes is a few milliseconds, and the rules (released, gaps,
variants) read better here than in SQL.
"""

from collections import defaultdict

from . import search
from .catalog import edition_name, image_fields, is_released, number_label, split_list
from .config import CURRENCY, today_iso
from .prices import market_value_sql

OPEN_PREORDER = ("ordered", "paid", "shipped")
NONE_VALUE = "__none__"   # a filter value that asks for the entries without a value in that field

EDITION_SQL = """SELECT e.*, s.title series_title, s.original_title, s.alt_titles, s.authors, s.genres, s.demographic,
                        s.status series_status, s.image_key series_image_key, s.image_url series_image_url
                 FROM editions e JOIN series s ON s.id=e.series_id"""
VOLUME_SQL = f"""SELECT v.*, e.series_id, e.title edition_title, e.label, e.publisher, e.language, e.format, e.status edition_status,
                        e.volume_count, s.title series_title, s.original_title, s.alt_titles, s.authors, s.genres, s.demographic,
                        {market_value_sql('v.id')} market_value
                 FROM volumes v JOIN editions e ON e.id=v.edition_id JOIN series s ON s.id=e.series_id"""


class Account:
    """What one account has of the catalogue, keyed by volume, edition and series id."""

    def __init__(self, connection, uid):
        self.uid = uid
        self.owned = {}
        for row in connection.execute(
                f"""SELECT c.volume_id, SUM(c.quantity) copies, SUM(c.quantity*COALESCE(c.purchase_price,0)) spent,
                      SUM(c.quantity*COALESCE({market_value_sql('v.id')}, c.purchase_price,
                          CASE WHEN v.currency='{CURRENCY}' THEN v.list_price END, 0)) value,
                      SUM(CASE WHEN c.purchase_price IS NULL THEN c.quantity ELSE 0 END) unpriced,
                      GROUP_CONCAT(DISTINCT c.condition) conditions, GROUP_CONCAT(DISTINCT NULLIF(c.location,'')) locations,
                      MAX(c.first_printing) first_printing, MAX(c.created_at) added_at, MAX(NULLIF(c.purchased_at,'')) purchased_at
                    FROM collection_entries c JOIN volumes v ON v.id=c.volume_id WHERE c.user_id=? GROUP BY c.volume_id""", (uid,)):
            self.owned[row["volume_id"]] = {
                "copies": row["copies"], "spent": round(row["spent"] or 0, 2), "value": round(row["value"] or 0, 2),
                "unpriced": row["unpriced"], "conditions": (row["conditions"] or "").split(",") if row["conditions"] else [],
                "locations": (row["locations"] or "").split(",") if row["locations"] else [],
                "first_printing": bool(row["first_printing"]), "added_at": row["added_at"], "purchased_at": row["purchased_at"] or "",
            }
        self.read = {row[0]: row[1] for row in connection.execute("SELECT volume_id, read_at FROM volume_reads WHERE user_id=?", (uid,))}
        self.preordered = {row[0]: row[1] for row in connection.execute(
            f"SELECT volume_id, SUM(quantity) FROM preorders WHERE user_id=? AND status IN {OPEN_PREORDER} GROUP BY volume_id", (uid,))}
        self.wished_volumes, self.wished_editions = {}, {}
        for row in connection.execute(
                """SELECT we.volume_id, we.edition_id, we.target_price, we.created_at FROM watchlist_entries we
                   JOIN watchlists w ON w.id=we.list_id WHERE w.user_id=?""", (uid,)):
            target = self.wished_volumes if row["volume_id"] else self.wished_editions
            key = row["volume_id"] or row["edition_id"]
            target.setdefault(key, row["target_price"])
        self.collected = {row[0] for row in connection.execute("SELECT edition_id FROM collected_editions WHERE user_id=?", (uid,))}
        self.reading = {row[0]: row[1] for row in connection.execute("SELECT series_id, status FROM series_reading WHERE user_id=?", (uid,))}


def volume_item(row, account, today=None):
    """A volume as the grids and the edition dialog show it."""
    today = today or today_iso()
    owned = account.owned.get(row["id"]) if account else None
    item = {key: row[key] for key in ("id", "edition_id", "series_id", "number", "title", "variant", "isbn", "release_date", "list_price",
                                      "currency", "pages", "created_at", "publisher", "language", "format", "series_title",
                                      "original_title", "alt_titles", "authors", "genres", "demographic", "market_value")}
    item.update(image_fields(row))
    item["number_label"] = number_label(row["number"])
    item["edition_name"] = edition_name({"title": row["edition_title"], "label": row["label"]}, row["series_title"])
    item["released"] = is_released(row["release_date"], today)
    item["owned"] = owned["copies"] if owned else 0
    item["value"] = owned["value"] if owned else 0
    item["spent"] = owned["spent"] if owned else 0
    if owned:
        item.update({key: owned[key] for key in ("conditions", "locations", "first_printing", "added_at", "purchased_at", "unpriced")})
    item["read"] = bool(account and row["id"] in account.read)
    item["read_at"] = account.read.get(row["id"]) if account else None
    item["preordered"] = account.preordered.get(row["id"], 0) if account else 0
    item["wished"] = bool(account and row["id"] in account.wished_volumes)
    return item


def volume_items(connection, account, where="1=1", params=()):
    today = today_iso()
    return [volume_item(row, account, today) for row in connection.execute(f"{VOLUME_SQL} WHERE {where}", params)]


def volume_order(item):
    """Within an edition: by number, the standard volume before its variants, special volumes last."""
    number = item["number"]
    return (number is None, number if number is not None else 0, bool(item["variant"]), search.fold(item["variant"] or item["title"] or ""), item["id"])


def summarize(edition, volumes, account, today):
    """The account's view of one edition from its volumes (list items, any order)."""
    numbered = [volume for volume in volumes if volume["number"] is not None]
    specials = [volume for volume in volumes if volume["number"] is None]
    released_numbers = {volume["number"] for volume in numbered if volume["released"]}
    released_through = int(max(released_numbers, default=0))
    if edition["status"] == "completed" and edition["volume_count"]:
        released_through = max(released_through, edition["volume_count"])
    expected = set(range(1, released_through + 1)) | {number for number in released_numbers if not float(number).is_integer()}
    owned_numbers = {volume["number"] for volume in numbered if volume["owned"]}
    read_numbers = {volume["number"] for volume in numbered if volume["read"]}
    highest = int(max((volume["number"] for volume in numbered), default=0))
    upcoming = sorted((volume for volume in volumes if not volume["released"] and volume["release_date"]),
                      key=lambda volume: (volume["release_date"], volume_order(volume)))
    released_dates = [volume["release_date"] for volume in volumes if volume["released"] and volume["release_date"]]
    ordered = sorted(volumes, key=volume_order)
    pictured = next((volume for volume in ordered if volume["has_image"] and not volume["variant"]), None) \
        or next((volume for volume in ordered if volume["has_image"]), None)
    if pictured:
        cover = {"kind": "volumes", "id": pictured["id"], "version": pictured["image_version"]}
    elif edition["series_image_key"] or edition["series_image_url"]:
        cover = {"kind": "series", "id": edition["series_id"], "version": (edition["series_image_key"] or "")[:12]}
    else:
        cover = None
    collecting = bool(account and edition["id"] in account.collected)
    gaps = sorted(expected - owned_numbers)
    return {
        "catalogued": len({volume["number"] for volume in numbered}), "specials": len(specials), "highest": highest,
        "released_through": released_through, "total": edition["volume_count"] or highest,
        "owned": len(owned_numbers) + sum(1 for volume in specials if volume["owned"]),
        "owned_numbers": len(owned_numbers),
        "copies": sum(volume["owned"] for volume in volumes),
        "read": len(read_numbers) + sum(1 for volume in specials if volume["read"]),
        "read_numbers": len(read_numbers),
        "unread_owned": sum(1 for volume in volumes if volume["owned"] and not volume["read"]),
        "gaps": [number_label(number) for number in gaps] if collecting else [],
        "gap_count": len(gaps) if collecting else 0,
        "complete": bool(expected) and not gaps and edition["status"] == "completed" and released_through == (edition["volume_count"] or highest),
        "next_release": {"id": upcoming[0]["id"], "number_label": upcoming[0]["number_label"], "release_date": upcoming[0]["release_date"]}
                        if upcoming else None,
        "latest_release": max(released_dates, default=""),
        "cover": cover,
        "value": round(sum(volume["value"] for volume in volumes), 2),
        "spent": round(sum(volume["spent"] for volume in volumes), 2),
        "preordered": sum(volume["preordered"] for volume in volumes),
        "wished": bool(account and (edition["id"] in account.wished_editions or any(volume["wished"] for volume in volumes))),
        "edition_wished": bool(account and edition["id"] in account.wished_editions),
        "collecting": collecting,
        "isbns": " ".join(volume["isbn"] for volume in volumes if volume["isbn"]),
    }


EDITION_COLUMNS = ("id", "series_id", "title", "label", "publisher", "language", "format", "status", "volume_count", "list_price", "currency",
                   "description", "source_url", "created_at", "series_title", "original_title", "alt_titles", "authors", "genres",
                   "demographic", "series_status")


def edition_items(connection, account, where="1=1", params=(), with_volumes=False):
    """Editions as list items (EDITION_COLUMNS, the summary, `name`, `reading_status`); with
    with_volumes, each also has its `volumes` in order."""
    today = today_iso()
    editions = connection.execute(f"{EDITION_SQL} WHERE {where}", params).fetchall()
    if not editions:
        return []
    by_edition = defaultdict(list)
    ids = [row["id"] for row in editions]
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        for item in volume_items(connection, account, f"v.edition_id IN ({','.join('?' for _ in chunk)})", chunk):
            by_edition[item["edition_id"]].append(item)
    items = []
    for row in editions:
        volumes = by_edition.get(row["id"], [])
        item = {key: row[key] for key in EDITION_COLUMNS}
        item["edition_title"] = row["title"]
        item["name"] = edition_name(row, row["series_title"])
        item.update(summarize(row, volumes, account, today))
        item["reading_status"] = account.reading.get(row["series_id"], "") if account else ""
        if with_volumes:
            item["volumes"] = sorted(volumes, key=volume_order)
        items.append(item)
    return items


# ---- Filters, sorts, facets, groups ------------------------------------------------------------

# Value filters: an item matches when the field equals the wanted value; list fields (authors,
# genres) when the value is one of their entries.
VALUE_FILTERS = {"language": "language", "publisher": "publisher", "format": "format", "demographic": "demographic",
                 "status": "status", "series": "series_title"}
LIST_FILTERS = {"author": "authors", "genre": "genres"}
FACETS = ("language", "publisher", "format", "author", "genre", "demographic", "status")
FIELD_OF = {**VALUE_FILTERS, **LIST_FILTERS}


def values_of(item, facet):
    field = FIELD_OF[facet]
    if facet in LIST_FILTERS:
        return split_list(item.get(field))
    value = item.get(field)
    return [value] if value else []


def apply_filters(items, args, kind="edition"):
    """The filters every grid shares, on list items of editions or volumes."""
    for facet in FIELD_OF:
        wanted = str(args.get(facet) or "").strip()
        if wanted == NONE_VALUE:
            items = [item for item in items if not values_of(item, facet)]
        elif wanted:
            items = [item for item in items if wanted in values_of(item, facet)]
    reading = str(args.get("reading") or "").strip()
    if reading:
        items = [item for item in items if (item.get("reading_status") or "none") == reading]
    query = str(args.get("q") or "").strip()
    if query:
        fields_of = search.edition_fields if kind == "edition" else search.volume_fields
        scored = [(search.query(query).score(fields_of(item)), item) for item in items]
        items = [item for score, item in scored if score > 0]
    return items


EDITION_MODES = {
    "all": lambda item: True,
    "owned": lambda item: item["owned"] > 0,
    "missing": lambda item: item["owned"] == 0,
    "collecting": lambda item: item["collecting"],
    "gaps": lambda item: item["gap_count"] > 0,
    "complete": lambda item: item["complete"] and item["owned_numbers"] >= item["released_through"] > 0,
    "wished": lambda item: item["wished"],
    "preordered": lambda item: item["preordered"] > 0,
    "unread": lambda item: item["unread_owned"] > 0,
}
VOLUME_MODES = {
    "all": lambda item: True,
    "owned": lambda item: item["owned"] > 0,
    "missing": lambda item: item["owned"] == 0,
    "read": lambda item: item["read"],
    "unread": lambda item: item["owned"] > 0 and not item["read"],
    "wished": lambda item: item["wished"],
    "preordered": lambda item: item["preordered"] > 0,
    "upcoming": lambda item: not item["released"],
}


def by_mode(items, mode, modes):
    return [item for item in items if modes.get(mode, modes["all"])(item)]


def title_key(item):
    return (search.fold(item.get("series_title") or ""), search.fold(item.get("name") or item.get("edition_name") or ""), item["id"])


EDITION_SORTS = {
    "title": (title_key, False),
    "added": (lambda item: (item["created_at"], item["id"]), True),
    "release": (lambda item: (item["latest_release"], item["id"]), True),
    "next": (lambda item: ((item["next_release"] or {}).get("release_date") or "9999", item["id"]), False),
    "progress": (lambda item: ((item["owned_numbers"] / item["total"]) if item["total"] else 0, item["owned"], item["id"]), True),
    "value": (lambda item: (item["value"], item["id"]), True),
    "publisher": (lambda item: (not item["publisher"], search.fold(item["publisher"] or ""), title_key(item)), False),
}
VOLUME_SORTS = {
    "title": (lambda item: (search.fold(item["series_title"]), search.fold(item["edition_name"]), item["edition_id"], volume_order(item)), False),
    "release": (lambda item: (item["release_date"] or "0000", item["id"]), True),
    "added": (lambda item: (item.get("added_at") or item["created_at"], item["id"]), True),
    "value": (lambda item: (item["market_value"] if item["market_value"] is not None else (item["value"] or -1), item["id"]), True),
}


def sort_items(items, sort, direction, sorts, default):
    key, descending = sorts.get(sort) or sorts[default]
    if direction in ("asc", "desc"):
        descending = direction == "desc"
    if sort == "publisher":   # entries without a publisher stay last either way
        with_value = sorted((item for item in items if item["publisher"]), key=key, reverse=descending)
        return with_value + sorted((item for item in items if not item["publisher"]), key=title_key)
    return sorted(items, key=key, reverse=descending)


def facets(items):
    """For the filter menus: every value of the grid's entries with how often it occurs."""
    counts = {facet: defaultdict(int) for facet in FACETS}
    for item in items:
        for facet in FACETS:
            for value in values_of(item, facet):
                counts[facet][value] += 1
    return {facet: sorted(([value, count] for value, count in values.items()), key=lambda pair: (-pair[1], search.fold(pair[0])))
            for facet, values in counts.items()}


# The kinds of groups the edition grids can show, side by side: ?group=<kind>.
GROUPINGS = {"series": "Reihe", "publisher": "Verlag", "author": "Autor:in", "genre": "Genre", "language": "Sprache",
             "demographic": "Zielgruppe"}
GROUP_FIELDS = {"series": "series_title", "publisher": "publisher", "language": "language", "demographic": "demographic",
                "author": "authors", "genre": "genres"}
GROUP_SORTS = ("name", "count", "owned", "value", "release")
GROUP_SAMPLES = 4


def group_keys(item, by):
    if by in ("author", "genre"):
        return split_list(item.get(GROUP_FIELDS[by])) or [""]
    return [item.get(GROUP_FIELDS[by]) or ""]


def group_items(items, by, sort="name"):
    """Editions grouped by one field (GROUPINGS): per group how many editions, how many of them the
    account has volumes of, its volumes, value, latest release and up to four covers. An edition
    with several authors or genres is in each of their groups. The group without a value (name "")
    comes last whatever the order."""
    groups = {}
    for item in items:
        for name in group_keys(item, by):
            group = groups.get(name)
            if group is None:
                group = groups[name] = {"name": name, "count": 0, "owned": 0, "volumes": 0, "copies": 0, "read": 0, "gaps": 0,
                                        "collecting": 0, "wished": 0, "value": 0.0, "spent": 0.0, "latest_release": "", "samples": []}
            group["count"] += 1
            group["owned"] += 1 if item["owned"] else 0
            group["volumes"] += item["owned"]
            group["copies"] += item["copies"]
            group["read"] += item["read"]
            group["gaps"] += item["gap_count"]
            group["collecting"] += 1 if item["collecting"] else 0
            group["wished"] += 1 if item["wished"] else 0
            group["value"] += item["value"]
            group["spent"] += item["spent"]
            group["latest_release"] = max(group["latest_release"], item["latest_release"])
            group["samples"].append(item)
    result = []
    for group in groups.values():
        samples = group.pop("samples")
        pictured = [item for item in samples if item["cover"]]
        plain = [item for item in samples if not item["cover"]]
        group["samples"] = [{"id": item["id"], "name": item["name"], "cover": item["cover"], "series_id": item["series_id"]}
                            for item in (pictured + plain)[:GROUP_SAMPLES]]
        group.update(value=round(group["value"], 2), spent=round(group["spent"], 2))
        result.append(group)
    result.sort(key=lambda group: search.fold(group["name"]))
    if sort == "count":
        result.sort(key=lambda group: group["count"], reverse=True)
    elif sort == "owned":
        result.sort(key=lambda group: (group["owned"] / group["count"], group["count"]), reverse=True)
    elif sort == "value":
        result.sort(key=lambda group: group["value"], reverse=True)
    elif sort == "release":
        result.sort(key=lambda group: group["latest_release"], reverse=True)
    result.sort(key=lambda group: not group["name"])
    return result


def grouped(args, items):
    """The editions in groups when the request asks for them (?group=<kind>&group_sort=...), else
    None. Groups are made after the grid's filters and sort, so their covers follow it."""
    if args.get("group") not in GROUPINGS:
        return None
    return {"group": args["group"], "groups": group_items(items, args["group"], args.get("group_sort", "name"))}


def edition_stats(items):
    return {
        "editions": len(items),
        "series": len({item["series_id"] for item in items}),
        "volumes": sum(item["owned"] for item in items),
        "copies": sum(item["copies"] for item in items),
        "read": sum(item["read"] for item in items),
        "unread": sum(item["unread_owned"] for item in items),
        "gaps": sum(item["gap_count"] for item in items),
        "value": round(sum(item["value"] for item in items), 2),
        "spent": round(sum(item["spent"] for item in items), 2),
    }


def volume_stats(items):
    return {
        "volumes": len(items),
        "copies": sum(item["owned"] for item in items),
        "read": sum(1 for item in items if item["read"]),
        "value": round(sum(item["value"] for item in items), 2),
        "spent": round(sum(item["spent"] for item in items), 2),
        "unpriced": sum(item.get("unpriced", 0) for item in items),
    }
