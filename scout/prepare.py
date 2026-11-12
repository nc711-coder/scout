"""Build the sample run everyone sees on the page: the 38 tested businesses, researched from the saved
snapshot (no Tavily credits; about 5 minutes of AI calls).

    python -m scout.prepare
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from . import db
from .llm import GroqJSON, load_dotenv
from .runs import create, work
from .web import SnapshotWeb

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    load_dotenv()
    snap = ROOT / "snapshots" / "evals.json"
    if not snap.exists():
        sys.exit("snapshots/evals.json is missing: run  python -m evals.run --record  first.")
    sys.path.insert(0, str(ROOT))
    from evals.companies import COMPANIES, HOLDOUT
    db.setup()
    companies = [{k: c[k] for k in ("name", "website", "city")} for c in COMPANIES + HOLDOUT]
    with db.connect() as conn:
        rid = create(conn, companies, kind="sample", title="Sample run: 38 cafés, bakeries, roasters and chains")
    print(f"Researching {len(companies)} businesses from the snapshot (run {rid})...")
    t = time.perf_counter()
    web, llm = SnapshotWeb(snap), GroqJSON()
    work(rid, db.connect, web, llm)
    count = "select count(*) filter (where status = 'failed') from scout.leads where run_id = %s"
    with db.connect() as conn:
        failed = conn.execute(count, (rid,)).fetchone()[0]
    if failed:                                   # usually a one-off malformed AI answer: try those again once
        print(f"Retrying {failed} that failed...")
        work(rid, db.connect, web, llm)
        with db.connect() as conn:
            failed = conn.execute(count, (rid,)).fetchone()[0]
    with db.connect() as conn:                   # replace the old sample only now, so the page is never empty
        conn.execute("delete from scout.runs where kind = 'sample' and id <> %s", (rid,))
    print(f"Done in {time.perf_counter() - t:.0f}s: {len(companies) - failed} researched, {failed} failed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
