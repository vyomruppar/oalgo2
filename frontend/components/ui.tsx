"use client";

import Link from "next/link";
import useSWR from "swr";
import { fetcher, type J } from "@/lib/api";
import { useEffect, useRef, useState } from "react";
import { fmtNum, scoreColor, signalStyle } from "@/lib/format";

export function useApi(path: string | null, refreshMs = 0) {
  return useSWR<J>(path, fetcher, { revalidateOnFocus: false, refreshInterval: refreshMs, keepPreviousData: true });
}

export function Card({ title, right, children, className = "", pad = true }: { title?: React.ReactNode; right?: React.ReactNode; children: React.ReactNode; className?: string; pad?: boolean }) {
  return (
    <section className={`card ${className}`}>
      {(title || right) && (
        <header className="card-h">
          <h2 className="card-t">{title}</h2>
          {right}
        </header>
      )}
      <div className={pad ? "p-4" : ""}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, sub, cls = "" }: { label: string; value: React.ReactNode; sub?: React.ReactNode; cls?: string }) {
  return (
    <div className="card px-4 py-3">
      <div className="sub">{label}</div>
      <div className={`num mt-1 text-xl font-medium leading-tight ${cls}`}>{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-faint">{sub}</div>}
    </div>
  );
}

export function SignalChip({ signal }: { signal: string | null | undefined }) {
  const s = signalStyle(signal);
  return <span className={`chip ${s.cls}`}>{s.label}</span>;
}

export function Tag({ children, tone = "dim" }: { children: React.ReactNode; tone?: "dim" | "up" | "down" | "accent" | "warn" }) {
  const cls = { dim: "border-line text-dim", up: "border-up/40 text-up", down: "border-down/50 text-down", accent: "border-accent/50 text-accent", warn: "border-warn/50 text-warn" }[tone];
  return <span className={`chip ${cls}`}>{children}</span>;
}

export function ScoreBar({ value, width = 64 }: { value: number | null | undefined; width?: number }) {
  const ok = typeof value === "number";
  return (
    <span className="inline-flex items-center gap-2">
      <span className="relative inline-block h-1.5 rounded-sm bg-line" style={{ width }}>
        {ok && <span className="absolute inset-y-0 left-0 rounded-sm" style={{ width: `${Math.max(2, Math.min(100, value))}%`, background: scoreColor(value) }} />}
      </span>
      <span className="num w-7 text-right text-[12px]" style={{ color: scoreColor(value) }}>
        {ok ? fmtNum(value, 0) : "—"}
      </span>
    </span>
  );
}

export function Seg<T extends string>({ options, value, onChange, labels }: { options: readonly T[]; value: T; onChange: (v: T) => void; labels?: Partial<Record<T, string>> }) {
  return (
    <div className="seg" role="tablist">
      {options.map((o) => (
        <button key={o} type="button" role="tab" aria-selected={o === value} data-on={o === value} onClick={() => onChange(o)}>
          {labels?.[o] ?? o}
        </button>
      ))}
    </div>
  );
}

export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-4" aria-busy="true">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-3 animate-pulse rounded bg-line/60" style={{ width: `${90 - i * 14}%` }} />
      ))}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="px-4 py-8 text-center">
      <div className="text-sm text-dim">{title}</div>
      {children && <div className="note mx-auto mt-1 max-w-md">{children}</div>}
    </div>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : String(error);
  const offline = msg.includes("Failed to fetch") || msg.includes("NetworkError") || msg.includes("Internal Server Error") || msg.includes("ECONNREFUSED");
  return (
    <div className="m-4 rounded border border-down/40 bg-down/5 px-3 py-2 text-xs text-down">
      {offline ? "Cannot reach the research backend. Start it with `make backend` and this page will reconnect." : msg}
    </div>
  );
}

export function Banner({ tone = "warn", children }: { tone?: "warn" | "info"; children: React.ReactNode }) {
  const cls = tone === "warn" ? "border-warn/40 bg-warn/5 text-warn" : "border-line bg-raised text-dim";
  return <div className={`rounded border px-3 py-2 text-[12px] leading-relaxed ${cls}`}>{children}</div>;
}

export function PageTitle({ title, sub, right }: { title: string; sub?: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="display text-[21px] font-medium leading-tight">{title}</h1>
        {sub && <p className="note mt-0.5 max-w-3xl">{sub}</p>}
      </div>
      {right}
    </div>
  );
}

export function SymbolLink({ symbol }: { symbol: string }) {
  return (
    <Link href={`/stocks/${symbol}`} className="num font-semibold text-ink underline-offset-2 hover:text-accent hover:underline">
      {symbol}
    </Link>
  );
}

export function KV({ rows }: { rows: [React.ReactNode, React.ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1.5 text-[12.5px]">
      {rows.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className="text-dim">{k}</dt>
          <dd className="num text-right">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Animates a number to its new value once when it changes; jumps straight there under reduced motion. */
export function CountUp({ value, format, duration = 900 }: { value: number | null | undefined; format: (v: number) => string; duration?: number }) {
  const [shown, setShown] = useState<number | null>(typeof value === "number" ? value : null);
  const from = useRef<number>(0);
  useEffect(() => {
    if (typeof value !== "number" || !Number.isFinite(value)) return setShown(null);
    if (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return setShown(value);
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const tick = (t: number) => {
      const k = Math.min(1, (t - start) / duration);
      const e = 1 - Math.pow(1 - k, 3);
      setShown(a + (value - a) * e);
      if (k < 1) raf = requestAnimationFrame(tick);
      else from.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);
  return <>{shown == null ? "—" : format(shown)}</>;
}

export function Sparkline({ data, width = 96, height = 28, color }: { data: number[]; width?: number; height?: number; color?: string }) {
  if (!data || data.length < 2) return <svg width={width} height={height} aria-hidden />;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const pts = data.map((v, i) => [(i / (data.length - 1)) * width, height - 2 - ((v - min) / span) * (height - 4)]);
  const d = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");
  const c = color ?? (data[data.length - 1] >= data[0] ? "rgb(61 242 196)" : "rgb(255 92 122)");
  const id = `sg-${Math.round(pts[pts.length - 1][1] * 100)}-${data.length}-${Math.round(min)}`;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="60-day price trend">
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={c} stopOpacity="0.35" />
          <stop offset="100%" stopColor={c} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${d}L${width},${height}L0,${height}Z`} fill={`url(#${id})`} />
      <path d={d} fill="none" stroke={c} strokeWidth="1.4" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export function SentimentBadge({ s, compact = false }: { s: { score: number | null; label: string | null; n: number } | null | undefined; compact?: boolean }) {
  if (!s || s.score == null) return <span className="text-[11px] text-faint">{compact ? "no news" : "No recent headlines"}</span>;
  const tone = s.label === "positive" ? "text-up border-up/40" : s.label === "negative" ? "text-down border-down/50" : "text-dim border-line";
  return (
    <span className={`chip ${tone}`} title={`Weighted tone of ${s.n} recent headline${s.n === 1 ? "" : "s"}: ${s.score >= 0 ? "+" : ""}${s.score.toFixed(2)} on a -1 to +1 scale. Headline tone only, not a forecast.`}>
      {s.label === "positive" ? "Positive" : s.label === "negative" ? "Negative" : "Neutral"}
      {!compact && <span className="num ml-1 font-normal opacity-80">{s.score >= 0 ? "+" : ""}{s.score.toFixed(2)} · {s.n}</span>}
    </span>
  );
}

export function Tabs({ tabs, current }: { tabs: { href: string; label: string }[]; current: string }) {
  return (
    <div className="mb-4 flex gap-1 border-b border-line/40">
      {tabs.map((t) => (
        <Link key={t.href} href={t.href} aria-current={t.href === current ? "page" : undefined} className={`-mb-px border-b-2 px-3 py-2 text-[13px] font-medium transition-colors ${t.href === current ? "border-accent text-ink" : "border-transparent text-dim hover:text-ink"}`}>
          {t.label}
        </Link>
      ))}
    </div>
  );
}

/** Says where a price comes from: live (delayed about 15 minutes), the last price after the close, or stored end-of-day data. */
export function PriceSource({ live, marketOpen, time, date }: { live?: boolean; marketOpen?: boolean; time?: string | null; date?: string | null }) {
  const t = time ? new Date(time).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }) : null;
  if (live && marketOpen) return <span className="chip border-up/40 text-up" title="Prices from Yahoo Finance, delayed about 15 minutes">Live · delayed ~15 min{t ? ` · ${t}` : ""}</span>;
  if (live) return <span className="chip border-line text-dim" title="The market is closed. This is the last price.">Market closed · last price{t ? ` ${t}` : ""}</span>;
  return <span className="chip border-warn/50 text-warn" title="Stored from the last scan, not a live price">Stored close{date ? ` of ${date}` : ""}</span>;
}
