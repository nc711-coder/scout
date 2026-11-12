export type Reason = { points: number; why: string; facts: number[] };
export type Fact = { topic: string; fact: string; quote: string; url: string; source: "site" | "search"; narrowed_from?: string };
export type Dropped = { topic?: string; fact?: string; quote?: string; why: string };
export type Page = { id: string; url: string; title: string | null; source: string; error: string | null; chars: number };
export type Fit = {
  score: number; tier: string; capped?: boolean; reasons: Reason[]; unknown: string[];
  answers: Record<string, { answer: string; facts: number[] }>;
};
export type Opener = { line: string; fact?: number; url?: string; quote?: string; why?: string };
export type Result = {
  facts: Fact[]; dropped: Dropped[]; pages: Page[]; fit: Fit; opener: Opener; site_read: boolean; seconds: number; credits: number;
};
export type LeadRow = {
  id: number; position: number; name: string; website: string; city: string; status: string; stage: string;
  score: number | null; tier: string | null; opener: string | null; error: string | null;
  reasons?: Reason[] | null; facts?: number | null;
};
export type Lead = LeadRow & { result: Result | null };
export type RunSummary = {
  id: number; kind: "sample" | "visitor"; title: string; status: string; created_at: string; mine: boolean;
  total: number; finished: number; strong: number; possible: number;
};
export type Run = RunSummary & { leads: LeadRow[] };
export type NewCompany = { name: string; website: string; city: string };

export const API = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export function visitor(): string {
  try {
    let v = localStorage.getItem("scout-visitor");
    if (!v) {
      v = (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2) + Date.now()).replace(/[^A-Za-z0-9-]/g, "");
      localStorage.setItem("scout-visitor", v);
    }
    return v;
  } catch {
    return "visitor-session-" + Math.floor(Date.now() / 1000);
  }
}

export class ApiError extends Error {}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${API}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", "X-Visitor": visitor(), ...(init?.headers || {}) },
    });
  } catch {
    throw new ApiError("Couldn't reach Scout's server. It may be waking up; try again in a few seconds.");
  }
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    const d = data && data.detail;
    const msg = Array.isArray(d) ? d.map((x: any) => String(x.msg || "").replace(/^Value error, /, "")).join("; ") : d;
    throw new ApiError(msg || `The server answered with an error (${r.status}).`);
  }
  return data as T;
}

export const api = {
  runs: () => call<{ sample: RunSummary | null; mine: RunSummary[]; max_per_run: number }>("/api/runs"),
  run: (id: number) => call<Run>(`/api/runs/${id}`),
  lead: (id: number) => call<Lead>(`/api/leads/${id}`),
  start: (companies: NewCompany[]) => call<Run>("/api/runs", { method: "POST", body: JSON.stringify({ companies }) }),
  remove: (id: number) => call<{ deleted: number }>(`/api/runs/${id}`, { method: "DELETE" }),
  csvUrl: (id: number) => `${API}/api/runs/${id}/csv?v=${encodeURIComponent(visitor())}`,
};
