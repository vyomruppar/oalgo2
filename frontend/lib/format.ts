export type Num = number | null | undefined;

const isNum = (v: Num): v is number => typeof v === "number" && Number.isFinite(v);

export function fmtNum(v: Num, digits = 2): string {
  if (!isNum(v)) return "—";
  return v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function fmtPct(v: Num, digits = 1, signed = false): string {
  if (!isNum(v)) return "—";
  const s = (v * 100).toFixed(digits);
  return `${signed && v > 0 ? "+" : ""}${s}%`;
}

export function fmtCompact(v: Num, prefix = ""): string {
  if (!isNum(v)) return "—";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e12) return `${sign}${prefix}${(a / 1e12).toFixed(2)}T`;
  if (a >= 1e9) return `${sign}${prefix}${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${sign}${prefix}${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${sign}${prefix}${(a / 1e3).toFixed(1)}K`;
  return `${sign}${prefix}${a.toFixed(0)}`;
}

export function fmtMoney(v: Num, digits = 2): string {
  if (!isNum(v)) return "—";
  const body = Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return `${v < 0 ? "-" : ""}$${body}`;
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
}

export function timeAgo(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "never";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "never";
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function signClass(v: Num): string {
  if (!isNum(v) || v === 0) return "text-dim";
  return v > 0 ? "text-up" : "text-down";
}

export function signalStyle(signal: string | null | undefined): { label: string; cls: string } {
  switch (signal) {
    case "STRONG BUY":
      return { label: "Strong buy", cls: "border-up/60 bg-up/15 text-up" };
    case "BUY":
      return { label: "Buy", cls: "border-up/40 text-up" };
    case "SELL":
      return { label: "Sell", cls: "border-down/50 text-down" };
    case "WATCHLIST":
      return { label: "Watchlist", cls: "border-warn/50 text-warn" };
    case "HOLD":
      return { label: "Hold", cls: "border-line text-dim" };
    case "NO_ACTION":
      return { label: "No action", cls: "border-line text-faint" };
    default:
      return { label: "Screened out", cls: "border-line text-faint" };
  }
}

export function regimeLabel(r: string | null | undefined): { label: string; cls: string } {
  if (r === "risk_on") return { label: "Risk-on", cls: "text-up" };
  if (r === "risk_off") return { label: "Risk-off", cls: "text-down" };
  if (r === "neutral") return { label: "Neutral", cls: "text-warn" };
  return { label: "Unknown", cls: "text-faint" };
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Score colour ramp: low scores red, mid neutral, high green. Returns an rgb() string. */
export function scoreColor(v: Num): string {
  if (!isNum(v)) return "rgb(108 117 170)";
  const t = Math.max(0, Math.min(100, v)) / 100;
  const lo = [255, 92, 122];
  const mid = [160, 168, 214];
  const hi = [61, 242, 196];
  const [a, b, k] = t < 0.5 ? [lo, mid, t / 0.5] : [mid, hi, (t - 0.5) / 0.5];
  const c = a.map((x, i) => Math.round(x + (b[i] - x) * k));
  return `rgb(${c[0]} ${c[1]} ${c[2]})`;
}
