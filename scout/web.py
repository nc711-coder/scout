"""The web, as Scout sees it: search and read pages.

    web = TavilyWeb()                              # live, through Tavily (TAVILY_API_KEY in .env)
    web = RecordingWeb(TavilyWeb(), "snapshots/x.json")   # live, and saves every answer to a snapshot
    web = SnapshotWeb("snapshots/x.json")          # replays a snapshot: no network, same answer every time

    web.search("Ritual Coffee Roasters San Francisco")   -> [{"url", "title", "content", "raw_content"}]
    web.read(["https://example.com", ...])               -> {url: {"url", "title", "text"} or {"url", "error"}}

Tests use the snapshot, so the scores don't change when a website does.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from .llm import LLMError, load_dotenv

API = "https://api.tavily.com"
MAX_CHARS = 60_000                       # per page, as stored; prompts use far less


class WebError(LLMError):
    """A message a person can act on."""


def domain(url: str) -> str:
    host = urlparse(url if "//" in url else f"https://{url}").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return url
    if "//" not in url:
        url = "https://" + url
    p = urlparse(url)
    path = p.path.rstrip("/")
    return f"{p.scheme}://{p.netloc.lower()}{path}" + (f"?{p.query}" if p.query else "")


# Keys that websites embed in their own pages (map widgets, payment buttons). They belong to those sites, not to
# us, but they don't belong in our snapshot or repo either, so they're blanked out as pages are read.
KEYS = re.compile(r"AIza[0-9A-Za-z_\-]{35}|AKIA[0-9A-Z]{16}|\b(?:sk|pk|rk)_(?:live|test)_[0-9A-Za-z]{16,}|"
                  r"\bgh[pousr]_[0-9A-Za-z]{30,}|\bxox[abposr]-[0-9A-Za-z-]{10,}")


def scrub(text: str) -> str:
    return KEYS.sub("[key removed]", text or "")


LINK = re.compile(r"\[([^\]]{0,120})\]\(([^)\s]+)\)")


def links(markdown: str, base: str) -> list[tuple[str, str]]:
    """(text, absolute url) of the links in a page's markdown."""
    out = []
    for text, href in LINK.findall(markdown or ""):
        if href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        out.append((text.strip(), normalize_url(urljoin(base + "/", href))))
    return out


def title_of(markdown: str) -> str:
    m = re.search(r"^#\s+(.+)$", markdown or "", re.M)
    return m.group(1).strip()[:150] if m else ""


class TavilyWeb:
    def __init__(self, key: str | None = None, client=None):
        load_dotenv()
        self.key = key or os.environ.get("TAVILY_API_KEY", "")
        self._client = client
        self.credits = 0.0                  # roughly: 1 per basic search, 1 per 5 pages read

    @property
    def client(self):
        if self._client is None:
            if not self.key:
                raise WebError("TAVILY_API_KEY is not set. Add it to .env in the project folder.")
            import httpx
            self._client = httpx.Client(base_url=API, timeout=40,
                                        headers={"Authorization": f"Bearer {self.key}"})
        return self._client

    def _post(self, path: str, body: dict) -> dict:
        for attempt in range(3):
            try:
                r = self.client.post(path, json=body)
            except Exception as e:                      # network hiccup
                if attempt == 2:
                    raise WebError(f"Couldn't reach Tavily ({type(e).__name__}). Check the internet connection.") from e
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code in (401, 403):
                raise WebError("Tavily rejected the API key. Check TAVILY_API_KEY in .env.")
            if r.status_code == 432 or r.status_code == 433:
                raise WebError("Tavily's monthly credits or plan limit is used up.")
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == 2:
                    raise WebError(f"Tavily is busy (HTTP {r.status_code}). Try again in a minute.")
                time.sleep(3 * (attempt + 1))
                continue
            if r.status_code >= 400:
                raise WebError(f"Tavily refused the request (HTTP {r.status_code}): {r.text[:200]}")
            return r.json()
        raise WebError("Tavily didn't answer.")

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        data = self._post("/search", {"query": query, "search_depth": "basic", "max_results": max_results,
                                      "include_raw_content": True, "topic": "general"})
        self.credits += 1
        return [{"url": normalize_url(r.get("url", "")), "title": r.get("title") or "",
                 "content": scrub(r.get("content") or ""), "raw_content": scrub(r.get("raw_content") or "")[:MAX_CHARS]}
                for r in data.get("results") or [] if r.get("url")]

    def read(self, urls: list[str]) -> dict[str, dict]:
        urls = list(dict.fromkeys(normalize_url(u) for u in urls if u))[:20]
        if not urls:
            return {}
        data = self._post("/extract", {"urls": urls, "extract_depth": "basic", "format": "markdown"})
        out = {}
        for r in data.get("results") or []:
            u = normalize_url(r.get("url", ""))
            text = scrub(r.get("raw_content") or "")[:MAX_CHARS]
            out[u] = {"url": u, "title": title_of(text), "text": text}
        for r in data.get("failed_results") or []:
            u = normalize_url(r.get("url", ""))
            out.setdefault(u, {"url": u, "error": str(r.get("error") or "couldn't read the page")[:200]})
        for u in urls:                                  # redirects can change the address: match by domain+path
            if u not in out:
                out[u] = next((v for k, v in out.items() if domain(k) == domain(u) and urlparse(k).path == urlparse(u).path),
                              {"url": u, "error": "the page couldn't be read"})
        self.credits += max(1, len([v for v in out.values() if "text" in v])) / 5
        return out


class SnapshotWeb:
    """Answers from a saved snapshot. Anything not in it counts as 'not found', never as a network call."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"search": {}, "read": {}}
        self.credits = 0.0

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        return self.data["search"].get(query, [])[:max_results]

    def read(self, urls: list[str]) -> dict[str, dict]:
        return {normalize_url(u): self.data["read"].get(normalize_url(u), {"url": normalize_url(u),
                                                                            "error": "not in the snapshot"})
                for u in urls if u}


class RecordingWeb:
    """Live web that also saves everything it sees, to build a snapshot for tests. Anything already in the
    snapshot is answered from it, so re-running a recording doesn't spend credits twice."""

    def __init__(self, live, path: str | Path):
        self.live, self.snap = live, SnapshotWeb(path)

    @property
    def credits(self):
        return self.live.credits

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        if query in self.snap.data["search"]:
            return self.snap.data["search"][query][:max_results]
        out = self.live.search(query, max_results)
        self.snap.data["search"][query] = out
        self._save()
        return out

    def read(self, urls: list[str]) -> dict[str, dict]:
        urls = [normalize_url(u) for u in urls if u]
        have = {u: self.snap.data["read"][u] for u in urls if "text" in self.snap.data["read"].get(u, {})}
        missing = [u for u in urls if u not in have]
        out = self.live.read(missing) if missing else {}
        self.snap.data["read"].update(out)
        if out:
            self._save()
        return {**have, **out}

    def _save(self):
        self.snap.path.parent.mkdir(parents=True, exist_ok=True)
        self.snap.path.write_text(json.dumps(self.snap.data, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":                 # python -m scout.web --scrub snapshots/evals.json
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--scrub":
        p = Path(sys.argv[2])
        raw = p.read_text(encoding="utf-8")
        found = len(KEYS.findall(raw))
        p.write_text(KEYS.sub("[key removed]", raw), encoding="utf-8")
        print(f"Removed {found} embedded keys from {p}.")
    else:
        print("usage: python -m scout.web --scrub snapshots/evals.json")
