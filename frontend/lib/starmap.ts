/**
 * Layout of the stock universe as a spiral galaxy. Pure and deterministic so it can be tested:
 * the same stock always lands in the same place.
 *
 *   arm      = sector (largest sectors first)
 *   distance = rank by market cap within the sector (largest nearest the core)
 *   size     = log market cap
 *   glow     = research score
 *   colour   = signal
 */
export type StarInput = {
  symbol: string;
  company?: string | null;
  sector: string;
  score: number | null;
  signal: string | null;
  price: number | null;
  market_cap: number | null;
  ret_1d: number | null;
  held: boolean;
  screen_pass: boolean;
};

export type Star = StarInput & { x: number; y: number; r: number; alpha: number; color: string; arm: number };
export type Arm = { sector: string; count: number; lx: number; ly: number; angle: number };

export const SIGNAL_COLOR: Record<string, string> = {
  "STRONG BUY": "#3df2c4",
  BUY: "#3df2c4",
  WATCHLIST: "#ffc46b",
  HOLD: "#aab4ff",
  SELL: "#ff5c7a",
  NO_ACTION: "#6c75aa",
  NONE: "#565e93",
};

/** Stable pseudo-random number in [0, 1) from a string and a salt. */
export function hash01(s: string, salt = 0): number {
  let h = 2166136261 ^ salt;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  h ^= h >>> 13;
  h = Math.imul(h, 0x5bd1e995);
  h ^= h >>> 15;
  return (h >>> 0) / 4294967296;
}

export function layoutStars(input: StarInput[], width: number, height: number): { stars: Star[]; arms: Arm[] } {
  const cx = width / 2;
  const cy = height / 2;
  const R = Math.min(width * 0.47, height * 0.8);
  const tilt = Math.min(0.62, (height * 0.46) / R);
  const bySector = new Map<string, StarInput[]>();
  for (const s of input) {
    const k = s.sector || "Unknown";
    if (!bySector.has(k)) bySector.set(k, []);
    bySector.get(k)!.push(s);
  }
  const sectors = [...bySector.entries()].sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]));
  const K = Math.max(sectors.length, 1);
  const stars: Star[] = [];
  const arms: Arm[] = [];
  const twist = 2.4; // radians of spiral winding from core to rim
  sectors.forEach(([sector, list], arm) => {
    const base = (arm / K) * Math.PI * 2 - Math.PI / 2;
    const ordered = [...list].sort((a, b) => (b.market_cap ?? 0) - (a.market_cap ?? 0) || a.symbol.localeCompare(b.symbol));
    const n = ordered.length;
    ordered.forEach((s, i) => {
      const t = (i + 0.5) / n;
      const rad = R * (0.2 + 0.8 * Math.pow(t, 0.8));
      const spread = (0.62 / K) * Math.PI * 2 * (1.5 - 0.95 * t);
      const theta = base + twist * (rad / R) + (hash01(s.symbol, 1) - 0.5) * spread;
      const jitter = (hash01(s.symbol, 2) - 0.5) * R * 0.05;
      const mc = s.market_cap && s.market_cap > 0 ? Math.log10(s.market_cap) : 9;
      const size = Math.max(1.1, Math.min(5.2, 1.1 + (mc - 9) * 1.25));
      const sc = typeof s.score === "number" ? s.score : null;
      stars.push({
        ...s,
        arm,
        x: cx + (rad + jitter) * Math.cos(theta),
        y: cy + (rad + jitter) * Math.sin(theta) * tilt,
        r: s.held ? Math.max(size, 3.2) : size,
        alpha: sc == null ? 0.28 : 0.35 + 0.65 * (sc / 100),
        color: SIGNAL_COLOR[s.signal ?? "NONE"] ?? SIGNAL_COLOR.NONE,
      });
    });
    const la = base + twist * 1.0;
    arms.push({ sector, count: n, angle: la, lx: cx + R * 1.03 * Math.cos(la), ly: cy + R * 1.03 * Math.sin(la) * tilt });
  });
  return { stars, arms };
}

/** Index of the star nearest to (x, y) within `maxDist` pixels, or -1. Held stars win ties. */
export function nearestStar(stars: Star[], x: number, y: number, maxDist = 14): number {
  let best = -1;
  let bestD = maxDist * maxDist;
  for (let i = 0; i < stars.length; i++) {
    const dx = stars[i].x - x;
    const dy = stars[i].y - y;
    const d = dx * dx + dy * dy - (stars[i].held ? 30 : 0) - stars[i].r * stars[i].r;
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  }
  return best;
}
