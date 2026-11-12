from scout import fit, opener

FACTS = [
    {"topic": "coffee", "fact": "Serves espresso from Mountain Roasting Co.", "quote": "We pour espresso from our neighbors at Mountain Roasting Co. every morning", "url": "https://h.example"},
    {"topic": "location", "fact": "In Asheville, North Carolina", "quote": "baking sourdough in Asheville, North Carolina since 2009", "url": "https://h.example"},
    {"topic": "news", "fact": "Opened a third shop on Haywood Road in March 2026", "quote": "We opened our third shop on Haywood Road in March 2026", "url": "https://h.example/about"},
]


def ans(**kw):
    return {k: {"answer": v[0], "facts": v[1]} for k, v in kw.items()}


def test_score_is_arithmetic_and_explained():
    out = fit.compute(ans(serves_coffee=("yes", [1]), in_us=("yes", [2]), roasts_own=("no", [1]), big_chain=("no", [3]),
                          quality_focus=("unknown", []), volume=("yes", [3]), has_roaster=("yes", [1])), 3)
    assert out["score"] == 30 + 25 + 10 + 5 + 5 + 10 - 5 == 80 and out["tier"] == "Strong fit"
    assert out["unknown"] == ["quality_focus"] and out["reasons"][0]["why"] == "serves coffee"


def test_answers_need_facts_and_deal_breakers_cap():
    # "yes" with no fact behind it counts as unknown; a fact number that doesn't exist doesn't count either
    out = fit.compute(ans(serves_coffee=("yes", []), in_us=("yes", [9])), 3)
    assert out["answers"]["serves_coffee"]["answer"] == "unknown" and out["answers"]["in_us"]["answer"] == "unknown"
    roaster = fit.compute(ans(serves_coffee=("yes", [1]), in_us=("yes", [2]), roasts_own=("yes", [1]),
                              quality_focus=("yes", [1]), volume=("yes", [3])), 3)
    assert roaster["score"] <= 20 and roaster["capped"] and roaster["tier"] == "Weak fit"
    abroad = fit.compute(ans(serves_coffee=("yes", [1]), in_us=("no", [2])), 3)
    assert abroad["score"] <= 10


def test_no_facts_no_score():
    assert fit.score([], llm=None)["tier"] == "Not enough information"


class LLM:
    def __init__(self, answers):
        self.answers, self.prompts = list(answers), []

    def json(self, system, user, schema=None, name="", max_tokens=0):
        self.prompts.append(user)
        return self.answers.pop(0), {}


def test_opener_checks_names_and_numbers_then_retries():
    bad = {"fact": 3, "line": "Congrats on opening your fourth shop on Haywood Road in April 2026, the Asheville crowd must be thrilled."}
    good = {"fact": 3, "line": "Congrats on opening your third shop on Haywood Road this March; that's a big step for a neighborhood bakery."}
    llm = LLM([bad, good])
    out = opener.write(FACTS, "Hilltop Bakery", llm)
    assert out["line"] == good["line"] and out["fact"] == 3 and out["url"] == "https://h.example/about"
    assert "April" in llm.prompts[1]                       # the retry is told what was wrong


def test_opener_gives_up_rather_than_invent():
    hype = {"fact": 1, "line": "We absolutely love what you're doing with espresso at your amazing bakery in town, truly."}
    out = opener.write(FACTS, "Hilltop Bakery", LLM([hype, hype]))
    assert out["line"] == "" and "flattery" in out["why"]
    assert opener.write(FACTS, "Hilltop Bakery", LLM([{"fact": 7, "line": "x"}] * 2))["line"] == ""


def test_check_line_rules():
    f = FACTS[0]
    assert opener.check_line("Saw that you pour espresso from your neighbors at Mountain Roasting Co. every single morning.", f, "Hilltop Bakery") == []
    assert any("Fernwood" in p for p in opener.check_line("Fernwood noticed you pour espresso from Mountain Roasting Co. every morning there.", f, "Hilltop"))


def test_big_chain_caps_the_score():
    out = fit.compute(ans(serves_coffee=("yes", [1]), in_us=("yes", [2]), big_chain=("yes", [3]), volume=("yes", [3]),
                          quality_focus=("yes", [1])), 3)
    assert out["score"] <= 35 and out["capped"] and out["tier"] == "Weak fit"


def test_first_line_doesnt_pitch():
    f = FACTS[0]
    assert any("pitches" in p for p in opener.check_line(
        "I noticed you pour espresso from Mountain Roasting Co., which fits our focus on quality coffee.", f, "Hilltop"))


def test_first_line_cant_be_old_news():
    from datetime import date
    old = date.today().year - 3
    f = {"topic": "news", "fact": f"Won Best Bakery in {old}", "quote": f"named Best Bakery in {old} by readers", "url": "u"}
    assert any("two years" in p for p in opener.check_line(f"Congratulations on being named Best Bakery in {old} by your readers there.", f, "Hilltop"))
