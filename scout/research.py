"""Research one business: read its website, search the web, and keep only facts whose quotes check out.

    python -m scout.research "Ritual Coffee Roasters" https://ritualcoffee.com --city "San Francisco"
    python -m scout.research ... --record snapshots/manual.json     # also save what it read, for tests

Steps (a fixed pipeline, so the cost per business is predictable, about 3 Tavily credits):
  1. read the homepage, then up to 3 useful pages it links to (about, locations, wholesale...)
  2. two web searches: what others say about the business, and who roasts its coffee / how many locations
  3. the AI lists facts, each with a quote copied from a page
  4. code checks every quote is really on that page; facts that fail are dropped, and listed as dropped
  5. a second, separate AI check reads each fact next to its quote: a fact the quote doesn't back up is cut
     down to what the quote says, or dropped
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time

from .llm import GroqJSON, LLMError
from .quotes import quote_on_page, words
from urllib.parse import urlparse

from .web import TavilyWeb, WebError, domain, links, normalize_url

PAGE_CHARS = 3500                 # of each page, in the prompt
MAX_SITE_PAGES = 3                # besides the homepage
MAX_SEARCH_PAGES = 3

# Which linked pages are worth reading, best first (matched against the link's text and address).
USEFUL = ["about", "our-story", "story", "who-we-are", "locations", "location", "visit", "find-us", "wholesale",
          "coffee", "menu", "press", "news", "careers", "contact"]

TOPICS = {
    "business_type": "what kind of business it is (café, bakery, restaurant, office, roaster, chain...)",
    "location": "where it is: city, state, country",
    "locations": "how many locations or branches",
    "coffee": "what coffee they serve, or how they make it",
    "roaster": "who roasts their coffee, or whether they roast their own",
    "size": "staff, seats, customers, years in business",
    "news": "recent openings, awards, events or press",
    "values": "what they say they care about",
    "offerings": "what they sell or offer besides coffee",
}

SYSTEM = f"""You research businesses for a coffee roaster's wholesale team. You get pages from a business's own
website and from a web search. List the facts these pages state about THIS business.

Reply with a JSON object: {{"facts": [{{"topic", "fact", "quote", "page"}}]}}
  "topic": one of {", ".join(TOPICS)}
           ({"; ".join(f"{k} = {v}" for k, v in TOPICS.items())})
  "fact":  the fact in a short sentence of your own
  "quote": the words on the page that show it, copied EXACTLY, 5 to 30 words, from one place on the page
  "page":  the page id it's from, like "P2"

Rules:
- Only facts the pages actually state. No guesses, no general knowledge, nothing about other businesses with a
  similar name.
- Facts about the business only: never personal details about people (no personal emails, phones, addresses).
- A quote must be copied character for character; code checks it and drops facts whose quote isn't on the page.
- Always include, when the pages say so: whether they roast their own coffee or who supplies it, how many
  locations they have, where they are (city, state, country), and how big they are (staff, revenue, owner).
- Up to 14 facts, most useful first. If the pages say little, return few facts."""

SCHEMA = {"type": "object", "properties": {"facts": {"type": "array", "items": {"type": "object", "properties": {
    "topic": {"type": "string", "enum": list(TOPICS)}, "fact": {"type": "string"}, "quote": {"type": "string"},
    "page": {"type": "string"}}, "required": ["topic", "fact", "quote", "page"]}}}, "required": ["facts"]}


def pick_links(home: dict, site: str, limit: int = MAX_SITE_PAGES) -> list[str]:
    """The site's own pages most likely to say what the business is, best first."""
    base = domain(site)
    scored = {}
    for text, url in links(home.get("text", ""), site):
        if domain(url) != base or url == normalize_url(site) or re.search(r"\.(jpg|png|pdf|gif|svg)$", url, re.I):
            continue
        s = urlparse(normalize_url(site))                          # same host spelling as the site (www or not)
        url = normalize_url(f"{s.scheme}://{s.netloc}" + url.split(urlparse(url).netloc, 1)[1])
        hay = f"{text} {url}".lower()
        rank = next((i for i, w in enumerate(USEFUL) if w in hay), None)
        if rank is not None and (url not in scored or rank < scored[url]):
            scored[url] = rank
    return [u for u, _ in sorted(scored.items(), key=lambda kv: kv[1])][:limit]


def about_this_business(text: str, company: dict) -> bool:
    """Does a search result talk about this business, not another one with a similar name? With a city given, it
    must mention that city or the business's website; without one, the business's name or website."""
    t = text.lower()
    city = (company.get("city") or "").split(",")[0].strip().lower()
    site = domain(company.get("website") or "")
    if site and site in t.replace("www.", ""):
        return True
    return (city in t) if city else company["name"].lower() in t


def gather(company: dict, web, progress=lambda stage: None) -> list[dict]:
    """Every page read: [{"id", "url", "title", "source": "site"|"search", "text" or "error"}]."""
    site = normalize_url(company.get("website") or "")
    pages: list[dict] = []

    def add(p: dict, source: str):
        if any(x["url"] == p["url"] for x in pages):
            return
        pages.append({"id": f"P{len(pages) + 1}", "source": source, **p})

    if site:
        progress("Reading the website")
        home = web.read([site]).get(site) or {"url": site, "error": "the page couldn't be read"}
        add(home, "site")
        if "text" in home:
            for p in web.read(pick_links(home, site)).values():
                add(p, "site")
    progress("Searching the web")
    base = " ".join(x for x in [company["name"], company.get("city") or ""] if x).strip()
    # what others say about it, then the facts that decide a fit: who roasts their coffee, how many locations
    for query, limit in ((base, MAX_SEARCH_PAGES), (f"{company['name']} coffee roaster locations", 2)):
        found = 0
        for r in web.search(query, max_results=6):
            if found >= limit:
                break
            text = r.get("raw_content") or r.get("content") or ""
            if not text or any(x["url"] == r["url"] for x in pages):
                continue
            if domain(r["url"]) != domain(site or "-") and not about_this_business(text, company):
                continue                            # probably a different business with a similar name
            add({"url": r["url"], "title": r.get("title", ""), "text": text}, "search")
            found += 1
    return pages


def prompt_for(company: dict, pages: list[dict]) -> str:
    head = f"Business: {company['name']}" + (f" ({company['website']})" if company.get("website") else "") + \
        (f", {company['city']}" if company.get("city") else "")
    blocks = [f"[{p['id']}] {p['url']} ({'their website' if p['source'] == 'site' else 'web search'})\n"
              f"{p.get('title', '')}\n{p['text'][:PAGE_CHARS]}" for p in pages if "text" in p]
    return head + "\n\n" + "\n\n---\n\n".join(blocks)


def verify(facts: list[dict], pages: list[dict]) -> tuple[list[dict], list[dict]]:
    """(facts whose quote is on a page, facts dropped with the reason)."""
    by_id = {p["id"]: p for p in pages if "text" in p}
    kept, dropped = [], []
    for f in facts:
        quote = str(f.get("quote") or "").strip()
        page = by_id.get(str(f.get("page") or "").strip().strip("[]"))
        if words(quote) > 40:
            dropped.append({**f, "why": "the quote is too long to check"})
            continue
        if page and quote_on_page(quote, page["text"]):
            kept.append({**f, "url": page["url"], "source": page["source"]})
            continue
        other = next((p for p in by_id.values() if quote_on_page(quote, p["text"])), None)
        if other:                                   # right quote, wrong page id: keep it, with the right page
            kept.append({**f, "page": other["id"], "url": other["url"], "source": other["source"]})
        else:
            dropped.append({**f, "why": "the quote isn't on the page"})
    return kept, dropped


CHECK = f"""Each item below is a fact about a business and the quote it is based on. Judge each one strictly,
using ONLY the quote (not what you know):
  "yes":    the quote fully shows the fact
  "partly": the quote shows part of it; rewrite the fact to say only what the quote shows
  "no":     the quote doesn't show it
Also give the topic that fits the (rewritten) fact best: one of {", ".join(TOPICS)}.
Reply with a JSON object: {{"checks": [{{"n": item number, "verdict": "yes"|"partly"|"no", "fact": the fact
(rewritten if "partly"), "topic": topic}}]}}"""

CHECK_SCHEMA = {"type": "object", "properties": {"checks": {"type": "array", "items": {"type": "object", "properties": {
    "n": {"type": "integer"}, "verdict": {"type": "string", "enum": ["yes", "partly", "no"]}, "fact": {"type": "string"},
    "topic": {"type": "string", "enum": list(TOPICS)}}, "required": ["n", "verdict", "fact", "topic"]}}},
    "required": ["checks"]}


def check_support(facts: list[dict], llm) -> tuple[list[dict], list[dict]]:
    """(facts the quote backs up, possibly narrowed; facts it doesn't). Unchecked items are dropped, not kept."""
    if not facts:
        return [], []
    items = "\n".join(f"{i + 1}. Fact: {f['fact']}\n   Quote: \"{f['quote']}\"" for i, f in enumerate(facts))
    data, _ = llm.json(CHECK, items, CHECK_SCHEMA, name="checks", max_tokens=2500)
    verdicts = {c.get("n"): c for c in data.get("checks") or [] if isinstance(c, dict)}
    kept, dropped = [], []
    for i, f in enumerate(facts, start=1):
        c = verdicts.get(i)
        if not c or c.get("verdict") == "no":
            dropped.append({**f, "why": "the quote doesn't back up the fact" if c else "the fact couldn't be checked"})
            continue
        new = {**f, "topic": c.get("topic") if c.get("topic") in TOPICS else f["topic"]}
        if c.get("verdict") == "partly" and c.get("fact"):
            new = {**new, "fact": c["fact"], "narrowed_from": f["fact"]}
        kept.append(new)
    return kept, dropped


def research(company: dict, web, llm, progress=lambda stage: None) -> dict:
    t = time.perf_counter()
    credits0 = getattr(web, "credits", 0)
    pages = gather(company, web, progress)
    readable = [p for p in pages if "text" in p]
    out = {"company": company, "pages": [{k: p.get(k) for k in ("id", "url", "title", "source", "error")}
                                         | {"chars": len(p.get("text", ""))} for p in pages],
           "site_read": any(p["source"] == "site" for p in readable), "facts": [], "dropped": []}
    if readable:
        progress("Listing facts and checking quotes")
        data, _ = llm.json(SYSTEM, prompt_for(company, readable), SCHEMA, name="facts", max_tokens=3000)
        on_page, not_on_page = verify(data.get("facts") or [], readable)
        out["facts"], unsupported = check_support(on_page, llm)
        out["dropped"] = not_on_page + unsupported
    out["credits"] = round(getattr(web, "credits", 0) - credits0, 1)
    out["seconds"] = round(time.perf_counter() - t, 1)
    return out


def show(r: dict) -> str:
    lines = [f"{r['company']['name']}: {len(r['facts'])} checked facts from {len([p for p in r['pages'] if not p.get('error')])} pages"
             f" ({r['seconds']}s, about {r['credits']} Tavily credits)"]
    if not r["site_read"]:
        lines.append("  ! Couldn't read the website.")
    for f in r["facts"]:
        lines.append(f"  [{f['topic']}] {f['fact']}" + (" (narrowed)" if f.get("narrowed_from") else "") +
                     f"\n      \"{f['quote']}\"  ({f['url']})")
    if r["dropped"]:
        lines.append(f"  Dropped {len(r['dropped'])} unchecked:")
        lines += [f"    - {d.get('fact', '')} ({d['why']})\n        quoted [{d.get('page', '?')}]: \"{d.get('quote', '')}\""
                  for d in r["dropped"]]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Research one business.")
    ap.add_argument("name")
    ap.add_argument("website", nargs="?", default="")
    ap.add_argument("--city", default="")
    ap.add_argument("--record", help="also save what was read to this snapshot file")
    ap.add_argument("--json", action="store_true", help="print the full result as JSON")
    a = ap.parse_args(argv)
    web = TavilyWeb()
    if a.record:
        from .web import RecordingWeb
        web = RecordingWeb(web, a.record)
    try:
        r = research({"name": a.name, "website": a.website, "city": a.city}, web, GroqJSON())
    except (WebError, LLMError) as e:
        print(f"Error: {e}")
        return 1
    print(json.dumps(r, indent=1, ensure_ascii=False) if a.json else show(r))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
