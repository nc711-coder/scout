"use client";

import { useEffect, useMemo, useState } from "react";
import { api, ApiError, type Run } from "@/lib/api";
import { parseLine } from "@/lib/format";

const EXAMPLE = `Tartine, tartinebakery.com, San Francisco
Zingerman's Bakehouse, zingermansbakehouse.com, Ann Arbor
Stumptown Coffee Roasters, stumptowncoffee.com, Portland`;

export default function NewRun({ max, onClose, onStarted }: { max: number; onClose: () => void; onStarted: (r: Run) => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const rows = useMemo(() => text.split("\n").map(parseLine).filter((x): x is NonNullable<typeof x> => !!x), [text]);
  const tooMany = rows.length > max;
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);

  async function go() {
    setBusy(true); setError("");
    try {
      onStarted(await api.start(rows));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
      setBusy(false);
    }
  }

  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" role="dialog" aria-label="Research businesses" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head"><h2>Research businesses</h2><button className="link" onClick={onClose}>Close</button></div>
        <p className="hint">One business per line: <strong>name, website, city</strong>. The website and city help Scout find the right
          business. Up to {max} per run in this demo; each takes about 10 seconds.</p>
        <textarea rows={6} value={text} onChange={(e) => setText(e.target.value)} placeholder={EXAMPLE} aria-label="Businesses, one per line" />
        <button className="link" onClick={() => setText(EXAMPLE)}>Use the example</button>
        {rows.length > 0 && (
          <table className="preview">
            <thead><tr><th>Business</th><th>Website</th><th>City</th></tr></thead>
            <tbody>{rows.slice(0, max + 2).map((r, i) => (
              <tr key={i} className={i >= max ? "over" : ""}><td>{r.name}</td><td>{r.website || <em>none</em>}</td><td>{r.city || <em>none</em>}</td></tr>
            ))}</tbody>
          </table>
        )}
        {tooMany && <p className="error">That&apos;s {rows.length}; the demo researches up to {max} at a time.</p>}
        {error && <p className="error">{error}</p>}
        <div className="actions">
          <button className="primary" disabled={busy || !rows.length || tooMany} onClick={go}>
            {busy ? "Starting…" : `Research ${rows.length || ""} ${rows.length === 1 ? "business" : "businesses"}`}
          </button>
          <button className="secondary" onClick={onClose}>Cancel</button>
        </div>
        <p className="meta">Only public, business-level information is used. Nothing is sent to the businesses.</p>
      </div>
    </div>
  );
}
