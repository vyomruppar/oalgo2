"use client";

import { useMemo, useState } from "react";
import EChart, { C, baseOption, catAxis, timeAxis, valueAxis, zoom } from "@/components/EChart";
import { Banner, Card, Empty, ErrorBox, KV, Loading, PageTitle, Seg, SymbolLink, Tag, useApi } from "@/components/ui";
import type { J } from "@/lib/api";
import { fmtNum, fmtPct, signClass, titleCase } from "@/lib/format";

const SEGMENTS = ["train", "validation", "out_of_sample"] as const;

function StatusTag({ s }: { s?: string }) {
  if (s === "supported") return <Tag tone="up">Supported</Tag>;
  if (s === "mixed") return <Tag tone="accent">Mixed</Tag>;
  if (s === "not supported") return <Tag tone="down">Not supported</Tag>;
  return <Tag>Benchmark</Tag>;
}

export default function Strategies() {
  const { data, error } = useApi("/api/strategies");
  const factors = useApi("/api/factors");
  const [selected, setSelected] = useState("multifactor");
  const [compare, setCompare] = useState<string[]>(["multifactor", "momentum", "universe_ew", "SPY"]);
  const [scale, setScale] = useState<"log" | "linear">("log");
  const [view, setView] = useState<"equity" | "drawdown" | "rolling_sharpe">("equity");
  const [icFactor, setIcFactor] = useState("quality");
  const curves = useApi(data?.available ? `/api/strategies/curves?keys=${[...new Set([...compare, selected])].join(",")}` : null);

  const names: Record<string, string> = useMemo(() => {
    const m: Record<string, string> = { SPY: "SPY total return", QQQ: "QQQ total return" };
    (data?.strategies ?? []).forEach((s: J) => (m[s.key] = s.name));
    return m;
  }, [data]);

  const curveOption = useMemo(() => {
    const cs = curves.data?.curves;
    if (!cs) return null;
    const keys = compare.filter((k) => cs[k]?.[view]);
    const pct = view === "drawdown";
    return baseOption({
      xAxis: timeAxis(),
      yAxis: view === "equity" && scale === "log" ? { type: "log", axisLine: { lineStyle: { color: C.line } }, axisLabel: { color: C.faint, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.line, opacity: 0.6 } } } : valueAxis({ axisLabel: { color: C.faint, fontSize: 10.5, formatter: (v: number) => (pct ? `${(v * 100).toFixed(0)}%` : v.toFixed(1)) } }),
      dataZoom: zoom(),
      grid: { left: 48, right: 16, top: 30, bottom: 44 },
      tooltip: { trigger: "axis", valueFormatter: (v) => (pct ? `${(Number(v) * 100).toFixed(1)}%` : Number(v).toFixed(2)) },
      series: keys.map((k) => ({ name: names[k] ?? k, type: "line", showSymbol: false, lineStyle: { width: k === selected ? 2 : 1.2 }, areaStyle: pct && keys.length === 1 ? { opacity: 0.15 } : undefined, data: cs[k][view] })),
    });
  }, [curves.data, compare, view, scale, names, selected]);

  const corrOption = useMemo(() => {
    const c = data?.correlation;
    if (!c) return null;
    const labels = c.keys.map((k: string) => names[k] ?? k);
    const d: [number, number, number][] = [];
    c.matrix.forEach((row: number[], i: number) => row.forEach((v, j) => d.push([j, i, v])));
    return baseOption({
      grid: { left: 168, right: 12, top: 8, bottom: 130 },
      tooltip: { trigger: "item", formatter: (p: J) => `${labels[p.value[1]]} / ${labels[p.value[0]]}: ${p.value[2].toFixed(2)}` },
      xAxis: catAxis(labels, { axisLabel: { color: C.faint, fontSize: 10, rotate: 60, interval: 0 }, axisLine: { show: false } }),
      yAxis: catAxis(labels, { inverse: true, axisLine: { show: false }, axisLabel: { color: C.faint, fontSize: 10, interval: 0 } }),
      visualMap: { show: false, min: 0.3, max: 1, inRange: { color: ["#1b2027", "#3b3524", "#b08a4c"] } },
      series: [{ type: "heatmap", data: d, label: { show: true, fontSize: 9, color: C.ink, formatter: (p: J) => (p.value[2] * 100).toFixed(0) }, itemStyle: { borderColor: C.panel, borderWidth: 1.5 } }],
    });
  }, [data, names]);

  const fr = factors.data?.ic ? factors.data : null;
  const icOption = useMemo(() => {
    if (!fr?.ic?.[icFactor]) return null;
    const s: [string, number][] = fr.ic[icFactor].series;
    let acc = 0;
    return baseOption({
      xAxis: timeAxis(),
      yAxis: [valueAxis(), valueAxis({ splitLine: { show: false } })],
      dataZoom: zoom(),
      grid: { left: 44, right: 44, top: 30, bottom: 44 },
      series: [
        { name: "Monthly rank IC", type: "bar", data: s.map(([d, v]) => ({ value: [d, v], itemStyle: { color: v >= 0 ? C.up : C.down, opacity: 0.7 } })) },
        { name: "Cumulative IC", type: "line", yAxisIndex: 1, showSymbol: false, lineStyle: { width: 1.5 }, color: C.accent, data: s.map(([d, v]) => [d, (acc += v)]) },
      ],
    });
  }, [fr, icFactor]);

  const fcorrOption = useMemo(() => {
    if (!fr?.correlation) return null;
    const labels: string[] = fr.factors.map((f: string) => titleCase(f));
    const d: [number, number, number][] = [];
    fr.correlation.forEach((row: number[], i: number) => row.forEach((v, j) => d.push([j, i, v])));
    return baseOption({
      grid: { left: 120, right: 12, top: 8, bottom: 84 },
      tooltip: { trigger: "item", formatter: (p: J) => `${labels[p.value[1]]} / ${labels[p.value[0]]}: ${p.value[2].toFixed(2)}` },
      xAxis: catAxis(labels, { axisLabel: { color: C.faint, fontSize: 10, rotate: 45 }, axisLine: { show: false } }),
      yAxis: catAxis(labels, { inverse: true, axisLine: { show: false } }),
      visualMap: { show: false, min: -1, max: 1, inRange: { color: ["#b84c4c", "#1b2027", "#3fae80"] } },
      series: [{ type: "heatmap", data: d, label: { show: true, fontSize: 9.5, color: C.ink, formatter: (p: J) => p.value[2].toFixed(2) }, itemStyle: { borderColor: C.panel, borderWidth: 1.5 } }],
    });
  }, [fr]);

  if (error && !data) return <ErrorBox error={error} />;
  if (!data) return <Loading rows={6} />;
  if (!data.available)
    return (
      <>
        <PageTitle title="Strategies & Factors" />
        <Card><Empty title="No backtests yet">Backtests run as part of a scan once enough price and filing history is stored. Start a scan from the Overview page.</Empty></Card>
      </>
    );

  const R = data.results;
  const meta: J[] = data.strategies;
  const sel = R[selected];
  const selMeta = meta.find((m) => m.key === selected);
  const toggle = (k: string) => setCompare((c) => (c.includes(k) ? c.filter((x) => x !== k) : [...c, k]));

  return (
    <>
      <PageTitle title="Strategies & Factors" sub={`Each strategy is tested independently and against benchmarks. Top ${data.config.top_n} stocks, equal weight, monthly re-rank, ${data.config.cost_bps_one_way} bps cost each way, ${data.config.first_date} to ${data.config.last_date}.`} right={<Tag tone="warn">Backtested · hypothetical</Tag>} />
      <Banner>
        <strong className="font-semibold">Read before using these numbers.</strong>
        <ul className="mt-1 list-disc space-y-0.5 pl-4">
          {data.disclosures.slice(1).map((d: string) => <li key={d}>{d}</li>)}
        </ul>
      </Banner>

      <Card title="Strategy comparison" className="mt-3" pad={false}>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-line">
                <th className="th">Plot</th>
                <th className="th">Strategy</th>
                <th className="th">Evidence</th>
                <th className="th">Status</th>
                <th className="th text-right">CAGR</th>
                <th className="th text-right">Vol</th>
                <th className="th text-right">Sharpe</th>
                <th className="th text-right">Sortino</th>
                <th className="th text-right">Max DD</th>
                <th className="th text-right" title="Annualised return minus the equal-weight eligible universe">vs universe</th>
                <th className="th text-right" title="Same, on the final 25% of the period">OOS vs univ.</th>
                <th className="th text-right">vs SPY</th>
                <th className="th text-right">Turnover</th>
                <th className="th text-right">Win rate</th>
                <th className="th text-right" title="Gross profit divided by gross loss on closed positions">Profit factor</th>
              </tr>
            </thead>
            <tbody>
              {meta.map((m) => {
                const r = R[m.key];
                const x = r.metrics;
                return (
                  <tr key={m.key} onClick={() => setSelected(m.key)} className={`cursor-pointer border-b border-line/50 hover:bg-raised/50 ${selected === m.key ? "bg-raised" : ""}`}>
                    <td className="td" onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" aria-label={`Plot ${m.name}`} checked={compare.includes(m.key)} onChange={() => toggle(m.key)} className="accent-[#d6a85c]" />
                    </td>
                    <td className="td font-medium">{m.name}</td>
                    <td className="td text-dim">{m.evidence}</td>
                    <td className="td"><StatusTag s={r.validation_status?.status} /></td>
                    <td className="td num text-right">{fmtPct(x.cagr)}</td>
                    <td className="td num text-right text-dim">{fmtPct(x.volatility)}</td>
                    <td className="td num text-right">{fmtNum(x.sharpe)}</td>
                    <td className="td num text-right text-dim">{fmtNum(x.sortino)}</td>
                    <td className="td num text-right text-down">{fmtPct(x.max_drawdown)}</td>
                    <td className={`td num text-right ${signClass(r.vs_universe?.excess_cagr)}`}>{fmtPct(r.vs_universe?.excess_cagr, 1, true)}</td>
                    <td className={`td num text-right ${signClass(r.vs_universe?.segments?.out_of_sample)}`}>{fmtPct(r.vs_universe?.segments?.out_of_sample, 1, true)}</td>
                    <td className={`td num text-right ${signClass(x.excess_cagr)}`}>{fmtPct(x.excess_cagr, 1, true)}</td>
                    <td className="td num text-right text-dim">{fmtNum(r.turnover_annual, 1)}x</td>
                    <td className="td num text-right text-dim">{fmtPct(r.trade_stats.win_rate, 0)}</td>
                    <td className="td num text-right text-dim">{fmtNum(r.trade_stats.profit_factor)}</td>
                  </tr>
                );
              })}
              {Object.entries(data.benchmarks).map(([k, x]: [string, J]) => (
                <tr key={k} className="border-b border-line/50 text-dim">
                  <td className="td"><input type="checkbox" aria-label={`Plot ${k}`} checked={compare.includes(k)} onChange={() => toggle(k)} className="accent-[#d6a85c]" /></td>
                  <td className="td">{names[k]} (buy and hold)</td>
                  <td className="td">benchmark</td>
                  <td className="td"><StatusTag /></td>
                  <td className="td num text-right">{fmtPct(x.cagr)}</td>
                  <td className="td num text-right">{fmtPct(x.volatility)}</td>
                  <td className="td num text-right">{fmtNum(x.sharpe)}</td>
                  <td className="td num text-right">{fmtNum(x.sortino)}</td>
                  <td className="td num text-right">{fmtPct(x.max_drawdown)}</td>
                  <td className="td" colSpan={7} />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="mt-3 grid gap-3 xl:grid-cols-3">
        <Card title="Historical curves" className="xl:col-span-2" right={
          <div className="flex items-center gap-2">
            <Seg options={["equity", "drawdown", "rolling_sharpe"] as const} value={view} onChange={setView} labels={{ equity: "Growth of 1", drawdown: "Drawdown", rolling_sharpe: "Rolling 1y Sharpe" }} />
            {view === "equity" && <Seg options={["log", "linear"] as const} value={scale} onChange={setScale} labels={{ log: "Log", linear: "Linear" }} />}
          </div>
        }>
          {curveOption ? <EChart option={curveOption} height={340} /> : <Loading />}
          <p className="note mt-2">Tick strategies in the table to add them. Drag the slider or scroll to zoom.</p>
        </Card>
        <Card title="Return correlation between strategies (x100)">{corrOption ? <EChart option={corrOption} height={400} /> : <Empty title="No data" />}</Card>
      </div>

      {sel && selMeta && (
        <div className="mt-3 grid gap-3 xl:grid-cols-3">
          <Card title={`${selMeta.name} · documentation`} right={<StatusTag s={sel.validation_status?.status} />}>
            <div className="space-y-2.5 text-[12.5px] leading-relaxed">
              <p><span className="text-faint">Hypothesis. </span>{selMeta.hypothesis}</p>
              <p><span className="text-faint">Definition. </span>{selMeta.definition}</p>
              <p><span className="text-faint">Assumptions. </span>{selMeta.assumptions}. Benchmark: {selMeta.benchmark} and the equal-weight eligible universe.</p>
              {sel.validation_status && (
                <div>
                  <span className="text-faint">Validation ({sel.validation_status.yardstick}). </span>
                  {sel.validation_status.reasons.length === 0 ? "Passed every check after costs." : (
                    <ul className="mt-1 list-disc space-y-0.5 pl-4 text-dim">{sel.validation_status.reasons.map((r: string) => <li key={r}>{r}</li>)}</ul>
                  )}
                </div>
              )}
            </div>
          </Card>
          <Card title="Train / validation / out-of-sample" pad={false}>
            <table className="w-full table-fixed">
              <thead><tr className="border-b border-line"><th className="th w-[36%]">Segment</th><th className="th text-right">CAGR</th><th className="th text-right">Sharpe</th><th className="th text-right">Max DD</th><th className="th text-right">vs univ.</th></tr></thead>
              <tbody>
                {SEGMENTS.map((s) => {
                  const g = sel.segments[s];
                  return (
                    <tr key={s} className="border-b border-line/50">
                      <td className="td">{titleCase(s)}<div className="text-[10.5px] text-faint">{g.start?.slice(0, 7)} to {g.end?.slice(0, 7)}</div></td>
                      <td className="td num text-right">{fmtPct(g.cagr)}</td>
                      <td className="td num text-right">{fmtNum(g.sharpe)}</td>
                      <td className="td num text-right text-down">{fmtPct(g.max_drawdown)}</td>
                      <td className={`td num text-right ${signClass(sel.vs_universe?.segments?.[s])}`}>{fmtPct(sel.vs_universe?.segments?.[s], 1, true)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="p-4">
              <KV rows={[
                ["Sharpe 95% interval (block bootstrap)", `${fmtNum(sel.bootstrap_sharpe?.lo)} to ${fmtNum(sel.bootstrap_sharpe?.hi)}`],
                ["Deflated Sharpe Ratio", sel.deflated_sharpe ? `${fmtNum(sel.deflated_sharpe.dsr)} (${sel.deflated_sharpe.n_trials} trials)` : "—"],
                ["Excess vs universe, FDR-adjusted p", fmtNum(sel.excess_vs_universe_test?.p_adj, 3)],
                ["Tracking error vs universe", fmtPct(sel.vs_universe?.tracking_error)],
                ["Information ratio vs universe", fmtNum(sel.vs_universe?.information_ratio)],
                ["Alpha / beta vs SPY", `${fmtPct(sel.metrics.alpha)} / ${fmtNum(sel.metrics.beta)}`],
                ["Average exposure / holdings", `${fmtPct(sel.exposure_avg, 0)} / ${fmtNum(sel.holdings_avg, 0)}`],
                ["Closed positions · avg win / loss", `${sel.trade_stats.n_trades} · ${fmtPct(sel.trade_stats.avg_win)} / ${fmtPct(sel.trade_stats.avg_loss)}`],
              ]} />
            </div>
          </Card>
          <Card title="Sensitivity and current holdings">
            <div className="text-[10.5px] font-semibold uppercase tracking-[0.12em] text-faint">Transaction-cost sensitivity (bps each way)</div>
            <table className="mt-1 w-full">
              <tbody>
                {Object.entries(sel.cost_sensitivity ?? {}).map(([bps, v]: [string, J]) => (
                  <tr key={bps} className="border-b border-line/40"><td className="td pl-0 text-dim">{bps} bps</td><td className="td num text-right">{fmtPct(v.cagr)} CAGR</td><td className="td num pr-0 text-right text-dim">{fmtNum(v.sharpe)} Sharpe</td></tr>
                ))}
              </tbody>
            </table>
            <div className="mt-3 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-faint">By market regime (annualised)</div>
            <table className="mt-1 w-full">
              <tbody>
                {Object.entries(sel.by_regime ?? {}).map(([g, v]: [string, J]) => (
                  <tr key={g} className="border-b border-line/40"><td className="td pl-0 text-dim">{titleCase(g)} · {v.days}d</td><td className={`td num text-right ${signClass(v.ann_return)}`}>{fmtPct(v.ann_return, 1, true)}</td><td className="td num pr-0 text-right text-dim">{fmtNum(v.sharpe)} Sharpe</td></tr>
                ))}
              </tbody>
            </table>
            <div className="mt-3 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-faint">Stocks currently qualifying ({sel.current_holdings.length})</div>
            <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[12px]">
              {sel.current_holdings.length ? sel.current_holdings.map((h: J) => <SymbolLink key={h.symbol} symbol={h.symbol} />) : <span className="text-faint">In cash: no stock qualifies right now.</span>}
            </div>
          </Card>
        </div>
      )}

      <PageTitle title="Factor research" sub={fr?.ic_note} />
      {!fr ? (
        <Card><Empty title="No factor research stored yet" /></Card>
      ) : (
        <div className="grid gap-3 xl:grid-cols-3">
          <Card title="Factor predictive power" pad={false} right={<Tag tone="warn">Backtested</Tag>}>
            <table className="w-full">
              <thead><tr className="border-b border-line"><th className="th">Factor</th><th className="th text-right">Mean IC</th><th className="th text-right">t-stat</th><th className="th text-right">Months &gt; 0</th></tr></thead>
              <tbody>
                {fr.factors.map((f: string) => {
                  const x = fr.ic[f];
                  return (
                    <tr key={f} onClick={() => setIcFactor(f)} className={`cursor-pointer border-b border-line/50 hover:bg-raised/50 ${icFactor === f ? "bg-raised" : ""}`} title={(fr.definitions[f] ?? []).join(", ")}>
                      <td className="td">{titleCase(f)}</td>
                      <td className={`td num text-right ${signClass(x.mean)}`}>{fmtNum(x.mean, 3)}</td>
                      <td className="td num text-right">{fmtNum(x.t_stat)}</td>
                      <td className="td num text-right text-dim">{fmtPct(x.hit_rate, 0)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="note px-4 py-2">{fr.ic[icFactor]?.n_months} monthly cross-sections. A t-stat above about 2 is conventionally significant; most factors here are not, on this small and survivorship-biased universe.</p>
          </Card>
          <Card title={`${titleCase(icFactor)} · information coefficient by month`}>{icOption ? <EChart option={icOption} height={300} /> : <Empty title="No series" />}</Card>
          <Card title="Factor correlation (current cross-section)">{fcorrOption ? <EChart option={fcorrOption} height={300} /> : <Empty title="No data" />}</Card>
        </div>
      )}
    </>
  );
}
