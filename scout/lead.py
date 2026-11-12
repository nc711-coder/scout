"""One lead, start to finish: research, score, first line.

    python -m scout.lead "Tartine" https://tartinebakery.com --city "San Francisco"
    python -m scout.lead ... --record snapshots/manual.json      # also save the pages, for tests
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from . import fit, opener
from .llm import GroqJSON, LLMError
from .research import research
from .web import TavilyWeb, WebError


def lead(company: dict, web, llm, progress=lambda stage: None) -> dict:
    t = time.perf_counter()
    r = research(company, web, llm, progress)
    progress("Scoring the fit")
    f = fit.score(r["facts"], llm)
    if f["score"] >= 45:
        progress("Writing the first line")
        o = opener.write(r["facts"], company["name"], llm)
    else:
        o = {"line": "", "why": "not written for weak fits"}
    return {**r, "fit": f, "opener": o, "seconds": round(time.perf_counter() - t, 1)}


def show(x: dict) -> str:
    f, o = x["fit"], x["opener"]
    lines = [f"{x['company']['name']}: {f['score']}/100, {f['tier']}" + (" (a deal-breaker caps the score)" if f.get("capped") else ""),
             f"  {len(x['facts'])} checked facts, {len(x['dropped'])} dropped, {x['seconds']}s, about {x['credits']} Tavily credits"]
    for r in f["reasons"]:
        lines.append(f"  {r['points']:+d}  {r['why']}  (facts {', '.join(map(str, r['facts']))})")
    if f["unknown"]:
        lines.append(f"  Unknown: {', '.join(f['unknown'])}")
    lines.append(f"  First line: {o['line']}" if o.get("line") else f"  No first line: {o.get('why')}")
    if o.get("line"):
        lines.append(f"    based on fact {o['fact']}: \"{o['quote']}\" ({o['url']})")
    lines.append("  Facts:")
    lines += [f"    {i}. [{y['topic']}] {y['fact']}  ({y['url']})" for i, y in enumerate(x["facts"], 1)]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Research, score and write a first line for one business.")
    ap.add_argument("name")
    ap.add_argument("website", nargs="?", default="")
    ap.add_argument("--city", default="")
    ap.add_argument("--record", help="also save what was read to this snapshot file")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    web = TavilyWeb()
    if a.record:
        from .web import RecordingWeb
        web = RecordingWeb(web, a.record)
    try:
        x = lead({"name": a.name, "website": a.website, "city": a.city}, web, GroqJSON())
    except (WebError, LLMError) as e:
        print(f"Error: {e}")
        return 1
    print(json.dumps(x, indent=1, ensure_ascii=False) if a.json else show(x))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
