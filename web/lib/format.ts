export const QUESTION: Record<string, string> = {
  serves_coffee: "Serves coffee", in_us: "In the US", roasts_own: "Roasts its own coffee", big_chain: "Large chain",
  quality_focus: "Cares about quality", volume: "Steady volume", has_roaster: "Names a roaster",
};

export const TOPIC: Record<string, string> = {
  business_type: "Business", location: "Location", locations: "Locations", coffee: "Coffee", roaster: "Roaster",
  size: "Size", news: "News", values: "Values", offerings: "Offerings",
};

export function tone(score: number | null | undefined): "strong" | "possible" | "weak" | "none" {
  if (score === null || score === undefined) return "none";
  return score >= 70 ? "strong" : score >= 45 ? "possible" : "weak";
}

export function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function when(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

/** "Flour Bakery, flourbakery.com, Boston" -> a company. The part that looks like a website is the website. */
export function parseLine(line: string): { name: string; website: string; city: string } | null {
  const parts = line.split(/[,\t]/).map((s) => s.trim()).filter(Boolean);
  if (!parts.length) return null;
  const isSite = (s: string) => /^(https?:\/\/)?([a-z0-9-]+\.)+[a-z]{2,}(\/\S*)?$/i.test(s);
  const website = parts.slice(1).find(isSite) || "";
  const rest = parts.slice(1).filter((s) => s !== website);
  return { name: parts[0], website, city: rest.join(", ") };
}
