"""Scout's tables in Postgres (the same Supabase project as Tally and Relay, schema "scout").

    python -m scout.db        create the tables (safe to run again; keeps existing runs)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .llm import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def connect(url: str | None = None, **kw):
    import psycopg
    return psycopg.connect(url or os.environ["DATABASE_URL"], autocommit=True, prepare_threshold=None, **kw)


def setup(url: str | None = None) -> None:
    with connect(url) as conn:
        conn.execute((ROOT / "sql" / "scout.sql").read_text(encoding="utf-8"))


if __name__ == "__main__":
    load_dotenv()
    if not os.environ.get("DATABASE_URL"):
        sys.exit("DATABASE_URL is not set. Add it to .env (the same value as in Relay's .env).")
    setup()
    print("Scout's tables are ready.")
