"use client";

import { useRouter } from "next/navigation";
import { useMemo } from "react";
import EChart, { C, baseOption, catAxis, valueAxis } from "./EChart";
import { Banner, Card, Empty, KV, SymbolLink } from "./ui";
import type { J } from "@/lib/api";
import { fmtNum, fmtPct } from "@/lib/format";

/** Risk analytics for a set of positions (the user's holdings or the paper portfolio). */
export default function RiskPanel({ r }: { r: J }) {
  const router = useRouter();
  const open = (p: J) => {
    const sym = typeof p.name === "string" && /^[A-Z-]+$/.test(p.name) ? p.name : null;
    if (sym) router.push(`/stocks/${sym}`);
  };

  const rcOption = useMemo(() => {
    const rc: J[] = r?.risk_contributions ?? [];
    if (!rc.length) return null;
    return baseOption({
      grid: { left: 44, right: 16, top: 28, bottom: 24 },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v) => `${(Number(v) * 100).toFixed(1)}%` },
      xAxis: catAxis(rc.map((x) => x.symbol)),
      yAxis: valueAxis({ scale: false, axisLabel: { color: C.faint, fontSize: 10.5, formatter: (v: number) => `${(v * 100).toFixed(0)}%` } }),
      series: [
        { name: "Weight", type: "bar", barGap: "10%", itemStyle: { color: "#4a5296", borderRadius: [3, 3, 0, 0] }, data: rc.map((x) => x.weight) },
        { name: "Share of portfolio risk", type: "bar", itemStyle: { color: C.accent, borderRadius: [3, 3, 0, 0] }, data: rc.map((x) => x.risk_pct) },
      ],
    });
  }, [r]);

  const sectorOption = useMemo(() => {
    const s: J[] = r?.sector_exposure ?? [];
    if (!s.length) return null;
    return baseOption({
      tooltip: { trigger: "item", valueFormatter: (v) => `${(Number(v) * 100).toFixed(1)}%` },
      legend: { show: false },
      series: [{ type: "pie", radius: ["38%", "58%"], padAngle: 2, minShowLabelAngle: 4, itemStyle: { borderRadius: 4, borderColor: C.panel, borderWidth: 2 }, label: { color: C.dim, fontSize: 11, formatter: "{b}\n{d}%", overflow: "none" }, labelLine: { lineStyle: { color: C.line } }, data: s.map((x) => ({ name: x.sector, value: x.weight })) }],
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
      series: [{ type: "heatmap", data, label: { show: c.symbols.length <= 12, fontSize: 10, color: C.ink, formatter: (p: J) => (p.value[2] == null ? "" : p.value[2].toFixed(2)) }, itemStyle: { borderColor: C.panel, borderWidth: 2, borderRadius: 3 }, emphasis: { itemStyle: { borderColor: C.ink } } }],
    });
  }, [r]);

  if (!r || r.empty) return <Card><Empty title="No positions to analyse">Risk analytics appear once there is at least one priced position.</Empty></Card>;
  return (
    <>
      {r.warnings?.length > 0 && <Banner><strong className="font-semibold">Risk warnings.</strong> {r.warnings.join(". ")}.</Banner>}
      <div className="mt-3 grid gap-4 xl:grid-cols-3">
        <Card title="Portfolio risk">
          <KV rows={[
            ["Volatility (annualised)", fmtPct(r.volatility)],
            ["Beta vs SPY", fmtNum(r.beta)],
            ["Max drawdown, past year at current weights", <span key="d" className="text-down">{fmtPct(r.max_drawdown)}</span>],
            ["1-day VaR 95% (historical / normal)", `${fmtPct(r.var_95?.hist_var, 2)} / ${fmtPct(r.var_95?.param_var, 2)}`],
            ["1-day CVaR 95%", fmtPct(r.var_95?.hist_cvar, 2)],
            ["1-day VaR 99% / CVaR 99%", `${fmtPct(r.var_99?.hist_var, 2)} / ${fmtPct(r.var_99?.hist_cvar, 2)}`],
            ["Largest position / top five", `${fmtPct(r.concentration.largest_weight)} / ${fmtPct(r.concentration.top5_weight)}`],
            ["Effective number of positions", fmtNum(r.concentration.effective_positions, 1)],
            ["Loss if every volatility stop is hit", <span key="s" className="text-down">{fmtPct(r.all_stops_hit_pct_of_equity, 2)}</span>],
          ]} />
          <p className="note mt-3">{r.basis} VaR and CVaR are losses as a share of the portfolio; real losses can exceed them.</p>
        </Card>
        <Card title="Weight against risk contribution">
          {rcOption ? <EChart option={rcOption} height={250} onClick={open} /> : <Empty title="No data" />}
          <p className="note mt-1">A position whose risk share exceeds its weight adds more risk than its size suggests. Click a bar to open the stock.</p>
        </Card>
        <Card title="Sector exposure">{sectorOption ? <EChart option={sectorOption} height={270} /> : <Empty title="No data" />}</Card>
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card title="Correlation between positions">
          {corrOption ? <EChart option={corrOption} height={280} /> : <Empty title="Needs two or more positions" />}
          {r.correlated_pairs?.length > 0 && <p className="note mt-1">Pairs above 0.70: {r.correlated_pairs.slice(0, 6).map((p: J) => `${p.a}/${p.b} ${p.correlation.toFixed(2)}`).join(", ")}.</p>}
        </Card>
        <Card title="Stop, gap and liquidity scenarios" className="xl:col-span-2" pad={false}>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead><tr className="border-b border-line/40"><th className="th">Stock</th><th className="th text-right">Weight</th><th className="th text-right" title="Portfolio loss if the 2.5 ATR stop is hit">Stop hit</th><th className="th text-right">Worst day, past year</th><th className="th text-right" title="Portfolio impact if that worst day repeats">Gap impact</th><th className="th text-right" title="Selling at 10% of average daily dollar volume">Days to exit</th></tr></thead>
              <tbody>
                {r.position_scenarios.map((s: J) => (
                  <tr key={s.symbol} className="border-b border-line/30 hover:bg-raised/40">
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
          <p className="note border-t border-line/40 px-4 py-2">A stop does not cap a loss: prices can gap through it.</p>
        </Card>
      </div>
    </>
  );
}
