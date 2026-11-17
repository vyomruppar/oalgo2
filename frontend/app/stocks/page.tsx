"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Card, Empty, ErrorBox, Loading, PageTitle, ScoreBar, Seg, SignalChip, SymbolLink, useApi } from "@/components/ui";
import type { J } from "@/lib/api";
import { fmtCompact, fmtMoney } from "@/lib/format";

const FILTERS = ["all", "STRONG BUY", "BUY", "WATCHLIST", "HOLD", "SELL", "failed"] as const;
const COMPONENTS = ["value", "quality", "momentum", "earnings", "low_vol", "technical"] as const;
const COMP_LABEL: Record<string, string> = { value: "Value", quality: "Quality", momentum: "Mom.", earnings: "Earn.", low_vol: "Low vol", technical: "Tech." };

export default function StockExplorer() {
  const router = useRouter();
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");
  const [q, setQ] = useState("");
  const [sector, setSector] = useState("");
  const [sort, setSort] = useState("score");
  const [jump, setJump] = useState("");

  const params = new URLSearchParams({ limit: "500", sort });
  if (filter === "failed") params.set("passed", "false");
  else if (filter !== "all") params.set("signal", filter);
  if (q) params.set("q", q);
  if (sector) params.set("sector", sector);
  const { data, error } = useApi(`/api/stocks?${params}`);
  const all = useApi("/api/stocks?limit=1");

  const Th = ({ k, label, right = false }: { k: string; label: string; right?: boolean }) => (
    <th className={`th cursor-pointer select-none hover:text-accent ${right ? "text-right" : ""}`} onClick={() => setSort(k)} aria-sort={sort === k ? "descending" : undefined}>
      {label}
      {sort === k ? " ↓" : ""}
    </th>
  );

  return (
    <>
      <PageTitle
        title="Stock Explorer"
        sub="Every scanned stock with its screen outcome, score and signal. Open a stock for charts, fundamentals, filings and the reasoning behind its signal."
        right={
          <form className="flex items-center gap-2" onSubmit={(e) => { e.preventDefault(); if (jump.trim()) router.push(`/stocks/${jump.trim().toUpperCase()}`); }}>
            <input className="input w-36" placeholder="Go to ticker" value={jump} onChange={(e) => setJump(e.target.value)} aria-label="Go to ticker" />
            <button className="btn" type="submit">Open</button>
          </form>
        }
      />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Seg options={FILTERS} value={filter} onChange={setFilter} labels={{ all: "All", "STRONG BUY": "Strong buy", BUY: "Buy", WATCHLIST: "Watchlist", HOLD: "Hold", SELL: "Sell", failed: "Failed screen" }} />
        <input className="input w-56" placeholder="Filter by ticker or company" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter by ticker or company" />
        <select className="input" value={sector} onChange={(e) => setSector(e.target.value)} aria-label="Sector">
          <option value="">All sectors</option>
          {(all.data?.sectors ?? data?.sectors ?? []).map((s: string) => <option key={s}>{s}</option>)}
        </select>
        <span className="note ml-auto">{data ? `${data.total} stocks` : ""}</span>
      </div>
      <Card pad={false}>
        {error && !data ? <ErrorBox error={error} /> : !data ? <Loading rows={8} /> : data.items.length === 0 ? (
          <Empty title="No stocks match">{all.data?.total ? "Change the filters above." : "No scan has completed yet. Start one from the Overview page."}</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-line">
                  <Th k="symbol" label="Symbol" />
                  <th className="th">Company</th>
                  <th className="th">Exch.</th>
                  <th className="th">Sector</th>
                  <Th k="price" label="Price" right />
                  <Th k="market_cap" label="Mkt cap" right />
                  <Th k="score" label="Score" />
                  <th className="th">Signal</th>
                  {COMPONENTS.map((c) => <Th key={c} k={c} label={COMP_LABEL[c]} />)}
                  <th className="th">Flags</th>
                  <th className="th">Screen</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((r: J) => (
                  <tr key={r.symbol} className="border-b border-line/50 hover:bg-raised/50">
                    <td className="td"><SymbolLink symbol={r.symbol} /></td>
                    <td className="td max-w-[200px] truncate text-dim">{(r.company ?? "").replace(/ - .*$| Common Stock.*$/i, "")}</td>
                    <td className="td text-dim">{r.exchange}</td>
                    <td className="td text-dim">{r.sector}</td>
                    <td className="td num text-right">{fmtMoney(r.price)}</td>
                    <td className="td num text-right text-dim">{fmtCompact(r.market_cap, "$")}</td>
                    <td className="td"><ScoreBar value={r.score} width={48} /></td>
                    <td className="td"><SignalChip signal={r.signal} /></td>
                    {COMPONENTS.map((c) => <td key={c} className="td"><ScoreBar value={r.components[c]} width={28} /></td>)}
                    <td className="td num text-dim">{r.n_red_flags || ""}</td>
                    <td className="td max-w-[260px] truncate text-[11.5px]" title={r.fail_reasons.join("; ")}>
                      {r.screen_pass ? <span className="text-up">Pass</span> : <span className="text-down">{r.fail_reasons[0]}{r.fail_reasons.length > 1 ? ` (+${r.fail_reasons.length - 1})` : ""}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <p className="note mt-2">Component columns are percentile ranks (0 to 100) within the screened universe. Click a column heading to sort.</p>
    </>
  );
}
