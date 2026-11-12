"""Score Scout on the test set.

    python -m evals.run --record      first time: live web (about 2 Tavily credits a business), saved to
                                      snapshots/evals.json; anything already saved isn't fetched again
    python -m evals.run               every time after: replays the snapshot, so only the AI's answers can change
    python -m evals.run --only "Gjusta" "Starbucks"
    python -m evals.run --set holdout --record      the held-out businesses (only once tuning is done)

Report: evals/reports/scout-<model>.md
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path

from scout.lead import lead
from scout.llm import GroqJSON, LLMError
from scout.web import RecordingWeb, SnapshotWeb, TavilyWeb, WebError

from .companies import COMPANIES, FLAG, HOLDOUT

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "snapshots" / "evals.json"
REPORTS = Path(__file__).resolve().parent / "reports"


def grade(c: dict, x: dict) -> dict:
    f = x["fit"]
    g = {"right_side": (f["score"] >= 45) == (c["expect"] == "fit")}
    if c.get("reason"):
        k, a = FLAG[c["reason"]]
        g["flag"] = f["answers"].get(k, {}).get("answer") == a
    if f["score"] >= 45:
        g["opener"] = bool(x["opener"].get("line"))
    g["facts"] = len(x["facts"])
    g["dropped"] = len(x["dropped"])
    g["site_read"] = x["site_read"]
    return g


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true", help="use the live web for anything not yet in the snapshot")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--set", choices=["main", "holdout"], default="main")
    ap.add_argument("--pause", type=float, default=2.0, help="seconds between businesses (Groq's rate limit)")
    a = ap.parse_args()
    companies = [c for c in (HOLDOUT if a.set == "holdout" else COMPANIES) if not a.only or c["name"] in a.only]
    if not a.record and not SNAP.exists():
        raise SystemExit("No snapshot yet: run  python -m evals.run --record  once first.")
    web = RecordingWeb(TavilyWeb(), SNAP) if a.record else SnapshotWeb(SNAP)
    llm = GroqJSON()
    rows = []
    for n, c in enumerate(companies, 1):
        t = time.perf_counter()
        try:
            x = lead(c, web, llm)
            g, err = grade(c, x), ""
        except (WebError, LLMError) as e:
            x, g, err = None, {}, str(e)
        ok = bool(g) and all(v for k, v in g.items() if k in ("right_side", "flag", "opener"))
        score = x["fit"]["score"] if x else "-"
        print(f"[{n:>2}/{len(companies)}] {'OK  ' if ok else 'MISS'} {score:>3} {c['expect']:4} {c['name'][:34]:34} "
              f"{time.perf_counter() - t:5.1f}s" + (f"  {err}" if err else ""))
        rows.append({"c": c, "x": x, "g": g, "err": err, "ok": ok})
        time.sleep(a.pause)

    def rate(key, subset=None):
        vals = [r["g"][key] for r in (rows if subset is None else subset) if key in r["g"]]
        return f"{sum(vals)}/{len(vals)}" if vals else "-"
    fits = [r for r in rows if r["c"]["expect"] == "fit"]
    weak = [r for r in rows if r["c"]["expect"] == "weak"]
    facts = [r["g"]["facts"] for r in rows if r["g"]]
    dropped = [r["g"]["dropped"] for r in rows if r["g"]]
    model = getattr(llm, "model", "model").split("/")[-1]
    lines = [f"# Scout check ({a.set}): {model}, {datetime.now():%Y-%m-%d %H:%M}", "",
             "| Check | Result |", "| --- | --- |",
             f"| Good fits scored 45+ | {rate('right_side', fits)} |",
             f"| Poor fits scored under 45 | {rate('right_side', weak)} |",
             f"| Deal-breaker found (roaster, chain, outside US) | {rate('flag')} |",
             f"| First line written for leads scoring 45+ | {rate('opener')} |",
             f"| Website read | {rate('site_read')} |",
             f"| Checked facts per business (average) | {sum(facts) / max(1, len(facts)):.1f} |",
             f"| Facts dropped by the checks | {sum(dropped)} of {sum(facts) + sum(dropped)} |",
             f"| Errors | {sum(bool(r['err']) for r in rows)} |", "", "## Misses", ""]
    for r in rows:
        if r["ok"]:
            continue
        c, x = r["c"], r["x"]
        lines.append(f"- **{c['name']}** (expected {c['expect']}{', ' + c['reason'] if c.get('reason') else ''})")
        if r["err"]:
            lines.append(f"  - error: {r['err']}")
            continue
        f = x["fit"]
        lines.append(f"  - score {f['score']} ({f['tier']}); answers: " +
                     ", ".join(f"{k}={v['answer']}" for k, v in f["answers"].items()))
        lines.append(f"  - first line: {x['opener'].get('line') or x['opener'].get('why')}")
        lines += [f"  - fact: [{y['topic']}] {y['fact']}" for y in x["facts"][:8]]
    lines += ["", "## First lines", ""]
    lines += [f"- **{r['c']['name']}**: {r['x']['opener']['line']}" for r in rows if r["x"] and r["x"]["opener"].get("line")]
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"scout-{model}-{a.set}{'-partial' if a.only else ''}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines[:13]) + f"\n\nFull report: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
