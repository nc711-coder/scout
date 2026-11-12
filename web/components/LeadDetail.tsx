"use client";

import { useEffect, useState } from "react";
import { api, ApiError, type Lead } from "@/lib/api";
import { host, QUESTION, TOPIC, tone } from "@/lib/format";

export default function LeadDetail({ id, onBack }: { id: number; onBack: () => void }) {
  const [lead, setLead] = useState<Lead | null>(null);
  const [error, setError] = useState("");
  const [lit, setLit] = useState<number[]>([]);

  useEffect(() => {
    setLead(null); setError(""); setLit([]);
    api.lead(id).then(setLead).catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't load this lead."));
  }, [id]);

  if (error) return <div className="detail"><button className="back" onClick={onBack}>← All businesses</button><p className="error">{error}</p></div>;
  if (!lead) return <div className="detail"><p className="hint">Loading…</p></div>;

  const r = lead.result;
  const t = tone(lead.score);
  return (
    <article className="detail">
      <button className="back" onClick={onBack}>← All businesses</button>
      <header className="detail-head">
        <div>
          <h2>{lead.name}</h2>
          <p className="from">
            {lead.website && <a href={lead.website.startsWith("http") ? lead.website : `https://${lead.website}`} target="_blank" rel="noreferrer">{host(lead.website.startsWith("http") ? lead.website : `https://${lead.website}`)}</a>}
            {lead.website && lead.city && " · "}{lead.city}
          </p>
        </div>
        {lead.score !== null && (
          <div className={`big-score ${t}`}><span className="num">{lead.score}</span><span className="of">/100</span><span className="tier">{lead.tier}</span></div>
        )}
      </header>

      {lead.status === "failed" && <div className="flag"><strong>Couldn&apos;t finish:</strong> {lead.error}</div>}
      {lead.status !== "done" && lead.status !== "failed" && <p className="hint">{lead.stage || "Waiting its turn"}…</p>}

      {r && (
        <>
          {!r.site_read && <p className="note">Scout couldn&apos;t read this website, so it relied on web search.</p>}

          <section>
            <h3>First line for the email</h3>
            {r.opener.line ? (
              <div className="opener">
                <p>{r.opener.line}</p>
                <span className="meta">Based on fact {r.opener.fact}{r.opener.url && <> · <a href={r.opener.url} target="_blank" rel="noreferrer">{host(r.opener.url)}</a></>}</span>
              </div>
            ) : <p className="hint">None written: {r.opener.why}.</p>}
          </section>

          <section>
            <h3>Why this score</h3>
            {r.fit.capped && <p className="note">A deal-breaker caps this score, whatever else is true.</p>}
            <ul className="reasons">
              {r.fit.reasons.map((x) => (
                <li key={x.why} onMouseEnter={() => setLit(x.facts)} onMouseLeave={() => setLit([])}>
                  <span className={`pts ${x.points > 0 ? "up" : "down"}`}>{x.points > 0 ? "+" : ""}{x.points}</span>
                  <span>{x.why}</span>
                  <span className="refs">{x.facts.map((n) => <button key={n} onClick={() => document.getElementById(`fact-${n}`)?.scrollIntoView({ behavior: "smooth", block: "center" })}>{n}</button>)}</span>
                </li>
              ))}
            </ul>
            <p className="meta">Starts at 30. {r.fit.unknown.length > 0 && <>Not known from its pages: {r.fit.unknown.map((k) => QUESTION[k] || k).join(", ").toLowerCase()} (no points either way).</>}</p>
          </section>

          <section>
            <h3>Checked facts ({r.facts.length})</h3>
            <ol className="facts">
              {r.facts.map((f, i) => (
                <li key={i} id={`fact-${i + 1}`} className={lit.includes(i + 1) ? "lit" : ""}>
                  <span className="n">{i + 1}</span>
                  <div>
                    <p className="fact"><span className="tag">{TOPIC[f.topic] || f.topic}</span> {f.fact}</p>
                    <blockquote>&ldquo;{f.quote}&rdquo;</blockquote>
                    <a className="src" href={f.url} target="_blank" rel="noreferrer">{host(f.url)}</a>
                    <span className="src-kind"> · {f.source === "site" ? "their website" : "web search"}</span>
                  </div>
                </li>
              ))}
            </ol>
          </section>

          {r.dropped.length > 0 && (
            <details className="more">
              <summary>{r.dropped.length} {r.dropped.length === 1 ? "claim" : "claims"} dropped by the checks</summary>
              <ul className="dropped">
                {r.dropped.map((d, i) => <li key={i}><span>{d.fact}</span><span className="why">{d.why}</span></li>)}
              </ul>
            </details>
          )}
          <details className="more">
            <summary>Pages read ({r.pages.filter((p) => !p.error).length} of {r.pages.length})</summary>
            <ul className="pages">
              {r.pages.map((p) => (
                <li key={p.id}><a href={p.url} target="_blank" rel="noreferrer">{host(p.url)}{new URL(p.url).pathname.replace(/\/$/, "")}</a>
                  <span className="why">{p.error ? `couldn't read: ${p.error}` : p.source === "site" ? "their website" : "web search"}</span></li>
              ))}
            </ul>
          </details>
          <p className="meta">Researched in {r.seconds.toFixed(0)}s.</p>
        </>
      )}
    </article>
  );
}
