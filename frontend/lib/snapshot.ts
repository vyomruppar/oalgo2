/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Read-only snapshot data source for the static build (no backend). Maps an API path to a JSON file
 * exported by backend/scripts/export_snapshot.py and applies the query in the browser.
 */
type J = any;

export class SnapshotMissing extends Error {
  status = 404;
}

const cache = new Map<string, Promise<J>>();

function load(file: string): Promise<J> {
  let p = cache.get(file);
  if (!p) {
    p = fetch(`/data/${file}`, { cache: "no-cache" }).then((r) => {
      if (!r.ok) throw new SnapshotMissing(`${file} is not part of this snapshot`);
      return r.json();
    });
    p.catch(() => cache.delete(file));
    cache.set(file, p);
  }
  return p;
}

const PRICE_ROWS: Record<string, number> = { "3m": 63, "6m": 126, "1y": 252, "2y": 504, "5y": 504, max: 504 };
const COMPONENTS = ["value", "quality", "momentum", "earnings", "low_vol", "investment", "financial_strength", "technical", "market", "ml", "sentiment"];

function slicePrices(p: J, range: string): J {
  if (!p) throw new SnapshotMissing("No price history is stored for this stock in the snapshot");
  const n = Math.min(PRICE_ROWS[range] ?? 252, p.dates.length);
  const cut = (a: J[]) => a.slice(-n);
  const first = p.dates[p.dates.length - n];
  const ohlcv: J = {};
  for (const k of Object.keys(p.ohlcv)) ohlcv[k] = cut(p.ohlcv[k]);
  const indicators: J = {};
  for (const k of Object.keys(p.indicators)) indicators[k] = cut(p.indicators[k]);
  return { ...p, dates: cut(p.dates), ohlcv, indicators, dividends: p.dividends.filter((d: J) => d[0] >= first), splits: p.splits.filter((d: J) => d[0] >= first) };
}

function filterStocks(all: J, q: URLSearchParams): J {
  let out: J[] = all.items;
  const signal = q.get("signal");
  const passed = q.get("passed");
  const sector = q.get("sector");
  const text = (q.get("q") ?? "").toLowerCase();
  if (signal) out = out.filter((r) => r.signal === signal);
  if (passed != null) out = out.filter((r) => r.screen_pass === (passed === "true"));
  if (sector) out = out.filter((r) => r.sector === sector);
  if (text) out = out.filter((r) => r.symbol.toLowerCase().includes(text) || (r.company ?? "").toLowerCase().includes(text));
  const sort = q.get("sort") ?? "score";
  const key = sort.replace(/^-/, "");
  const num = (r: J): number | null => (key === "score" || key === "price" || key === "market_cap" ? r[key] : COMPONENTS.includes(key) ? r.components?.[key] : null) ?? null;
  out = [...out];
  if (key === "symbol") out.sort((a, b) => a.symbol.localeCompare(b.symbol));
  else out.sort((a, b) => (num(a) == null ? 1 : 0) - (num(b) == null ? 1 : 0) || (num(b) ?? 0) - (num(a) ?? 0));
  if (sort.startsWith("-")) out.reverse();
  const limit = Number(q.get("limit") ?? 100);
  const offset = Number(q.get("offset") ?? 0);
  return { total: out.length, items: out.slice(offset, offset + limit), sectors: [...new Set(out.map((r) => r.sector).filter(Boolean))].sort() };
}

function filterNews(all: J, q: URLSearchParams): J {
  const symbol = q.get("symbol")?.toUpperCase();
  const scope = q.get("scope") ?? "holdings";
  const minRel = Number(q.get("min_relevance") ?? 0);
  const limit = Number(q.get("limit") ?? 60);
  const want: string[] | null = symbol ? [symbol] : scope === "holdings" ? all.holdings : null;
  const items = all.items.filter((n: J) => n.relevance >= minRel && (want == null || n.symbols.some((s: string) => want.includes(s))));
  const sentiment: J = {};
  for (const [k, v] of Object.entries(all.sentiment)) if (want == null || want.includes(k)) sentiment[k] = v;
  return { engine: all.engine, scope: symbol ?? scope, items: items.slice(0, limit), sentiment, source: all.source };
}

// Alerts marked read are remembered in this browser only (the published data cannot be changed).
const READ_KEY = "oalgo-read-alerts";
function readIds(): Set<number> {
  try {
    return new Set(JSON.parse(localStorage.getItem(READ_KEY) ?? "[]"));
  } catch {
    return new Set();
  }
}
export async function markAlertsRead(id?: number): Promise<number> {
  const all = await load("alerts.json");
  const ids = readIds();
  const before = ids.size;
  for (const a of all.items) if (id == null || a.id === id) ids.add(a.id);
  try {
    localStorage.setItem(READ_KEY, JSON.stringify([...ids]));
  } catch {
    /* storage blocked: nothing to remember */
  }
  return ids.size - before;
}
function withReadState(all: J): J {
  const ids = readIds();
  const items = all.items.map((a: J) => (ids.has(a.id) ? { ...a, read: true } : a));
  return { ...all, items, unread: items.filter((a: J) => !a.read).length };
}

function filterAlerts(raw: J, q: URLSearchParams): J {
  const all = withReadState(raw);
  const kind = q.get("kind");
  let items: J[] = all.items;
  if (kind) items = items.filter((a) => a.kind === kind);
  if (q.get("unread") === "true") items = items.filter((a) => !a.read);
  return { unread: all.unread, items: items.slice(0, Number(q.get("limit") ?? 100)) };
}

export async function snapshotFetch(path: string): Promise<J> {
  const [route, query = ""] = path.split("?");
  const q = new URLSearchParams(query);
  const simple: Record<string, string> = {
    "/api/overview": "overview.json", "/api/dashboard": "dashboard.json", "/api/holdings": "holdings.json", "/api/holdings/risk": "holdings-risk.json",
    "/api/strategies": "strategies.json", "/api/factors": "factors.json", "/api/ml": "ml.json", "/api/market/summary": "market-summary.json",
    "/api/lab/mean-reversion": "mean-reversion.json", "/api/config": "config.json", "/api/providers": "providers.json", "/api/scans": "scans.json",
    "/api/portfolio": "paper.json", "/api/portfolio/risk": "paper-risk.json", "/api/meta": "meta.json",
  };
  if (route === "/api/overview" || route === "/api/dashboard") {
    const [d, alerts] = await Promise.all([load(simple[route]), load("alerts.json")]);
    return { ...d, unread_alerts: withReadState(alerts).unread };
  }
  if (route === "/api/listings") return load("listings.json");
  if (route === "/api/ops-log") return load("ops-log.json").catch(() => ({ entries: [] }));
  if (simple[route]) return load(simple[route]);
  if (route === "/api/holdings/history") return load(`holdings-history-${q.get("range") ?? "all"}.json`);
  if (route === "/api/market/indexes") return load(`indexes-${q.get("range") ?? "1y"}.json`);
  if (route === "/api/lab/regime-history") return load(`regime-${q.get("years") ?? "5"}.json`);
  if (route === "/api/stocks") return filterStocks(await load("stocks.json"), q);
  if (route === "/api/news") return filterNews(await load("news.json"), q);
  if (route === "/api/alerts") return filterAlerts(await load("alerts.json"), q);
  if (route === "/api/events/recent") return [];
  if (route === "/api/strategies/curves") {
    const all = await load("curves.json");
    const curves: J = {};
    for (const k of (q.get("keys") ?? "").split(",")) if (all.curves[k]) curves[k] = all.curves[k];
    return { label: all.label, curves };
  }
  const m = route.match(/^\/api\/stocks\/([A-Za-z-]+)(\/prices|\/fundamentals)?$/);
  if (m) {
    const bundle = await load(`stock/${m[1].toUpperCase()}.json`).catch(() => {
      throw new SnapshotMissing(`${m[1].toUpperCase()} is not one of the stocks included in this snapshot`);
    });
    if (m[2] === "/prices") return slicePrices(bundle.prices, q.get("range") ?? "1y");
    if (m[2] === "/fundamentals") return bundle.fundamentals;
    return bundle.detail;
  }
  throw new SnapshotMissing("This view needs the live backend and is not available in the snapshot");
}
