"use client";

import { useMemo, useState } from "react";
import EChart, { C, baseOption, catAxis, timeAxis, valueAxis, zoom } from "@/components/EChart";
import { Banner, Card, Empty, ErrorBox, KV, Loading, PageTitle, Stat, SymbolLink, Tabs, Tag, useApi } from "@/components/ui";
import { READ_ONLY, send, SNAPSHOT, type J } from "@/lib/api";
import { fmtDateTime, fmtMoney, fmtNum, fmtPct, signClass } from "@/lib/format";

export default function Portfolio() {
  const pf = useApi("/api/portfolio", 60000);
  const risk = useApi("/api/portfolio/risk", 60000);
  const [busy, setBusy] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const d = pf.data;
  const r = risk.data;

  const reset = async () => {
    setConfirmReset(false);
    setBusy(true);
    try {
      await send("POST", "/api/portfolio/reset?initial_cash=100000");
      pf.mutate();
      risk.mutate();
    } finally {
      setBusy(false);
    }
  };

  const equityOption = useMemo(() => {
    const c: J[] = d?.equity_curve ?? [];
    if (c.length < 2) return null;
    const e0 = c[0].equity;
    const b0 = c.find((x) => x.benchmark_close != null)?.benchmark_close;
    return baseOption({
      xAxis: timeAxis(),
      yAxis: valueAxis({ axisLabel: { color: C.faint, fontSize: 10.5, formatter: (v: number) => `${v.toFixed(1)}%` } }),
      dataZoom: zoom(),
      grid: { left: 48, right: 16, top: 28, bottom: 44 },
      tooltip: { trigger: "axis", valueFormatter: (v) => `${Number(v).toFixed(2)}%` },
      series: [
        { name: "Paper portfolio", type: "line", showSymbol: c.length < 30, lineStyle: { width: 2 }, color: C.accent, data: c.map((x) => [x.date, (x.equity / e0 - 1) * 100]) },
        { name: "S&P 500 (price index)", type: "line", showSymbol: false, lineStyle: { width: 1.2 }, color: "#5ec8ff", data: c.map((x) => [x.date, b0 && x.benchmark_close != null ? (x.benchmark_close / b0 - 1) * 100 : null]) },
      ],
    });
  }, [d]);

  const allocOption = useMemo(() => {
    const pos: J[] = d?.positions ?? [];
    if (!pos.length || !d.equity) return null;
    const data = pos.map((p) => ({ name: p.symbol, value: +(p.market_value ?? 0).toFixed(2) }));
    data.push({ name: "Cash", value: +d.cash.toFixed(2), itemStyle: { color: "#2a3070" } } as (typeof data)[number]);
    return baseOption({
      tooltip: { trigger: "item", valueFormatter: (v) => fmtMoney(Number(v), 0) },
      legend: { show: false },
      series: [{ type: "pie", radius: ["48%", "74%"], itemStyle: { borderColor: C.panel, borderWidth: 2 }, label: { color: C.dim, fontSize: 10.5, formatter: "{b} {d}%" }, labelLine: { lineStyle: { color: C.line } }, data }],
    });
  }, [d]);

  const sectorOption = useMemo(() => {
    const s: J[] = r?.sector_exposure ?? [];
    if (!s.length) return null;
    const rows = [...s].reverse();
    return baseOption({
      grid: { left: 150, right: 44, top: 4, bottom: 18 },
      legend: { show: false },
      tooltip: { trigger: "item" },
      xAxis: valueAxis({ scale: false, axisLabel: { color: C.faint, fontSize: 10.5, formatter: (v: number) => `${(v * 100).toFixed(0)}%` } }),
      yAxis: catAxis(rows.map((x) => x.sector), { axisLine: { show: false } }),
      series: [{ type: "bar", barWidth: 10, itemStyle: { color: C.accent, borderRadius: 2 }, data: rows.map((x) => x.weight), label: { show: true, position: "right", color: C.dim, fontSize: 10.5, formatter: (p: J) => `${(p.value * 100).toFixed(1)}%` } }],
    });
  }, [r]);

  const rcOption = useMemo(() => {
    const rc: J[] = r?.risk_contributions ?? [];
    if (!rc.length) return null;
    return baseOption({
      grid: { left: 44, right: 16, top: 28, bottom: 24 },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v) => `${(Number(v) * 100).toFixed(1)}%` },
      xAxis: catAxis(rc.map((x) => x.symbol)),
      yAxis: valueAxis({ scale: false, axisLabel: { color: C.faint, fontSize: 10.5, formatter: (v: number) => `${(v * 100).toFixed(0)}%` } }),
      series: [
        { name: "Weight", type: "bar", barGap: "10%", itemStyle: { color: "#4a5296" }, data: rc.map((x) => x.weight) },
        { name: "Share of portfolio risk", type: "bar", itemStyle: { color: C.accent }, data: rc.map((x) => x.risk_pct) },
      ],
    });
  }, [r]);

  const corrOption = useMemo(() => {
    const c = r?.correlation;
    if (!c || c.symbols.length < 2) return null;
    const data: [number, number, number | null][] = [];
    c.matrix.forEach((row: (number | null)[], i: number) => row.forEach((v, j) => data.push([j, i, v])));
    return baseOption({
      grid: { left: 56, right: 12, top: 8, bottom: 40 },
      tooltip: { trigger: "item", formatter: (p: J) => `${c.symbols[p.value[1]]} / ${c.symbols[p.value[0]]}: ${p.value[2] == null ? "n/a" : p.value[2].toFixed(2)}` },
      xAxis: catAxis(c.symbols, { axisLine: { show: false } }),
      yAxis: catAxis(c.symbols, { inverse: true, axisLine: { show: false } }),
      visualMap: { show: false, min: -1, max: 1, inRange: { color: ["#d0456b", "#11163c", "#2fd0aa"] } },
      series: [{ type: "heatmap", data, label: { show: c.symbols.length <= 12, fontSize: 9.5, color: C.ink, formatter: (p: J) => (p.value[2] == null ? "" : p.value[2].toFixed(2)) }, itemStyle: { borderColor: C.panel, borderWidth: 1.5 } }],
    });
  }, [r]);

  if (pf.error && !d) return <ErrorBox error={pf.error} />;
  if (!d) return <Loading rows={6} />;
  const pending = d.trades.filter((t: J) => t.status === "pending").length;

  return (
    <>
      <Tabs tabs={[{ href: "/portfolio", label: "My holdings" }, { href: "/portfolio/paper", label: "Paper trading" }]} current="/portfolio/paper" />
      <PageTitle
        title="Paper trading"
        sub={`Hypothetical positions only. Fill model: ${d.fill_model}. Place paper orders from any stock's research page.`}
        right={<div className="flex items-center gap-2"><Tag tone="warn">Paper-traded · no real orders</Tag>{confirmReset ? (
            <>
              <span className="text-[12px] text-dim">Delete all paper positions, trades and history?</span>
              <button className="btn border-down/60 text-down" disabled={busy} onClick={reset}>Yes, reset</button>
              <button className="btn" onClick={() => setConfirmReset(false)}>Keep it</button>
            </>
          ) : (
            <button className="btn" disabled={busy || SNAPSHOT} title={SNAPSHOT ? READ_ONLY : undefined} onClick={() => setConfirmReset(true)}>Reset paper portfolio</button>
          )}</div>}
      />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Paper equity" value={fmtMoney(d.equity, 0)} sub={`started at ${fmtMoney(d.initial_cash, 0)}`} />
        <Stat label="Total return" value={fmtPct(d.total_return, 2, true)} cls={signClass(d.total_return)} sub="since inception, after costs" />
        <Stat label="Cash" value={fmtMoney(d.cash, 0)} sub={d.equity ? `${fmtPct(d.cash / d.equity, 0)} of equity` : undefined} />
        <Stat label="Unrealised P&L" value={fmtMoney(d.unrealized_pnl, 0)} cls={signClass(d.unrealized_pnl)} />
        <Stat label="Realised P&L" value={fmtMoney(d.realized_pnl, 0)} cls={signClass(d.realized_pnl)} />
        <Stat label="Dividends received" value={fmtMoney(d.dividends_received, 0)} sub={pending ? `${pending} order${pending > 1 ? "s" : ""} pending next open` : "no pending orders"} />
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-3">
        <Card title="Equity curve vs benchmark" className="xl:col-span-2" right={<Tag tone="warn">Paper-traded</Tag>}>
          {equityOption ? <EChart option={equityOption} height={280} /> : <Empty title="No equity history yet">A daily mark is recorded once the portfolio has existed across two sessions.</Empty>}
          <p className="note mt-2">The benchmark is the S&amp;P 500 price index, which excludes dividends.</p>
        </Card>
        <Card title="Allocation">{allocOption ? <EChart option={allocOption} height={280} /> : <Empty title="All cash">No open paper positions.</Empty>}</Card>
      </div>

      <Card title="Positions" className="mt-3" pad={false}>
        {d.positions.length === 0 ? <Empty title="No open positions">Open a stock in the Explorer and use the paper trade ticket.</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead><tr className="border-b border-line">{["Symbol", "Shares", "Avg cost", "Last close", "As of", "Market value", "Weight", "Unrealised", "%", "Opened"].map((h, i) => <th key={h} className={`th ${i > 0 && i !== 4 && i !== 9 ? "text-right" : ""}`}>{h}</th>)}</tr></thead>
              <tbody>
                {d.positions.map((p: J) => (
                  <tr key={p.symbol} className="border-b border-line/50 hover:bg-raised/50">
                    <td className="td"><SymbolLink symbol={p.symbol} /></td>
                    <td className="td num text-right">{fmtNum(p.quantity, 0)}</td>
                    <td className="td num text-right text-dim">{fmtMoney(p.avg_cost)}</td>
                    <td className="td num text-right">{fmtMoney(p.price)}</td>
                    <td className="td num text-dim">{p.price_date}</td>
                    <td className="td num text-right">{fmtMoney(p.market_value, 0)}</td>
                    <td className="td num text-right text-dim">{fmtPct(p.weight)}</td>
                    <td className={`td num text-right ${signClass(p.unrealized_pnl)}`}>{fmtMoney(p.unrealized_pnl, 0)}</td>
                    <td className={`td num text-right ${signClass(p.unrealized_pct)}`}>{fmtPct(p.unrealized_pct, 1, true)}</td>
                    <td className="td num text-dim">{p.opened_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <PageTitle title="Risk" sub={r && !r.empty ? r.basis : undefined} />
      {risk.error && !r ? <ErrorBox error={risk.error} /> : !r ? <Loading /> : r.empty ? (
        <Card><Empty title="No positions to analyse">Risk analytics appear once the paper portfolio holds at least one position.</Empty></Card>
      ) : (
        <>
          {r.warnings?.length > 0 && <Banner><strong className="font-semibold">Risk warnings.</strong> {r.warnings.join(". ")}.</Banner>}
          <div className="mt-3 grid gap-3 xl:grid-cols-3">
            <Card title="Portfolio risk">
              <KV rows={[
                ["Volatility (annualised)", fmtPct(r.volatility)],
                ["Beta vs SPY (including cash)", fmtNum(r.beta)],
                ["Max drawdown (1y at current weights)", <span key="d" className="text-down">{fmtPct(r.max_drawdown)}</span>],
                ["Calmar ratio", fmtNum(r.calmar)],
                ["1-day VaR 95% (historical / normal)", `${fmtPct(r.var_95?.hist_var, 2)} / ${fmtPct(r.var_95?.param_var, 2)}`],
                ["1-day CVaR 95% (historical)", fmtPct(r.var_95?.hist_cvar, 2)],
                ["1-day VaR 99% / CVaR 99%", `${fmtPct(r.var_99?.hist_var, 2)} / ${fmtPct(r.var_99?.hist_cvar, 2)}`],
                ["Largest position / top five", `${fmtPct(r.concentration.largest_weight)} / ${fmtPct(r.concentration.top5_weight)}`],
                ["Effective number of positions (invested part)", fmtNum(r.concentration.effective_positions, 1)],
                ["Loss if every stop is hit", <span key="s" className="text-down">{fmtPct(r.all_stops_hit_pct_of_equity, 2)}</span>],
              ]} />
              <p className="note mt-3">VaR and CVaR are losses as a share of equity. Historical simulation assumes the past year is representative; real losses can exceed these figures.</p>
            </Card>
            <Card title="Weight vs risk contribution">{rcOption ? <EChart option={rcOption} height={260} /> : <Empty title="No data" />}<p className="note mt-1">Ledoit-Wolf shrinkage covariance. A position whose risk share exceeds its weight is adding more than its size suggests.</p></Card>
            <Card title="Sector exposure">{sectorOption ? <EChart option={sectorOption} height={Math.max(140, r.sector_exposure.length * 30)} /> : <Empty title="No data" />}</Card>
          </div>
          <div className="mt-3 grid gap-3 xl:grid-cols-3">
            <Card title="Correlation between positions">
              {corrOption ? <EChart option={corrOption} height={280} /> : <Empty title="Needs two or more positions" />}
              {r.correlated_pairs?.length > 0 && <p className="note mt-1">Pairs above 0.70: {r.correlated_pairs.slice(0, 6).map((p: J) => `${p.a}/${p.b} ${p.correlation.toFixed(2)}`).join(", ")}.</p>}
            </Card>
            <Card title="Stop-loss, gap and liquidity scenarios" className="xl:col-span-2" pad={false}>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead><tr className="border-b border-line"><th className="th">Symbol</th><th className="th text-right">Weight</th><th className="th text-right" title="Loss as a share of equity if the 2.5 ATR stop is hit">Stop hit</th><th className="th text-right">Worst day, 1y</th><th className="th text-right" title="Equity impact if that worst day repeats">Gap impact</th><th className="th text-right" title="At 10% of average daily dollar volume">Days to exit</th></tr></thead>
                  <tbody>
                    {r.position_scenarios.map((s: J) => (
                      <tr key={s.symbol} className="border-b border-line/50">
                        <td className="td"><SymbolLink symbol={s.symbol} /></td>
                        <td className="td num text-right text-dim">{fmtPct(s.weight)}</td>
                        <td className="td num text-right text-down">{fmtPct(s.stop_loss_pct_of_equity, 2)}</td>
                        <td className="td num text-right text-down">{fmtPct(s.worst_day_1y)}</td>
                        <td className="td num text-right text-down">{fmtPct(s.gap_loss_pct_of_equity, 2)}</td>
                        <td className="td num text-right text-dim">{s.days_to_liquidate != null && s.days_to_liquidate < 0.01 ? "< 0.01" : fmtNum(s.days_to_liquidate, 2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="note border-t border-line px-4 py-2">A stop does not cap the loss: prices can gap through it. The gap column shows what each position&apos;s worst day of the last year would cost.</p>
            </Card>
          </div>
        </>
      )}

      <Card title="Paper trade history" className="mt-3" pad={false}>
        {d.trades.length === 0 ? <Empty title="No paper trades yet" /> : (
          <div className="max-h-96 overflow-auto">
            <table className="w-full">
              <thead className="sticky top-0 bg-panel"><tr className="border-b border-line">{["Entered", "Symbol", "Side", "Shares", "Status", "Fill date", "Fill price", "Costs", "Realised P&L", "Note"].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
              <tbody>
                {d.trades.map((t: J) => (
                  <tr key={t.id} className="border-b border-line/50 text-[12px]">
                    <td className="td num text-dim">{fmtDateTime(t.created_at)}</td>
                    <td className="td"><SymbolLink symbol={t.symbol} /></td>
                    <td className={`td font-semibold ${t.side === "BUY" ? "text-up" : "text-down"}`}>{t.side}</td>
                    <td className="td num">{fmtNum(t.quantity, 0)}</td>
                    <td className="td">{t.status === "filled" ? <Tag tone="up">Filled</Tag> : t.status === "pending" ? <Tag tone="accent">Pending</Tag> : <Tag tone="down">{t.status}</Tag>}</td>
                    <td className="td num text-dim">{t.fill_date ?? "next open"}</td>
                    <td className="td num">{fmtMoney(t.fill_price)}</td>
                    <td className="td num text-dim">{t.status === "filled" ? fmtMoney(t.cost) : "—"}</td>
                    <td className={`td num ${signClass(t.realized_pnl)}`}>{t.realized_pnl == null ? "—" : fmtMoney(t.realized_pnl)}</td>
                    <td className="td max-w-[260px] truncate text-faint" title={t.note ?? ""}>{t.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
