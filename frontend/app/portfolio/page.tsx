"use client";

import { useRouter } from "next/navigation";
import { useMemo } from "react";
import EChart, { C, baseOption } from "@/components/EChart";
import NewsFeed from "@/components/NewsFeed";
import { HoldingsEditor, PortfolioTracker } from "@/components/Portfolio";
import RiskPanel from "@/components/RiskPanel";
import { Card, CountUp, Empty, ErrorBox, Loading, PageTitle, PriceSource, ScoreBar, SentimentBadge, SignalChip, Sparkline, Stat, SymbolLink, Tabs, Tag, useApi } from "@/components/ui";
import type { J } from "@/lib/api";
import { useLiveHoldings } from "@/lib/quotes";
import { fmtMoney, fmtNum, fmtPct, signClass } from "@/lib/format";

export default function MyPortfolio() {
  const router = useRouter();
  const pf = useApi("/api/holdings", 60000);
  const risk = useApi("/api/holdings/risk", 120000);
  const live = useLiveHoldings(pf.data);
  const d = live.h;
  const refresh = () => {
    pf.mutate();
    risk.mutate();
  };

  const allocOption = useMemo(() => {
    const pos: J[] = (d?.positions ?? []).filter((p: J) => p.value != null);
    if (!pos.length) return null;
    return baseOption({
      tooltip: { trigger: "item", valueFormatter: (v) => fmtMoney(Number(v), 0) },
      legend: { show: false },
      series: [{ type: "pie", radius: ["40%", "62%"], padAngle: 2, minShowLabelAngle: 4, itemStyle: { borderRadius: 5, borderColor: C.panel, borderWidth: 2 }, label: { color: C.dim, fontSize: 11, formatter: "{b} {d}%", overflow: "none" }, labelLine: { lineStyle: { color: C.line } }, emphasis: { scaleSize: 8 }, data: pos.map((p) => ({ name: p.symbol, value: +p.value.toFixed(2) })) }],
    });
  }, [d]);

  if (pf.error && !d) return <ErrorBox error={pf.error} />;
  if (!d) return <Loading rows={6} />;
  const has = d.n_positions > 0;

  return (
    <>
      <Tabs tabs={[{ href: "/portfolio", label: "My holdings" }, { href: "/portfolio/paper", label: "Paper trading" }]} current="/portfolio" />
      <PageTitle title="My portfolio" sub="The stocks you actually own, valued at the last completed session's close. This is a tracker: it records and analyses, and never places an order." right={<Tag tone="accent">Tracking only</Tag>} />

      {has && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Value" value={<CountUp value={d.value} format={(v) => fmtMoney(v, 0)} />} sub={<PriceSource live={d.live} marketOpen={d.market_open} time={d.live_time} date={d.as_of} />} />
          <Stat label={d.live && d.market_open ? "Today" : "Last session"} value={<CountUp value={d.day_change} format={(v) => fmtMoney(v, 0)} />} cls={signClass(d.day_change)} sub={fmtPct(d.day_change_pct, 2, true)} />
          <Stat label="Total gain" value={<CountUp value={d.gain} format={(v) => fmtMoney(v, 0)} />} cls={signClass(d.gain)} sub={`${fmtPct(d.gain_pct, 1, true)} on ${fmtMoney(d.invested, 0)} invested`} />
          <Stat label="Positions" value={d.n_positions} sub={`${d.lots.length} lot${d.lots.length === 1 ? "" : "s"}`} />
        </div>
      )}

      <div className={`${has ? "mt-4" : ""} grid gap-4 xl:grid-cols-3`}>
        <Card title="Value over time" className="xl:col-span-2">
          <PortfolioTracker height={300} />
        </Card>
        <Card title="Allocation">
          {allocOption ? <EChart option={allocOption} height={330} onClick={(p) => typeof p.name === "string" && router.push(`/stocks/${p.name}`)} /> : <Empty title="No holdings yet">Add your first holding below.</Empty>}
        </Card>
      </div>

      {has && (
        <Card title="Positions" className="mt-4" pad={false}>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-line/40">
                  {["Stock", "Shares", "Avg cost", "Last close", "Last session", "60 days", "Value", "Weight", "Gain", "Signal", "Score", "News tone"].map((h, i) => (
                    <th key={h} className={`th ${[1, 2, 3, 4, 6, 7, 8].includes(i) ? "text-right" : ""}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {d.positions.map((p: J) => (
                  <tr key={p.symbol} className="cursor-pointer border-b border-line/30 hover:bg-raised/40" onClick={() => router.push(`/stocks/${p.symbol}`)}>
                    <td className="td">
                      <SymbolLink symbol={p.symbol} />
                      <div className="max-w-[180px] truncate text-[11px] text-faint">{(p.company ?? "").replace(/ - .*$| Common Stock.*$| Class .*$/i, "")}</div>
                    </td>
                    <td className="td num text-right">{fmtNum(p.shares, p.shares % 1 ? 3 : 0)}</td>
                    <td className="td num text-right text-dim">{fmtMoney(p.avg_cost)}</td>
                    <td className="td num text-right">{fmtMoney(p.price)}</td>
                    <td className={`td num text-right ${signClass(p.day_change_pct)}`}>{fmtPct(p.day_change_pct, 2, true)}</td>
                    <td className="td"><Sparkline data={p.spark} width={84} height={24} /></td>
                    <td className="td num text-right">{fmtMoney(p.value, 0)}</td>
                    <td className="td num text-right text-dim">{fmtPct(p.weight)}</td>
                    <td className={`td num text-right ${signClass(p.gain)}`}>{fmtMoney(p.gain, 0)} <span className="opacity-70">({fmtPct(p.gain_pct, 1, true)})</span></td>
                    <td className="td"><SignalChip signal={p.signal} /></td>
                    <td className="td">{p.score != null ? <ScoreBar value={p.score} width={44} /> : <span className="text-[11px] text-faint">{p.researched ? "not scored" : "not scanned"}</span>}</td>
                    <td className="td"><SentimentBadge s={p.sentiment} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {d.missing_prices.length > 0 && <p className="note border-t border-line/40 px-4 py-2">No stored prices yet for {d.missing_prices.join(", ")}; totals exclude them until the next scan.</p>}
        </Card>
      )}

      <div className="mt-4">
        <HoldingsEditor lots={d.lots} onChange={refresh} />
      </div>

      {has && (
        <>
          <h2 className="display mb-1 mt-6 text-[17px] font-medium">Risk</h2>
          {risk.data ? <RiskPanel r={risk.data} /> : <Loading />}
          <Card title="News on your holdings" className="mt-4">
            <NewsFeed scope="holdings" limit={12} />
          </Card>
        </>
      )}
    </>
  );
}
