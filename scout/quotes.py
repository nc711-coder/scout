"""Is a quote really on the page? Code decides, not the AI.

Pages come back as markdown, so links, bold, headings and typography are flattened on both sides before
comparing, and only the words are compared (not commas or bullets), so a quote of a list ("People Matter,
Consistent Excellence") matches the list on the page. A quote must be at least 4 words and appear word for
word; "..." may skip part of the page, as long as each piece (2+ words in the middle) is there, in order.
"""
from __future__ import annotations

import re

_ODD = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
                      "‑": "-", " ": " ", "…": "..."})


def flatten(text: str) -> str:
    t = (text or "").translate(_ODD)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)                 # images
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)              # [text](url) -> text
    t = re.sub(r"<[^>]+>", " ", t)                              # stray html
    t = re.sub(r"[*_`#>|~]+", " ", t)                           # markdown marks
    t = re.sub(r"[^\w$%&'.,:;!?/-]+", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def words(text: str) -> int:
    return len(flatten(text).split())


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9$%]+(?:'[a-z]+)?", flatten(text))


def quote_on_page(quote: str, page_text: str) -> bool:
    pieces = [tokens(p) for p in re.split(r"\.\.\.|\u2026|\[\.\.\.\]", quote or "")]
    pieces = [p for p in pieces if p]
    if sum(len(p) for p in pieces) < 4 or any(len(p) < 2 for p in pieces[1:-1]):
        return False
    page = " " + " ".join(tokens(page_text)) + " "
    at = 0
    for p in pieces:
        i = page.find(" " + " ".join(p) + " ", at)
        if i < 0:
            return False
        at = i + 1
    return True
