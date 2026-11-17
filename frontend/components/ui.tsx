"use client";

import Link from "next/link";
import useSWR from "swr";
import { fetcher, type J } from "@/lib/api";
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
      <div className="text-[10.5px] font-semibold uppercase tracking-[0.12em] text-faint">{label}</div>
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
  const offline = msg.includes("Failed to fetch") || msg.includes("NetworkError");
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
        <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
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
