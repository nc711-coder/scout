"""Score how well a business fits Fernwood's wholesale program, from checked facts only.

The AI answers a fixed list of yes/no/unknown questions and must point to the facts behind each answer; the
score itself is plain arithmetic in code (WEIGHTS below), so it's the same every time for the same answers and
every point can be explained.

    fit = score(facts, llm)   -> {"score": 0-100, "tier", "answers": {...}, "reasons": [...], "unknown": [...]}
"""
from __future__ import annotations

# The ideal customer, as Fernwood's wholesale team describes it.
IDEAL = """Fernwood Coffee Roasters sells wholesale coffee (1 kg bags, 30% off retail, minimum 4 bags, ships free,
US only) to independent cafés, bakeries, restaurants and offices in the United States. Best fits serve coffee
every day, care about quality, and have steady volume (several locations, catering, a busy menu, a large team).
Not a fit: businesses that roast their own coffee, big chains with central buying, or anyone outside the US."""

QUESTIONS = {
    "serves_coffee": "Does the business serve or sell coffee drinks to customers or staff? (yes if the facts mention "
                     "its café(s), coffee bar, espresso, coffee drinks or a coffee brand it pours)",
    "in_us": "Is the business (or at least one location) in the United States? (a US city or state means yes; "
             "if every address or city in the facts is in another country, e.g. London, Paris, VIC/NSW Australia, "
             "Ontario, the answer is no)",
    "roasts_own": "Does the business roast its own coffee, or own the roastery that supplies it?",
    "big_chain": "Is it a large chain that buys centrally? (yes if: more than 15 locations, franchises, described as "
                 "multinational, international or nationwide, more than 500 employees, or owned by a large "
                 "restaurant group)",
    "quality_focus": "Do they talk about quality, craft, sourcing, scratch-made food, an award, or specialty coffee?",
    "volume": "Are there signs of steady volume: several locations, catering, events, a large team or long hours?",
    "has_roaster": "Do they name a coffee roaster or coffee brand that they serve or that supplies them?",
}

# Points for a "yes" and for a "no"; "unknown" scores 0. Start at 30.
WEIGHTS = {
    "serves_coffee": (+25, -30),
    "in_us": (+10, -40),
    "roasts_own": (-45, +5),
    "big_chain": (-25, +5),
    "quality_focus": (+10, 0),
    "volume": (+10, 0),
    "has_roaster": (-5, +5),
}
BASE = 30
# Deal-breakers: whatever else is true, the score can't go above this.
CAPS = {("serves_coffee", "no"): 15, ("in_us", "no"): 10, ("roasts_own", "yes"): 20, ("big_chain", "yes"): 35}

WHY = {
    ("serves_coffee", "yes"): "serves coffee", ("serves_coffee", "no"): "doesn't serve coffee",
    ("in_us", "yes"): "in the US", ("in_us", "no"): "outside the US (Fernwood ships to the US only)",
    ("roasts_own", "yes"): "roasts its own coffee", ("roasts_own", "no"): "doesn't roast its own",
    ("big_chain", "yes"): "large chain, likely buys centrally", ("big_chain", "no"): "independent or small group",
    ("quality_focus", "yes"): "cares about quality and craft",
    ("volume", "yes"): "steady volume",
    ("has_roaster", "yes"): "already has a roaster (would need to switch)", ("has_roaster", "no"): "no roaster named",
}

SYSTEM = f"""You qualify sales leads for a coffee roaster's wholesale team.

{IDEAL}

Answer each question using ONLY the numbered facts given (all are checked against the business's web pages).
Reply with a JSON object: {{"answers": {{question key: {{"answer": "yes"|"no"|"unknown", "facts": [fact numbers]}}}}}}
Questions:
{chr(10).join(f'  "{k}": {v}' for k, v in QUESTIONS.items())}
Rules:
- "yes" or "no" when the facts show it, reading them the way a sensible person would (a business with cafés
  serves coffee; a shop in Chicago is in the US). List the fact numbers that show it. Otherwise "unknown" with [].
- Not mentioned is not "no". Answer "no" only when a fact says so (e.g. "we don't serve coffee", every location
  abroad). A menu or list that leaves something out means "unknown".
- Don't use general knowledge about the business, even if you recognise it."""

SCHEMA = {"type": "object", "properties": {"answers": {"type": "object", "properties": {
    k: {"type": "object", "properties": {"answer": {"type": "string", "enum": ["yes", "no", "unknown"]},
                                        "facts": {"type": "array", "items": {"type": "integer"}}},
        "required": ["answer", "facts"]} for k in QUESTIONS}, "required": list(QUESTIONS)}}, "required": ["answers"]}


def numbered(facts: list[dict]) -> str:
    return "\n".join(f"{i}. [{f['topic']}] {f['fact']} (quote: \"{f['quote']}\")" for i, f in enumerate(facts, 1))


def tier(score: int) -> str:
    return "Strong fit" if score >= 70 else "Possible fit" if score >= 45 else "Weak fit"


def compute(answers: dict, n_facts: int) -> dict:
    """The score from the answers: plain arithmetic. An answer without valid facts behind it counts as unknown."""
    clean = {}
    for k in QUESTIONS:
        a = answers.get(k) or {}
        ids = [i for i in a.get("facts") or [] if isinstance(i, int) and 1 <= i <= n_facts]
        ans = a.get("answer") if a.get("answer") in ("yes", "no") and ids else "unknown"
        clean[k] = {"answer": ans, "facts": ids if ans != "unknown" else []}
    score, reasons = BASE, []
    for k, (yes, no) in WEIGHTS.items():
        ans = clean[k]["answer"]
        pts = yes if ans == "yes" else no if ans == "no" else 0
        score += pts
        if pts and (k, ans) in WHY:
            reasons.append({"points": pts, "why": WHY[(k, ans)], "facts": clean[k]["facts"]})
    cap = min([c for (k, a), c in CAPS.items() if clean[k]["answer"] == a] or [100])
    score = max(0, min(score, cap, 100))
    unknown = [k for k, v in clean.items() if v["answer"] == "unknown"]
    reasons.sort(key=lambda r: -abs(r["points"]))
    return {"score": score, "tier": tier(score), "answers": clean, "reasons": reasons, "unknown": unknown,
            "capped": cap < 100}


def score(facts: list[dict], llm) -> dict:
    if not facts:
        out = compute({}, 0)
        return {**out, "score": 0, "tier": "Not enough information"}
    data, _ = llm.json(SYSTEM, numbered(facts), SCHEMA, name="fit", max_tokens=2000)
    return compute(data.get("answers") or {}, len(facts))
