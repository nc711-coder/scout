"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import LeadDetail from "@/components/LeadDetail";
import NewRun from "@/components/NewRun";
import { api, ApiError, type LeadRow, type Run, type RunSummary } from "@/lib/api";
import { host, tone, when } from "@/lib/format";

const REPO = "https://github.com/nc711-coder/scout";
type Filter = "all" | "strong" | "possible" | "weak";

export default function Home() {
  const [sample, setSample] = useState<RunSummary | null>(null);
  const [mine, setMine] = useState<RunSummary[]>([]);
  const [max, setMax] = useState(5);
  const [run, setRun] = useState<Run | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [byScore, setByScore] = useState(true);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");

  const loadList = useCallback(async () => {
    const d = await api.runs();
    setSample(d.sample); setMine(d.mine); setMax(d.max_per_run);
    return d;
  }, []);

  const show = useCallback(async (id: number) => {
    try {
      setRun(await api.run(id)); setOpen(null); setFilter("all"); setError("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load that run.");
    }
  }, []);

  useEffect(() => {
    loadList().then((d) => { const first = d.mine.find((r) => r.status !== "done") || d.sample || d.mine[0]; if (first) show(first.id); })
      .catch((e) => setError(e.message));
  }, [loadList, show]);

  // while a run is going, check on it every few seconds
  useEffect(() => {
    if (!run || run.status === "done") return;
    const t = setInterval(async () => {
      try {
        const r = await api.run(run.id);
        setRun(r);
        if (r.status === "done") loadList();
      } catch { /* keep trying */ }
    }, 2500);
    return () => clearInterval(t);
  }, [run, loadList]);

  const leads = useMemo(() => {
    if (!run) return [];
    const xs = run.leads.filter((l) => filter === "all" || tone(l.score) === filter);
    return byScore ? [...xs].sort((a, b) => (b.score ?? -1) - (a.score ?? -1) || a.position - b.position) : xs;
  }, [run, filter, byScore]);
  const count = (f: Filter) => run ? run.leads.filter((l) => tone(l.score) === f).length : 0;

  async function remove() {
    if (!run) return;
    try {
      await api.remove(run.id);
      const d = await loadList();
      if (d.sample) show(d.sample.id); else setRun(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't delete it.");
    }
  }

  return (
    <main className="app">
      <header className="top">
        <div className="brand"><span className="logo" aria-hidden="true">◎</span><span className="wordmark">Scout</span>
          <span className="sub">AI lead research for Fernwood Coffee&apos;s wholesale team (fictional)</span></div>
        <nav><button className="primary" onClick={() => setAdding(true)}>Research businesses</button></nav>
      </header>
      <p className="lede">
        Give Scout a list of businesses. It reads each website, searches the web, and <strong>keeps only facts it can quote
        from a page</strong>, with the link. Then it scores the fit for Fernwood&apos;s wholesale program, explaining every point,
        and writes a first line for the email.
      </p>
      {error && <p className="error banner">{error}</p>}

      <div className="runs" role="tablist" aria-label="Runs">
        {sample && <button role="tab" className={run?.id === sample.id ? "on" : ""} onClick={() => show(sample.id)}>Sample run · {sample.total}</button>}
        {mine.map((r) => (
          <button role="tab" key={r.id} className={run?.id === r.id ? "on" : ""} onClick={() => show(r.id)} title={r.title}>
            {r.status !== "done" && <span className="dot" aria-hidden="true" />}Your run · {when(r.created_at)}
          </button>
        ))}
      </div>

      {run && (
        <section className="run">
          <div className="run-head">
            <div>
              <h2>{run.kind === "sample" ? "Sample run" : "Your run"}</h2>
              <p className="meta">
                {run.kind === "sample" ? `${run.total} real cafés, bakeries, roasters and chains, researched from saved pages. ` : ""}
                {run.status === "done" ? `${run.strong} strong · ${run.possible} possible · ${run.total - run.strong - run.possible} weak or unfinished`
                  : `Researching ${run.finished} of ${run.total} done…`}
              </p>
              {run.status !== "done" && <div className="bar"><span style={{ width: `${(100 * run.finished) / Math.max(1, run.total)}%` }} /></div>}
            </div>
            <div className="run-actions">
              <a className="secondary" href={api.csvUrl(run.id)} download>Download CSV</a>
              {run.mine && run.status === "done" && <button className="link danger-text" onClick={remove}>Delete run</button>}
            </div>
          </div>

          <div className={`split ${open ? "has-open" : ""}`}>
            <div className="list">
              <div className="filters">
                {([["all", `All ${run.leads.length}`], ["strong", `Strong ${count("strong")}`], ["possible", `Possible ${count("possible")}`],
                   ["weak", `Weak ${count("weak")}`]] as [Filter, string][]).map(([k, label]) => (
                  <button key={k} className={filter === k ? "on" : ""} onClick={() => setFilter(k)}>{label}</button>
                ))}
                <button className="sort" onClick={() => setByScore(!byScore)}>{byScore ? "Sorted by score" : "In your order"}</button>
              </div>
              {leads.map((l) => <Row key={l.id} l={l} selected={open === l.id} onOpen={() => setOpen(l.id)} />)}
              {!leads.length && <p className="empty">None here.</p>}
            </div>
            <section className="pane">
              {open ? <LeadDetail id={open} onBack={() => setOpen(null)} />
                : <div className="placeholder"><p>Pick a business to see its checked facts with sources, every point of its score, and the first line.</p></div>}
            </section>
          </div>
        </section>
      )}

      <footer className="foot">
        <p>Scout uses public, business-level information only. Every fact links to the page it came from; claims it
          can&apos;t check against the page are dropped, not guessed.</p>
        <p><a href={REPO}>Source code on GitHub</a> · Fernwood Coffee is fictional; the businesses are real.</p>
      </footer>

      {adding && <NewRun max={max} onClose={() => setAdding(false)} onStarted={(r) => { setAdding(false); setRun(r); setOpen(null); loadList(); }} />}
    </main>
  );
}

/** Why a lead got no first line: its deal-breakers, or too few signs of a fit in what Scout could check. */
function weakWhy(l: LeadRow): string {
  const minus = (l.reasons || []).filter((r) => r.points < 0).map((r) => r.why);
  if (minus.length) return minus.slice(0, 2).join("; ");
  return l.facts ? `Too few signs of a fit in ${l.facts} checked facts` : "Couldn't find facts to check";
}

function Row({ l, selected, onOpen }: { l: LeadRow; selected: boolean; onOpen: () => void }) {
  const t = tone(l.score);
  const busy = l.status === "queued" || l.status === "running";
  return (
    <button className={`row ${selected ? "selected" : ""}`} onClick={onOpen} disabled={busy && l.status === "queued"}>
      <span className={`score ${t}`}>{l.score ?? (busy ? "…" : "–")}</span>
      <span className="row-main">
        <span className="who">{l.name}</span>
        <span className="where">{[l.city, l.website && host(l.website.startsWith("http") ? l.website : `https://${l.website}`)].filter(Boolean).join(" · ")}</span>
        {l.status === "done" && (l.opener ? <span className="snippet">&ldquo;{l.opener}&rdquo;</span>
          : <span className="snippet muted">{weakWhy(l)}</span>)}
        {l.status === "running" && <span className="snippet stage">{l.stage}…</span>}
        {l.status === "queued" && <span className="snippet muted">Waiting its turn</span>}
        {l.status === "failed" && <span className="snippet error-text">Couldn&apos;t finish: {l.error}</span>}
      </span>
    </button>
  );
}
