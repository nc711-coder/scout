import json

import pytest

from scout.quotes import flatten, quote_on_page
from scout.research import pick_links, research, verify
from scout.web import RecordingWeb, SnapshotWeb, normalize_url

HOME = """# Hilltop Bakery

[About us](/about) · [Our Locations](https://www.hilltopbakery.example/locations/) · [Instagram](https://instagram.com/x)
[Order a cake](/cakes) · ![logo](/logo.png)

Hilltop Bakery has been baking **sourdough** in Asheville, North Carolina since 2009.
We pour espresso from our neighbors at **Mountain Roasting Co.** every morning."""

ABOUT = """# About

Three bakeries across Asheville, with 40 people baking through the night.
We opened our third shop on Haywood Road in March 2026."""

SEARCH = [{"url": "https://news.example/hilltop", "title": "Hilltop wins award",
           "content": "Hilltop Bakery named best bakery", "raw_content": "Asheville favorite Hilltop Bakery was named Best Bakery in Western North Carolina for 2026 by readers."}]


class FakeWeb:
    def __init__(self):
        self.pages = {"https://hilltopbakery.example": {"url": "https://hilltopbakery.example", "title": "Hilltop Bakery", "text": HOME},
                      "https://hilltopbakery.example/about": {"url": "https://hilltopbakery.example/about", "title": "About", "text": ABOUT},
                      "https://hilltopbakery.example/locations": {"url": "https://hilltopbakery.example/locations", "error": "timeout"}}
        self.credits, self.queries = 0.0, []

    def read(self, urls):
        return {normalize_url(u): self.pages.get(normalize_url(u), {"url": normalize_url(u), "error": "404"}) for u in urls}

    def search(self, query, max_results=5):
        self.queries.append(query)
        return SEARCH


class FakeLLM:
    """Lists the given facts; the support check says "yes" unless told otherwise (by item number)."""

    def __init__(self, facts, verdicts=None):
        self.facts, self.verdicts, self.prompts = facts, verdicts or {}, []

    def json(self, system, user, schema=None, name="", max_tokens=0):
        self.prompts.append(user)
        if name == "checks":
            n = user.count("Fact:")
            return {"checks": [{"n": i, **self.verdicts.get(i, {"verdict": "yes", "fact": "", "topic": "news"})}
                               for i in range(1, n + 1)]}, {}
        return {"facts": self.facts}, {}


def test_flatten_ignores_markdown_and_typography():
    assert flatten("We pour espresso from our neighbors at **Mountain Roasting Co.**") == \
        flatten("we pour espresso from our neighbors at Mountain Roasting Co.")
    assert quote_on_page("baking sourdough in Asheville, North Carolina", HOME)
    assert quote_on_page("Hilltop Bakery has been baking “sourdough” in Asheville", HOME.replace("**", '"'))
    assert not quote_on_page("baking bagels in Asheville, North Carolina", HOME)
    assert not quote_on_page("Asheville", HOME)                          # too short to prove anything


def test_picks_useful_pages_on_the_same_site():
    picked = pick_links({"text": HOME}, "https://hilltopbakery.example")
    assert picked == ["https://hilltopbakery.example/about", "https://hilltopbakery.example/locations"]


def test_research_keeps_only_checked_facts():
    facts = [
        {"topic": "location", "fact": "Based in Asheville, NC", "quote": "baking sourdough in Asheville, North Carolina since 2009", "page": "P1"},
        {"topic": "roaster", "fact": "Serves Mountain Roasting Co. espresso", "quote": "We pour espresso from our neighbors at Mountain Roasting Co.", "page": "P1"},
        {"topic": "locations", "fact": "Three bakeries", "quote": "Three bakeries across Asheville, with 40 people", "page": "P1"},   # wrong page id
        {"topic": "news", "fact": "Best Bakery award", "quote": "named Best Bakery in Western North Carolina for 2026", "page": "P3"},
        {"topic": "size", "fact": "100 staff", "quote": "over one hundred people work at our bakeries", "page": "P2"},              # invented
    ]
    web = FakeWeb()
    r = research({"name": "Hilltop Bakery", "website": "hilltopbakery.example", "city": "Asheville"}, web, FakeLLM(facts))
    assert [p["id"] for p in r["pages"]] == ["P1", "P2", "P3", "P4"]
    assert r["pages"][2]["error"] == "timeout" and r["pages"][3]["source"] == "search"
    assert web.queries == ["Hilltop Bakery Asheville", "Hilltop Bakery coffee roaster locations"]
    assert len(r["facts"]) == 4
    assert r["facts"][2]["url"] == "https://hilltopbakery.example/about"                    # page id corrected
    assert [d["fact"] for d in r["dropped"]] == ["100 staff"] and r["site_read"]


def test_unreadable_site_still_searches():
    web = FakeWeb()
    web.pages = {}
    r = research({"name": "Hilltop Bakery", "website": "https://hilltopbakery.example"}, web, FakeLLM([]))
    assert not r["site_read"] and r["pages"][0]["error"] and r["pages"][1]["source"] == "search"


def test_snapshot_records_and_replays(tmp_path):
    path = tmp_path / "snap.json"
    rec = RecordingWeb(FakeWeb(), path)
    research({"name": "Hilltop Bakery", "website": "hilltopbakery.example"}, rec, FakeLLM([]))
    data = json.loads(path.read_text())
    assert "Hilltop Bakery" in data["search"] and "https://hilltopbakery.example/about" in data["read"]
    llm = FakeLLM([])
    r = research({"name": "Hilltop Bakery", "website": "hilltopbakery.example"}, SnapshotWeb(path), llm)
    assert len(r["pages"]) == 4 and "Three bakeries" in llm.prompts[0]
    assert SnapshotWeb(path).read(["https://elsewhere.example"])["https://elsewhere.example"]["error"]


def test_tavily_requests_and_errors():
    from scout.web import TavilyWeb, WebError

    class Resp:
        def __init__(self, code, data):
            self.status_code, self._data, self.text = code, data, json.dumps(data)

        def json(self):
            return self._data

    class Client:
        def __init__(self, answers):
            self.answers, self.sent = list(answers), []

        def post(self, path, json=None):
            self.sent.append((path, json))
            return self.answers.pop(0)

    c = Client([Resp(200, {"results": [{"url": "https://www.a.example/", "raw_content": "# A\nhello"}],
                           "failed_results": [{"url": "https://b.example", "error": "blocked"}]})])
    w = TavilyWeb(key="tvly-test", client=c)
    out = w.read(["a.example", "https://b.example/"])
    assert c.sent[0] == ("/extract", {"urls": ["https://a.example", "https://b.example"], "extract_depth": "basic", "format": "markdown"})
    assert out["https://a.example"]["title"] == "A" and out["https://b.example"]["error"] == "blocked"
    with pytest.raises(WebError, match="TAVILY_API_KEY"):
        TavilyWeb(key="tvly-x", client=Client([Resp(401, {})])).search("x")


def test_list_quotes_and_skips():
    page = "Our values:\n- People Matter\n- Consistent Excellence\n- Open Collaboration\n\nWe bake every night, then we open at 7am."
    assert quote_on_page("People Matter, Consistent Excellence, Open Collaboration", page)
    assert quote_on_page("We bake every night ... we open at 7am", page)
    assert not quote_on_page("We bake every night ... we close at 7am", page)
    assert not quote_on_page("we open at 7am ... We bake every night", page)              # pieces must be in order
    assert quote_on_page("PEOPLE MATTER \u2026 CONSISTENT EXCELLENCE \u2026 OPEN COLLABORATION", page)
    assert not quote_on_page("People ... Matter ... Open", page)                          # one-word pieces prove nothing


def test_support_check_narrows_or_drops():
    facts = [
        {"topic": "location", "fact": "Based in Asheville", "quote": "baking sourdough in Asheville, North Carolina since 2009", "page": "P1"},
        {"topic": "roaster", "fact": "Has dozens of locations since 2009", "quote": "Hilltop Bakery has been baking sourdough in Asheville", "page": "P1"},
        {"topic": "roaster", "fact": "Bakes its own bread", "quote": "We pour espresso from our neighbors at Mountain Roasting Co.", "page": "P1"},
    ]
    llm = FakeLLM(facts, {1: {"verdict": "yes", "fact": "", "topic": "location"},
                          2: {"verdict": "partly", "fact": "Bakes sourdough in Asheville", "topic": "offerings"},
                          3: {"verdict": "no", "fact": "", "topic": "roaster"}})
    r = research({"name": "Hilltop Bakery", "website": "hilltopbakery.example"}, FakeWeb(), llm)
    assert [(f["topic"], f["fact"]) for f in r["facts"]] == [("location", "Based in Asheville"),
                                                            ("offerings", "Bakes sourdough in Asheville")]
    assert r["facts"][1]["narrowed_from"] == "Has dozens of locations since 2009"
    assert r["dropped"][0]["why"] == "the quote doesn't back up the fact"


def test_recording_reuses_what_it_already_has(tmp_path):
    path = tmp_path / "snap.json"
    live = FakeWeb()
    rec = RecordingWeb(live, path)
    rec.read(["https://hilltopbakery.example"])
    rec.search("Hilltop Bakery")
    calls = []
    live.read = lambda urls: calls.append(urls) or {}
    live.search = lambda q, max_results=5: calls.append(q) or []
    again = RecordingWeb(live, path)
    assert "text" in again.read(["https://hilltopbakery.example"])["https://hilltopbakery.example"]
    assert again.search("Hilltop Bakery") == SEARCH and calls == []


def test_search_results_about_another_business_are_skipped():
    from scout.research import about_this_business
    co = {"name": "Dahlia Bakery", "website": "https://dahliabakery.com", "city": "Seattle"}
    assert about_this_business("Dahlia Bakery on 4th Avenue in Seattle bakes...", co)
    assert about_this_business("Order online at dahliabakery.com", co)
    assert not about_this_business("Dahlia Coffee Co. roasts small batches in Cleveland, Ohio", co)
    assert about_this_business("Starbucks has 40,000 stores", {"name": "Starbucks", "website": "", "city": ""})
    web = FakeWeb()
    web.search = lambda q, max_results=5: [{"url": "https://other.example", "title": "x", "content": "",
                                            "raw_content": "Hilltop Bakery in Denver roasts its own beans."}]
    r = research({"name": "Hilltop Bakery", "website": "hilltopbakery.example", "city": "Asheville"}, web, FakeLLM([]))
    assert all(p["source"] == "site" for p in r["pages"])


def test_embedded_keys_are_blanked():
    from scout.web import scrub
    key = "AIza" + "Sy" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q"
    assert scrub(f'<script src="maps.js?key={key}">') == '<script src="maps.js?key=[key removed]">'
    assert scrub("We bake sourdough daily.") == "We bake sourdough daily."
