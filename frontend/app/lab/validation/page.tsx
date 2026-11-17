"use client";

import { useMemo } from "react";
import EChart, { C, baseOption, catAxis, timeAxis, valueAxis, zoom } from "@/components/EChart";
import { Disclosures, StatusTag } from "@/components/Lab";
import { Card, Empty, ErrorBox, Loading, PageTitle, Tag, useApi } from "@/components/ui";
import type { J } from "@/lib/api";
import { fmtNum, fmtPct, signClass } from "@/lib/format";

export default function Validation() {
  const { data, error } = useApi("/api/strategies");

  const forest = useMemo(() => {
    if (!data?.available) return null;
    const rows: J[] = data.strategies.filter((s: J) => s.key !== "universe_ew").map((s: J) => ({ name: s.name, ...data.results[s.key] })).reverse();
    return baseOption({
      grid: { left: 210, right: 30, top: 24, bottom: 34 },
      legend: { show: false },
      tooltip: { trigger: "item", formatter: (p: J) => { const r = rows[p.dataIndex]; return `<b>${r.name}</b><br/>Sharpe ${fmtNum(r.metrics.sharpe)}<br/>95% interval ${fmtNum(r.bootstrap_sharpe?.lo)} to ${fmtNum(r.bootstrap_sharpe?.hi)}`; } },
      xAxis: valueAxis({ name: "Annualised Sharpe ratio with 95% bootstrap interval", nameLocation: "middle", nameGap: 22, nameTextStyle: { color: C.faint, fontSize: 11 } }),
      yAxis: catAxis(rows.map((r) => r.name), { axisLine: { show: false } }),
      series: [
        {
          type: "custom",
          renderItem: (_: J, api: J) => {
            const y = api.coord([0, api.value(0)])[1];
            const lo = api.coord([api.value(1), api.value(0)])[0];
            const hi = api.coord([api.value(2), api.value(0)])[0];
            return { type: "group", children: [
              { type: "line", shape: { x1: lo, y1: y, x2: hi, y2: y }, style: { stroke: C.accent, lineWidth: 2, opacity: 0.8 } },
              { type: "line", shape: { x1: lo, y1: y - 5, x2: lo, y2: y + 5 }, style: { stroke: C.accent, lineWidth: 2 } },
              { type: "line", shape: { x1: hi, y1: y - 5, x2: hi, y2: y + 5 }, style: { stroke: C.accent, lineWidth: 2 } },
            ] };
          },
          encode: { x: [1, 2], y: 0 },
          data: rows.map((r, i) => [i, r.bootstrap_sharpe?.lo ?? 0, r.bootstrap_sharpe?.hi ?? 0]),
          z: 1,
        },
        { type: "scatter", symbolSize: 11, itemStyle: { color: C.ink, borderColor: C.accent, borderWidth: 2 }, data: rows.map((r, i) => [r.metrics.sharpe, i]), z: 2,
          markLine: { silent: true, symbol: "none", lineStyle: { color: C.down, type: "dashed" }, label: { formatter: "no skill", color: C.faint, fontSize: 10 }, data: [{ xAxis: 0 }] } },
      ],
    });
  }, [data]);

  const costOption = useMemo(() => {
    if (!data?.available) return null;
    const strategies: J[] = data.strategies.filter((s: J) => s.key !== "universe_ew");
    const uni = data.results.universe_ew.metrics.cagr;
    return baseOption({
      grid: { left: 48, right: 16, top: 60, bottom: 30 },
      legend: { type: "scroll", textStyle: { color: C.dim, fontSize: 11 }, top: 0 },
      tooltip: { trigger: "axis", valueFormatter: (v) => `${(Number(v) * 100).toFixed(1)}%` },
      xAxis: catAxis(["0", "10", "25", "50"], { name: "Trading cost each way (bps)", nameLocation: "middle", nameGap: 22, nameTextStyle: { color: C.faint, fontSize: 11 } }),
      yAxis: valueAxis({ axisLabel: { color: C.faint, fontSize: 10.5, formatter: (v: number) => `${(v * 100).toFixed(0)}%` } }),
      series: [
        ...strategies.map((s) => ({ name: s.name, type: "line" as const, symbolSize: 5, emphasis: { focus: "series" as const }, lineStyle: { width: 1.5 }, data: ["0", "10", "25", "50"].map((b) => data.results[s.key].cost_sensitivity?.[b]?.cagr ?? null) })),
        { name: "Equal-weight universe (10 bps)", type: "line" as const, symbol: "none", lineStyle: { width: 1.5, type: "dashed" as const, color: C.ink }, itemStyle: { color: C.ink }, data: [uni, uni, uni, uni] },
      ],
    });
  }, [data]);

  const universeOption = useMemo(() => {
    const u: [string, number][] = data?.universe_count ?? [];
    if (!u.length) return null;
    return baseOption({ grid: { left: 44, right: 16, top: 12, bottom: 44 }, legend: { show: false }, xAxis: timeAxis(), yAxis: valueAxis({ scale: false }), dataZoom: zoom(), series: [{ name: "Eligible stocks", type: "line", step: "end", showSymbol: false, areaStyle: { opacity: 0.18 }, lineStyle: { width: 1.6 }, data: u }] });
  }, [data]);

  if (error && !data) return <ErrorBox error={error} />;
  if (!data) return <Loading rows={6} />;
  if (!data.available) return (<><PageTitle title="Validation" /><Card><Empty title="No backtests to validate yet">Run a scan first.</Empty></Card></>);
  const rows: J[] = data.strategies.filter((s: J) => s.key !== "universe_ew");
  const counts = rows.reduce((a: Record<string, number>, s) => { const k = data.results[s.key].validation_status?.status ?? "n/a"; a[k] = (a[k] ?? 0) + 1; return a; }, {});

  return (
    <>
      <PageTitle title="Validation" sub="Whether any of this survives scrutiny. Each strategy is checked for excess return over the equal-weight universe, out-of-sample persistence, statistical significance after correcting for the number of strategies tried, and sensitivity to trading costs." right={<Tag tone="warn">Backtested</Tag>} />
      <Disclosures data={data} />
      <p className="mt-3 text-[13px] text-dim">
        Of {rows.length} strategies: <span className="text-up">{counts.supported ?? 0} supported</span>, <span className="text-warn">{counts.mixed ?? 0} mixed</span>, <span className="text-down">{counts["not supported"] ?? 0} not supported</span>.
      </p>
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="Is the Sharpe ratio distinguishable from zero?">{forest ? <EChart option={forest} height={Math.max(300, rows.length * 30 + 60)} /> : <Empty title="No data" />}<p className="note mt-1">Stationary block bootstrap, 400 resamples. An interval that reaches the dashed line means the result could be noise.</p></Card>
        <Card title="What trading costs do to returns">{costOption ? <EChart option={costOption} height={Math.max(300, rows.length * 30 + 60)} /> : <Empty title="No data" />}<p className="note mt-1">Hover a line to isolate it. High-turnover strategies fall fastest.</p></Card>
      </div>
      <Card title="Verdict by strategy" className="mt-4" pad={false}>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-line/40">
                <th className="th">Strategy</th><th className="th">Status</th>
                <th className="th text-right">vs universe</th><th className="th text-right">Out-of-sample</th>
                <th className="th text-right" title="Benjamini-Hochberg adjusted p-value for excess return over the universe">Adjusted p</th>
                <th className="th text-right" title="Probability the Sharpe ratio is real after allowing for the number of strategies tried">Deflated Sharpe</th>
                <th className="th text-right">CAGR at 50 bps</th><th className="th">Why</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => {
                const r = data.results[s.key];
                return (
                  <tr key={s.key} className="border-b border-line/30 align-top">
                    <td className="td font-medium">{s.name}</td>
                    <td className="td"><StatusTag s={r.validation_status?.status} /></td>
                    <td className={`td num text-right ${signClass(r.vs_universe?.excess_cagr)}`}>{fmtPct(r.vs_universe?.excess_cagr, 1, true)}</td>
                    <td className={`td num text-right ${signClass(r.vs_universe?.segments?.out_of_sample)}`}>{fmtPct(r.vs_universe?.segments?.out_of_sample, 1, true)}</td>
                    <td className="td num text-right">{fmtNum(r.excess_vs_universe_test?.p_adj, 3)}</td>
                    <td className="td num text-right">{fmtNum(r.deflated_sharpe?.dsr)}</td>
                    <td className="td num text-right text-dim">{fmtPct(r.validation_status?.cagr_at_50bps)}</td>
                    <td className="td whitespace-normal text-[11.5px] text-faint" style={{ minWidth: 300 }}>{r.validation_status?.reasons?.length ? r.validation_status.reasons.join("; ") : "Passed every check."}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
      <Card title="Size of the eligible universe over time" className="mt-4">
        {universeOption ? <EChart option={universeOption} height={200} /> : <Empty title="No data" />}
        <p className="note mt-1">Stocks passing the screen at each monthly re-rank. It grows because the scan starts from today&apos;s listings: companies that were delisted never appear, which is the survivorship bias named above.</p>
      </Card>
    </>
  );
}
