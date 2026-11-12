import os

import pytest

TEST_DB = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="set TEST_DATABASE_URL to a throwaway Postgres database")

from tests.test_research import FakeWeb  # noqa: E402

ME = {"X-Visitor": "visitor-aaaa-1111"}
YOU = {"X-Visitor": "visitor-bbbb-2222"}

FACTS = [{"topic": "location", "fact": "In Asheville", "quote": "baking sourdough in Asheville, North Carolina since 2009", "page": "P1"},
         {"topic": "coffee", "fact": "Pours Mountain Roasting Co.", "quote": "We pour espresso from our neighbors at Mountain Roasting Co.", "page": "P1"}]
ANSWERS = {"serves_coffee": {"answer": "yes", "facts": [2]}, "in_us": {"answer": "yes", "facts": [1]},
           "roasts_own": {"answer": "no", "facts": [2]}, "big_chain": {"answer": "unknown", "facts": []},
           "quality_focus": {"answer": "unknown", "facts": []}, "volume": {"answer": "unknown", "facts": []},
           "has_roaster": {"answer": "yes", "facts": [2]}}


class LLM:
    def json(self, system, user, schema=None, name="", max_tokens=0):
        if name == "facts":
            if "Broken" in user:
                from scout.llm import LLMError
                raise LLMError("The model kept producing malformed JSON.")
            return {"facts": FACTS}, {}
        if name == "checks":
            return {"checks": [{"n": i, "verdict": "yes", "fact": "", "topic": "location"} for i in (1, 2)]}, {}
        if name == "fit":
            return {"answers": ANSWERS}, {}
        return {"fact": 2, "line": "I noticed you pour espresso from your neighbors at Mountain Roasting Co. every morning."}, {}


@pytest.fixture()
def client(monkeypatch):
    os.environ["DATABASE_URL"] = TEST_DB
    from fastapi.testclient import TestClient
    from scout import app as appmod, db, runs
    db.setup()
    with db.connect() as conn:
        conn.execute("delete from scout.runs")
    monkeypatch.setattr(runs.time, "sleep", lambda s: None)
    web = FakeWeb()
    monkeypatch.setattr(appmod, "start_worker", lambda rid: runs.work(rid, db.connect, web, LLM()))
    appmod.limits = appmod.Limits()
    return TestClient(appmod.app)


def test_run_research_and_download(client):
    body = {"companies": [{"name": "Hilltop Bakery", "website": "hilltopbakery.example", "city": "Asheville"},
                          {"name": "Broken Bakery", "website": "hilltopbakery.example", "city": ""}]}
    r = client.post("/api/runs", json=body, headers=ME)
    assert r.status_code == 200
    rid = r.json()["id"]
    run = client.get(f"/api/runs/{rid}", headers=ME).json()
    a, b = run["leads"]
    assert a["status"] == "done" and a["score"] == 30 + 25 + 10 + 5 - 5 and a["opener"].startswith("I noticed")
    assert a["facts"] == 2 and a["reasons"][0]["why"] == "serves coffee"
    assert b["status"] == "failed" and "malformed" in b["error"] and run["finished"] == 2
    full = client.get(f"/api/leads/{a['id']}", headers=ME).json()
    assert full["result"]["facts"][1]["url"] == "https://hilltopbakery.example"
    assert client.get(f"/api/runs/{rid}", headers=YOU).status_code == 404
    assert client.get(f"/api/leads/{a['id']}", headers=YOU).status_code == 404
    csv = client.get(f"/api/runs/{rid}/csv?v=visitor-aaaa-1111")
    assert csv.status_code == 200 and "Hilltop Bakery" in csv.text and "Mountain Roasting" in csv.text
    assert client.get(f"/api/runs/{rid}/csv").status_code == 404
    assert [x["id"] for x in client.get("/api/runs", headers=ME).json()["mine"]] == [rid]
    assert client.get("/api/runs", headers=YOU).json()["mine"] == []
    assert client.delete(f"/api/runs/{rid}", headers=YOU).status_code == 404
    assert client.delete(f"/api/runs/{rid}", headers=ME).json() == {"deleted": rid}


def test_limits_and_validation(client):
    six = {"companies": [{"name": f"Bakery {i}"} for i in range(6)]}
    assert client.post("/api/runs", json=six, headers=ME).status_code == 400
    assert client.post("/api/runs", json={"companies": [{"name": "X Bakery", "website": "not a site"}]}, headers=ME).status_code == 422
    assert client.post("/api/runs", json={"companies": [{"name": "Hilltop"}]}).status_code == 400      # no visitor id
    for _ in range(3):
        assert client.post("/api/runs", json={"companies": [{"name": "Hilltop Bakery"}]}, headers=ME).status_code == 200
    assert client.post("/api/runs", json={"companies": [{"name": "Hilltop Bakery"}]}, headers=ME).status_code == 429


def test_sample_run_is_shared_and_read_only(client):
    from scout import db
    from scout.runs import create
    with db.connect() as conn:
        rid = create(conn, [{"name": "Hilltop Bakery", "website": "", "city": ""}], kind="sample", title="Sample")
    assert client.get("/api/runs", headers=YOU).json()["sample"]["id"] == rid
    assert client.get(f"/api/runs/{rid}").status_code == 200
    assert client.get(f"/api/runs/{rid}/csv").status_code == 200
    assert client.delete(f"/api/runs/{rid}", headers=ME).status_code == 403
