"use client";

import Link from "next/link";
import { useState } from "react";
import { Empty, Loading, Tag, useApi } from "./ui";
import { NO_WRITES, READ_ONLY, send, type J } from "@/lib/api";
import { timeAgo } from "@/lib/format";

function ToneBar({ v }: { v: number | null }) {
  if (v == null) return <span className="inline-block h-8 w-1 rounded-full bg-line" />;
  const color = v >= 0.2 ? "rgb(61 242 196)" : v <= -0.2 ? "rgb(255 92 122)" : "rgb(160 168 214)";
  return <span className="inline-block w-1 rounded-full" style={{ height: 32, background: color, opacity: 0.35 + 0.65 * Math.min(1, Math.abs(v)), boxShadow: Math.abs(v) > 0.5 ? `0 0 10px ${color}` : undefined }} title={`Headline tone ${v >= 0 ? "+" : ""}${v.toFixed(2)}`} />;
}

export function EngineNote({ engine }: { engine: J }) {
  if (!engine) return null;
  return (
    <span className="flex flex-wrap items-center gap-2 text-[11.5px] text-faint">
      <Tag tone={engine.is_ai ? "accent" : "dim"}>{engine.is_ai ? "Scored by FinBERT" : "Scored by word list"}</Tag>
      <span title={engine.note ?? engine.caveat}>{engine.description}</span>
    </span>
  );
}

/** Scored headlines for one stock, the user's holdings, or everything stored. */
export default function NewsFeed({ symbol, scope = "holdings", limit = 12, showRefresh = true, minRelevance = 0 }: { symbol?: string; scope?: "holdings" | "all"; limit?: number; showRefresh?: boolean; minRelevance?: number }) {
  const q = new URLSearchParams({ limit: String(limit), min_relevance: String(minRelevance) });
  if (symbol) q.set("symbol", symbol);
  else q.set("scope", scope);
  const { data, mutate } = useApi(`/api/news?${q}`, 300000);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = async () => {
    setBusy(true);
    setErr(null);
    try {
      await send("POST", `/api/news/refresh${symbol ? `?symbol=${symbol}` : ""}`);
      await mutate();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!data) return <Loading />;
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <EngineNote engine={data.engine} />
        {showRefresh && (
          <button className="btn" disabled={busy || NO_WRITES} title={NO_WRITES ? READ_ONLY : undefined} onClick={refresh} type="button">
            {busy ? "Fetching headlines" : "Fetch latest headlines"}
          </button>
        )}
      </div>
      {err && <div className="mb-2 text-[12px] text-down">{err}</div>}
      {data.items.length === 0 ? (
        <Empty title="No headlines stored yet">{symbol ? "Fetch the latest headlines for this stock." : scope === "holdings" ? "Add holdings, then fetch headlines or run a scan." : "Headlines are collected for the stocks you own and for buy and watchlist names during a scan."}</Empty>
      ) : (
        <ul className="divide-y divide-line/30">
          {data.items.map((n: J) => (
            <li key={n.uuid} className="flex items-stretch gap-3 py-2">
              <ToneBar v={n.sentiment} />
              <div className="min-w-0 flex-1">
                <a href={n.link ?? "#"} target="_blank" rel="noreferrer" className="block text-[13px] leading-snug text-ink hover:text-accent">
                  {n.title}
                </a>
                <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-faint">
                  <span>{n.publisher ?? "Unknown publisher"}</span>
                  <span>{timeAgo(n.published_at)}</span>
                  {!symbol && n.symbols.slice(0, 4).map((s: string) => (
                    <Link key={s} href={`/stocks/${s}`} className="font-semibold text-dim hover:text-accent">
                      {s}
                    </Link>
                  ))}
                  {n.relevance < 0.5 && <span title="This story mentions the stock among many others, so it counts for less in the sentiment average">mentions only</span>}
                </div>
              </div>
              <span className={`num shrink-0 self-center text-[12px] ${n.sentiment == null ? "text-faint" : n.sentiment >= 0.2 ? "text-up" : n.sentiment <= -0.2 ? "text-down" : "text-dim"}`}>
                {n.sentiment == null ? "—" : `${n.sentiment >= 0 ? "+" : ""}${n.sentiment.toFixed(2)}`}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="note mt-2">{data.source}. Scores read the headline only, from -1 (negative) to +1 (positive). They are not forecasts.</p>
    </div>
  );
}
