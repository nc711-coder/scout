"""Batch runs: a list of businesses, researched one after another in the background, with progress saved
after every step so the page can show it.

    run_id = create(conn, companies, kind="visitor", visitor="...")
    work(run_id, connect, web, llm)          # usually in a background thread
"""
from __future__ import annotations

import csv
import io
import json
import logging
import time

from .lead import lead
from .llm import LLMError
from .web import WebError

log = logging.getLogger("scout")


def create(conn, companies: list[dict], kind: str, visitor: str | None = None, title: str = "") -> int:
    rid = conn.execute("insert into scout.runs (kind, visitor, title) values (%s, %s, %s) returning id",
                       (kind, visitor, title)).fetchone()[0]
    with conn.cursor() as cur:
        cur.executemany("insert into scout.leads (run_id, position, name, website, city) values (%s, %s, %s, %s, %s)",
                        [(rid, i, c["name"], c.get("website") or "", c.get("city") or "") for i, c in enumerate(companies)])
    return rid


def work(run_id: int, connect, web, llm) -> None:
    """Research every lead in the run, in order. One business failing doesn't stop the others."""
    with connect() as conn:
        conn.execute("update scout.runs set status = 'running' where id = %s", (run_id,))
        rows = conn.execute("select id, name, website, city from scout.leads where run_id = %s and status <> 'done' "
                            "order by position", (run_id,)).fetchall()
    for n, (lid, name, website, city) in enumerate(rows):
        if n:
            time.sleep(1.0)                                 # spread the AI calls out (Groq's rate limit)
        with connect() as conn:
            def progress(stage: str, lid=lid, conn=conn):
                conn.execute("update scout.leads set status = 'running', stage = %s, updated_at = now() where id = %s",
                             (stage, lid))
            progress("Starting")
            try:
                x = lead({"name": name, "website": website, "city": city}, web, llm, progress)
                conn.execute("""update scout.leads set status = 'done', stage = '', score = %s, tier = %s, opener = %s,
                                result = %s, error = null, updated_at = now() where id = %s""",
                             (x["fit"]["score"], x["fit"]["tier"], x["opener"].get("line") or None,
                              json.dumps(x, ensure_ascii=False), lid))
            except (WebError, LLMError) as e:
                conn.execute("update scout.leads set status = 'failed', stage = '', error = %s, updated_at = now() "
                             "where id = %s", (str(e)[:300], lid))
            except Exception as e:                         # a bug shouldn't leave the lead "running" forever
                log.exception("lead %s failed", lid)
                conn.execute("update scout.leads set status = 'failed', stage = '', error = %s, updated_at = now() "
                             "where id = %s", (f"Something went wrong ({type(e).__name__}).", lid))
    with connect() as conn:
        conn.execute("update scout.runs set status = 'done', finished_at = now() where id = %s", (run_id,))


def as_csv(run_title: str, leads: list[dict]) -> str:
    """One row per business, for Google Sheets or Excel."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Business", "Website", "City", "Score", "Fit", "First line", "First line based on", "Why",
                "Unknown", "Checked facts (with sources)", "Status"])
    for x in leads:
        r = x.get("result") or {}
        f, o = r.get("fit") or {}, r.get("opener") or {}
        why = "; ".join(f"{p['why']} ({p['points']:+d})" for p in f.get("reasons") or [])
        facts = "\n".join(f"{y['fact']} [{y['url']}]" for y in r.get("facts") or [])
        w.writerow([x["name"], x["website"], x["city"], x.get("score") if x.get("score") is not None else "",
                    x.get("tier") or "", o.get("line") or "", o.get("url") or "", why,
                    ", ".join(f.get("unknown") or []), facts, x.get("error") or x["status"]])
    return "﻿" + out.getvalue()          # the mark tells Excel it's UTF-8 (cafés keep their accents)
