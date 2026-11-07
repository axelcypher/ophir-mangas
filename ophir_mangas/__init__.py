"""Ophir Mangas: a self-hosted collection manager for manga.

Importing the package builds the whole application: every module registers its routes on the one
Flask app, then the database is created or migrated. `app.py` in the repository root is the entry
point servers and scripts import.
"""
from . import config, web, schema  # noqa: F401  -- the order is the dependency order
from . import (prices, images, catalog, listing, series, editions, volumes, reading, planning, collection, watchlists,  # noqa: F401
               preorders, lookup, link_import, backup, auth, account, admin, pages, public_profile)
from .web import app

schema.init_database()

__all__ = ["app"]
