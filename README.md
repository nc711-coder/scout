# Scout: an AI lead research agent that cites its sources

Scout researches businesses for **Fernwood Coffee's** wholesale team (fictional): it reads each business's
website, searches the web, and lists what it learned, **with a quote and a link for every fact**. Code checks
that each quote really is on the page; anything that can't be checked is dropped.

**Live demo:** https://scout-swart-omega.vercel.app/

## What it does

* **Researches each business**: reads its website (homepage plus about, locations and similar pages) and runs two
web searches, about 3 Tavily credits a business.
* **Keeps only checked facts.** Every fact comes with a quote and a link; code checks the quote is really on that
page, and a second AI check makes sure the quote backs up the fact. Search results about a different business
with a similar name (another city, another website) are skipped.
* **Scores the fit** for Fernwood's wholesale program. The AI answers seven yes/no/unknown questions, each tied to
facts; the score is plain arithmetic in code, and deal-breakers (roasts its own coffee, big chain, outside the
US) cap it. Every point is shown with its reason.
* **Writes a first line** for the email from one checked fact. Code rejects a line with any name or number not in
that fact, flattery, a sales pitch, or news more than two years old; if no line passes, none is written.
* **Runs in batches** on the page, with live progress, and downloads as CSV for Google Sheets or Excel.

## How well it works

Tested on real, public businesses, each labelled by hand before testing: good fits (independent US bakeries and
cafés that serve coffee) and poor fits for a stated reason (they roast their own coffee, are a big chain, or are
outside the US). Tests replay a saved snapshot of the pages, so only the AI's answers can change between runs
([`evals/`](evals)).

|Check|Main set (27, used for tuning)|Held-out set (11, run once)|
|-|-|-|
|Good fits scored 45+|10/11|5/5|
|Poor fits scored under 45|16/16|5/5|
|The right deal-breaker found|15/16|5/5|
|First line written for leads scoring 45+|10/10|5/5|
|Errors|0|1 (the AI returned malformed output for one business)|

The held-out numbers are from its first run. That run stopped on one business when the AI returned malformed
output; a second run on the same saved pages scored all 11 correctly (6/6 poor fits, deal-breaker found each time).

Facts the checks dropped (quote not on the page, or not backing up the fact): about 27%. Those never reach the
score or the first line.

**Known limits.** Data-aggregator pages can be wrong: one claimed a 10-shop bakery had "165 units", and Scout
believed it. Borderline businesses (a bakery in 8 states) can score either side of 45 from run to run. Labels are
my judgment from what each business is publicly known for. After the held-out run, one rule was added to first
lines (no year more than two years old); it doesn't affect any score.

## Run it on your computer

```powershell
python -m venv .venv
.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
copy .env.example .env                 # DATABASE\_URL, GROQ\_API\_KEY, TAVILY\_API\_KEY
python -m scout.lead "Tartine" https://tartinebakery.com --city "San Francisco"     # one business, in the terminal
python -m scout.db                     # the tables, for the page
python -m scout.prepare                # the sample run (from the saved snapshot, no Tavily credits)
uvicorn scout.app:app --reload         # the API on http://127.0.0.1:8000
```

The page (Node.js 20+), in a second terminal: `cd web`, `copy .env.example .env.local`, `npm install`, `npm run dev`.

Tests: `python -m pytest` (set `TEST\_DATABASE\_URL` to a throwaway Postgres database for the API tests).
Evals: `python -m evals.run` (replays `snapshots/evals.json`). Online: [DEPLOY.md](DEPLOY.md).

## Stack

Python · FastAPI · PostgreSQL (Supabase) · Tavily (web search and page reading) · Groq (`openai/gpt-oss-120b`) ·
Next.js · Google Cloud Run · Vercel.

