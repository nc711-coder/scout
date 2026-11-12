"""The first line of an outreach email, built on one checked fact.

The AI picks a fact and writes one sentence about it; code then checks the sentence: it must name a real
fact, stay short, and every number or capitalised name in it must come from that fact's quote (or the business's
own name), so it can't invent a detail.
"""
from __future__ import annotations

import re
from datetime import date

from .fit import numbered

SYSTEM = """Write the first line of a short, friendly email from Fernwood Coffee's wholesale team to this business.
Base it on ONE of the numbered facts: something specific and real that shows we looked at their business.

Reply with a JSON object: {"fact": fact number, "line": the sentence}
Rules for the line:
- One sentence, 12 to 30 words, plain and warm. No flattery or gushing ("amazing", "love", "thrilled").
- Mention only what that fact's quote says; no other details, numbers or names.
- Only about them: don't pitch, don't mention us or Fernwood (the email does that next). Keep lists short.
- Prefer something current: news from the last two years, a distinctive offering, or how they serve coffee.
  Don't present anything older than two years as news ("congrats on opening in 2016" sounds out of touch).
  Avoid generic facts like the address."""

SCHEMA = {"type": "object", "properties": {"fact": {"type": "integer"}, "line": {"type": "string"}},
          "required": ["fact", "line"]}

PITCH = re.compile(r"\bour\b|\bwe (offer|sell|roast|supply|provide|can)\b|\bwholesale\b", re.I)
HYPE = re.compile(r"\b(amazing|incredible|love|loved|huge fan|awesome|stunning|world-class|best in|thrilled|"
                  r"excited|impressed|delighted|blown away)\b", re.I)
NAMEISH = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-zA-Z'&-]+(?:\s+[A-Z][a-zA-Z'&-]+)*")


def check_line(line: str, fact: dict, company: str) -> list[str]:
    problems = []
    n = len(line.split())
    if not 8 <= n <= 35:
        problems.append(f"the line is {n} words; it should be 12 to 30")
    if HYPE.search(line):
        problems.append("the line uses flattery words")
    old = [y for y in re.findall(r"\b(19\d\d|20\d\d)\b", line) if int(y) < date.today().year - 2]
    if old:
        problems.append(f"{old[0]} is more than two years ago; pick something current")
    if PITCH.search(line):
        problems.append("the line pitches; it should only be about them")
    if "fernwood" in line.lower():
        problems.append("the line mentions Fernwood")
    allowed = (fact["quote"] + " " + fact["fact"] + " " + company).lower()
    for num in re.findall(r"\d[\d,.]*", line):
        if num.strip(".,") not in allowed:
            problems.append(f"{num} isn't in the fact")
    for name in NAMEISH.findall(line):
        if name.lower() not in allowed and name not in ("I", "We", "Your", "Congrats", "Congratulations", "Saw", "Noticed"):
            problems.append(f"\"{name}\" isn't in the fact")
    return problems


def write(facts: list[dict], company: str, llm) -> dict:
    """{"line", "fact", "url"} or {"line": "", "why": ...} when no checked line could be written."""
    if not facts:
        return {"line": "", "why": "no checked facts to base it on"}
    prompt = f"Today is {date.today():%B %d, %Y}.\nBusiness: {company}\n\nFacts:\n{numbered(facts)}"
    last = []
    for attempt in range(2):
        extra = "" if not last else f"\n\nYour last line had problems: {'; '.join(last)}. Write a new one."
        data, _ = llm.json(SYSTEM, prompt + extra, SCHEMA, name="opener", max_tokens=1200)
        i, line = data.get("fact"), " ".join(str(data.get("line") or "").split())
        if not isinstance(i, int) or not 1 <= i <= len(facts):
            last = ["it didn't name one of the numbered facts"]
            continue
        last = check_line(line, facts[i - 1], company)
        if not last:
            return {"line": line, "fact": i, "url": facts[i - 1]["url"], "quote": facts[i - 1]["quote"]}
    return {"line": "", "why": "; ".join(last) or "no line passed the checks"}
