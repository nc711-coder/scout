"""The web API behind Scout's page.

    uvicorn scout.app:app --reload           then http://127.0.0.1:8000/docs

    GET    /api/runs                 the sample run, plus the runs this visitor started
    GET    /api/runs/{id}            one run with every lead's status, stage, score and first line
    POST   /api/runs                 start a run: {"companies": [{"name", "website", "city"}, ...]} (up to 5)
    DELETE /api/runs/{id}            delete one of your own runs
    GET    /api/runs/{id}/csv        the run as a CSV file (opens in Google Sheets or Excel)
    GET    /api/leads/{id}           one lead in full: facts with quotes and sources, score breakdown, first line
    GET    /health

Visitors are told apart by an X-Visitor header (a random id the page keeps); the sample run is shown to
everyone. Limits protect the Tavily credits: MAX_PER_RUN (5), RUNS_PER_HOUR per visitor (3), LEADS_PER_DAY
overall (40).
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import defaultdict, deque
from datetime import date

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, field_validator

from . import db
from .llm import load_dotenv
from .runs import as_csv, create, work

load_dotenv()
log = logging.getLogger("scout")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app):
    tidy_up()
    yield


origins = [o.strip().rstrip("/") for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app = FastAPI(title="Scout", version="1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "DELETE"], allow_headers=["*"])

MAX_PER_RUN = int(os.environ.get("MAX_PER_RUN") or 5)
VISITOR = re.compile(r"^[A-Za-z0-9-]{8,64}$")
SITE = re.compile(r"^(https?://)?([a-z0-9-]+\.)+[a-z]{2,}(/\S*)?$", re.I)


def visitor_id(x: str | None) -> str | None:
    return x if x and VISITOR.match(x) else None


class Company(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    website: str = Field(default="", max_length=200)
    city: str = Field(default="", max_length=60)

    @field_validator("name", "website", "city")
    @classmethod
    def strip(cls, v: str) -> str:
        return " ".join(v.split())

    @field_validator("website")
    @classmethod
    def looks_like_a_site(cls, v: str) -> str:
        if v and not SITE.match(v):
            raise ValueError(f"\"{v}\" doesn't look like a website address")
        return v


class NewRun(BaseModel):
    companies: list[Company] = Field(min_length=1)


class Limits:
    def __init__(self):
        self.per_hour = int(os.environ.get("RUNS_PER_HOUR") or 3)
        self.per_day = int(os.environ.get("LEADS_PER_DAY") or 40)
        self.seen: dict[str, deque] = defaultdict(deque)
        self.day, self.count = date.today(), 0
        self.lock = threading.Lock()

    def allow(self, who: str, n: int) -> str | None:
        now = time.time()
        with self.lock:
            if date.today() != self.day:
                self.day, self.count = date.today(), 0
            if self.count + n > self.per_day:
                return "The demo has researched its businesses for today. Please try again tomorrow."
            q = self.seen[who]
            while q and now - q[0] > 3600:
                q.popleft()
            if len(q) >= self.per_hour:
                return f"The demo allows {self.per_hour} runs an hour. Please wait a little and try again."
            q.append(now)
            self.count += n
        return None


limits = Limits()
_tools = None
_tools_lock = threading.Lock()


def tools():
    """The live web and the AI, created on first use (so the API starts even before keys are set)."""
    global _tools
    with _tools_lock:
        if _tools is None:
            from .llm import GroqJSON
            from .web import TavilyWeb
            _tools = (TavilyWeb(), GroqJSON())
    return _tools


def start_worker(run_id: int) -> None:
    web, llm = tools()
    threading.Thread(target=work, args=(run_id, db.connect, web, llm), daemon=True).start()


def tidy_up() -> None:
    """Leads left 'running' by a restart can't finish: mark them, so the page doesn't wait forever."""
    try:
        db.setup()
        with db.connect() as conn:
            conn.execute("""update scout.leads set status = 'failed', stage = '', error = 'Interrupted by a server restart.'
                            where status in ('queued', 'running') and updated_at < now() - interval '10 minutes'""")
            conn.execute("""update scout.runs r set status = 'done', finished_at = now() where status <> 'done' and not exists
                            (select 1 from scout.leads l where l.run_id = r.id and l.status in ('queued', 'running'))""")
    except Exception:
        log.exception("couldn't tidy up on startup")


RUN_COLS = "id, kind, title, status, created_at, finished_at"
LEAD_COLS = "id, position, name, website, city, status, stage, score, tier, opener, error"


def run_row(conn, run_id: int, v: str | None) -> dict:
    row = conn.execute(f"select {RUN_COLS}, visitor from scout.runs where id = %s", (run_id,)).fetchone()
    if not row or (row[1] == "visitor" and row[-1] != v):
        raise HTTPException(404, "No such run.")
    return dict(zip(RUN_COLS.split(", "), row[:-1])) | {"mine": row[1] == "visitor"}


def leads_of(conn, run_id: int, full: bool = False) -> list[dict]:
    cols = LEAD_COLS + (", result" if full else ", result->'fit'->'reasons', jsonb_array_length(coalesce(result->'facts', '[]'))")
    rows = conn.execute(f"select {cols} from scout.leads where run_id = %s order by position", (run_id,)).fetchall()
    keys = LEAD_COLS.split(", ") + (["result"] if full else ["reasons", "facts"])
    return [dict(zip(keys, r)) for r in rows]


def summary(conn, run: dict) -> dict:
    n = conn.execute("""select count(*), count(*) filter (where status in ('done', 'failed')),
                               count(*) filter (where score >= 70), count(*) filter (where score >= 45 and score < 70)
                        from scout.leads where run_id = %s""", (run["id"],)).fetchone()
    return run | {"total": n[0], "finished": n[1], "strong": n[2], "possible": n[3]}


@app.get("/health")
def health():
    return {"status": "ok", "allowed_origins": origins}


@app.get("/api/runs")
def list_runs(x_visitor: str | None = Header(default=None)):
    v = visitor_id(x_visitor) or "-"
    with db.connect() as conn:
        rows = conn.execute(f"""select {RUN_COLS} from scout.runs where kind = 'sample' or (kind = 'visitor' and visitor = %s)
                                order by (kind = 'sample') desc, created_at desc limit 30""", (v,)).fetchall()
        runs = [summary(conn, dict(zip(RUN_COLS.split(", "), r)) | {"mine": r[1] == "visitor"}) for r in rows]
    sample = next((r for r in runs if r["kind"] == "sample"), None)
    return {"sample": sample, "mine": [r for r in runs if r["kind"] == "visitor"], "max_per_run": MAX_PER_RUN}


@app.get("/api/runs/{run_id}")
def get_run(run_id: int, x_visitor: str | None = Header(default=None)):
    with db.connect() as conn:
        run = run_row(conn, run_id, visitor_id(x_visitor))
        return summary(conn, run) | {"leads": leads_of(conn, run_id)}


@app.get("/api/leads/{lead_id}")
def get_lead(lead_id: int, x_visitor: str | None = Header(default=None)):
    with db.connect() as conn:
        row = conn.execute("select run_id from scout.leads where id = %s", (lead_id,)).fetchone()
        if not row:
            raise HTTPException(404, "No such lead.")
        run_row(conn, row[0], visitor_id(x_visitor))          # 404 if it's someone else's
        return next(x for x in leads_of(conn, row[0], full=True) if x["id"] == lead_id)


@app.post("/api/runs")
def new_run(body: NewRun, request: Request, x_visitor: str | None = Header(default=None)):
    v = visitor_id(x_visitor)
    if not v:
        return JSONResponse({"detail": "Missing visitor id; reload the page."}, status_code=400)
    companies = list({c.name.lower(): c.model_dump() for c in body.companies}.values())
    if len(companies) > MAX_PER_RUN:
        return JSONResponse({"detail": f"Up to {MAX_PER_RUN} businesses per run in the demo."}, status_code=400)
    with db.connect() as conn:
        busy = conn.execute("""select 1 from scout.runs where kind = 'visitor' and visitor = %s and status <> 'done'
                               and created_at > now() - interval '15 minutes'""", (v,)).fetchone()
    if busy:
        return JSONResponse({"detail": "Your last run is still going. Wait for it to finish first."}, status_code=409)
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
          (request.client.host if request.client else "?"))
    why = limits.allow(f"{v}|{ip}", len(companies))
    if why:
        return JSONResponse({"detail": why}, status_code=429)
    title = ", ".join(c["name"] for c in companies)[:120]
    with db.connect() as conn:
        rid = create(conn, companies, kind="visitor", visitor=v, title=title)
        run = summary(conn, run_row(conn, rid, v)) | {"leads": leads_of(conn, rid)}
    start_worker(rid)
    return run


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: int, x_visitor: str | None = Header(default=None)):
    v = visitor_id(x_visitor)
    with db.connect() as conn:
        run = run_row(conn, run_id, v)
        if not run["mine"]:
            return JSONResponse({"detail": "The sample run can't be deleted."}, status_code=403)
        if run["status"] != "done":
            return JSONResponse({"detail": "Wait for the run to finish before deleting it."}, status_code=409)
        conn.execute("delete from scout.runs where id = %s and kind = 'visitor' and visitor = %s", (run_id, v))
    return {"deleted": run_id}


@app.get("/api/runs/{run_id}/csv")
def run_csv(run_id: int, v: str = "", x_visitor: str | None = Header(default=None)):
    """A download link can't send headers, so the visitor id may also come as ?v=."""
    who = visitor_id(x_visitor) or visitor_id(v)
    with db.connect() as conn:
        run = run_row(conn, run_id, who)
        text = as_csv(run["title"], leads_of(conn, run_id, full=True))
    name = "scout-sample" if run["kind"] == "sample" else f"scout-run-{run_id}"
    return Response(text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})


@app.exception_handler(Exception)
async def unexpected(request: Request, exc: Exception):
    log.exception("unexpected error on %s", request.url.path)
    return JSONResponse({"detail": "Something went wrong on the server. Please try again."}, status_code=500)
