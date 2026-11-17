"use client";

import { useMemo, useState } from "react";
import EChart, { C, baseOption, catAxis, timeAxis, valueAxis, zoom } from "./EChart";
import { Banner, Card, Empty, ErrorBox, KV, Loading, Seg, SymbolLink, Tag, useApi } from "./ui";
import type { J } from "@/lib/api";
import { fmtNum, fmtPct, signClass, titleCase } from "@/lib/format";

const SEGMENTS = ["train", "validation", "out_of_sample"] as const;

export function StatusTag({ s }: { s?: string }) {
  if (s === "supported") return <Tag tone="up">Supported</Tag>;
  if (s === "mixed") return <Tag tone="warn">Mixed</Tag>;
  if (s === "not supported") return <Tag tone="down">Not supported</Tag>;
  return <Tag>Benchmark</Tag>;
}

export function Disclosures({ data }: { data: J }) {
  const [open, setOpen] = useState(false);
  return (
    <Banner>
      <button type="button" className="flex w-full items-center justify-between gap-3 text-left" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span>
          <strong className="font-semibold">Backtested, hypothetical results.</strong> Survivorship bias overstates them; strategies are judged against the equal-weight universe.
        </span>
        <span className="shrink-0 underline">{open ? "Hide" : "Read the caveats"}</span>
      </button>
      {open && (
        <ul className="mt-2 list-disc space-y-0.5 pl-4">
          {data.disclosures.slice(1).map((d: string) => (
            <li key={d}>{d}</li>
          ))}
          <li>Top {data.config.top_n} stocks, equal weight, monthly re-rank, {data.config.cost_bps_one_way} bps cost each way, {data.config.first_date} to {data.config.last_date}.</li>
        </ul>
      )}
    </Banner>
  );
}

/** Backtest comparison for a subset of strategies: table, interactive curves and the selected strategy's detail. */
export function StrategyLab({ keys, initial }: { keys: string[]; initial?: string }) {
  const { data, error } = useApi("/api/strategies");
  const [selected, setSelected] = useState(initial ?? keys[0]);
  const [compare, setCompare] = useState<string[]>([...keys.slice(0, 3), "universe_ew", "SPY"]);
  const [scale, setScale] = useState<"log" | "linear">("log");
  const [view, setView] = useState<"equity" | "drawdown" | "rolling_sharpe">("equity");
  const curves = useApi(data?.available ? `/api/strategies/curves?keys=${[...new Set([...compare, selected])].join(",")}` : null);

  const names: Record<string, string> = useMemo(() => {
    const m: Record<string, string> = { SPY: "SPY total return", QQQ: "QQQ total return" };
    (data?.strategies ?? []).forEach((s: J) => (m[s.key] = s.name));
    return m;
  }, [data]);

  const curveOption = useMemo(() => {
    const cs = curves.data?.curves;
    if (!cs) return null;
    const ks = compare.filter((k) => cs[k]?.[view]);
    const pct = view === "drawdown";
    return baseOption({
      xAxis: timeAxis(),
      yAxis: view === "equity" && scale === "log" ? { type: "log", axisLine: { lineStyle: { color: C.line } }, axisLabel: { color: C.faint, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.line, opacity: 0.5 } } } : valueAxis({ axisLabel: { color: C.faint, fontSize: 10.5, formatter: (v: number) => (pct ? `${(v * 100).toFixed(0)}%` : v.toFixed(1)) } }),
      dataZoom: zoom(),
      grid: { left: 48, right: 16, top: 34, bottom: 44 },
      tooltip: { trigger: "axis", valueFormatter: (v) => (pct ? `${(Number(v) * 100).toFixed(1)}%` : Number(v).toFixed(2)) },
      series: ks.map((k) => ({ name: names[k] ?? k, type: "line", showSymbol: false, emphasis: { focus: "series" }, lineStyle: { width: k === selected ? 2.4 : 1.2, ...(k === selected ? { shadowBlur: 10, shadowColor: "rgba(139,124,255,0.6)" } : {}) }, areaStyle: pct && ks.length === 1 ? { opacity: 0.15 } : undefined, data: cs[k][view] })),
    });
  }, [curves.data, compare, view, scale, names, selected]);

  if (error && !data) return <ErrorBox error={error} />;
  if (!data) return <Loading rows={5} />;
  if (!data.available) return <Card><Empty title="No backtests yet">Backtests run during a scan once enough price and filing history is stored. Start a scan from the Command page.</Empty></Card>;

  const R = data.results;
  const meta: J[] = data.strategies.filter((m: J) => keys.includes(m.key));
  const sel = R[selected];
  const selMeta = data.strategies.find((m: J) => m.key === selected);
  const toggle = (k: string) => setCompare((c) => (c.includes(k) ? c.filter((x) => x !== k) : [...c, k]));
  const rows: J[] = [...meta, ...data.strategies.filter((m: J) => m.key === "universe_ew")];

  return (
    <>
      <Disclosures data={data} />
      <Card title="Strategies in this section" className="mt-4" pad={false}>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-line/40">
                <th className="th">Plot</th>
                <th className="th">Strategy</th>
                <th className="th">Evidence</th>
                <th className="th">Status</th>
                <th className="th text-right">CAGR</th>
                <th className="th text-right">Sharpe</th>
                <th className="th text-right">Max drawdown</th>
                <th className="th text-right" title="Annualised return minus the equal-weight eligible universe">vs universe</th>
                <th className="th text-right" title="The same on the final quarter of the period">Out-of-sample</th>
                <th className="th text-right">vs SPY</th>
                <th className="th text-right">Turnover</th>
                <th className="th text-right">Win rate</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => {
                const r = R[m.key];
                const x = r.metrics;
                return (
                  <tr key={m.key} onClick={() => setSelected(m.key)} className={`cursor-pointer border-b border-line/30 transition-colors hover:bg-raised/40 ${selected === m.key ? "bg-accent/15" : ""}`}>
                    <td className="td" onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" aria-label={`Plot ${m.name}`} checked={compare.includes(m.key)} onChange={() => toggle(m.key)} className="accent-[#8b7cff]" />
                    </td>
                    <td className="td font-medium">{m.name}</td>
                    <td className="td text-dim">{m.evidence}</td>
                    <td className="td"><StatusTag s={r.validation_status?.status} /></td>
                    <td className="td num text-right">{fmtPct(x.cagr)}</td>
                    <td className="td num text-right">{fmtNum(x.sharpe)}</td>
                    <td className="td num text-right text-down">{fmtPct(x.max_drawdown)}</td>
                    <td className={`td num text-right ${signClass(r.vs_universe?.excess_cagr)}`}>{fmtPct(r.vs_universe?.excess_cagr, 1, true)}</td>
                    <td className={`td num text-right ${signClass(r.vs_universe?.segments?.out_of_sample)}`}>{fmtPct(r.vs_universe?.segments?.out_of_sample, 1, true)}</td>
                    <td className={`td num text-right ${signClass(x.excess_cagr)}`}>{fmtPct(x.excess_cagr, 1, true)}</td>
                    <td className="td num text-right text-dim">{fmtNum(r.turnover_annual, 1)}x</td>
                    <td className="td num text-right text-dim">{fmtPct(r.trade_stats.win_rate, 0)}</td>
                  </tr>
                );
              })}
              {Object.entries(data.benchmarks).map(([k, x]: [string, J]) => (
                <tr key={k} className="border-b border-line/30 text-dim">
                  <td className="td"><input type="checkbox" aria-label={`Plot ${k}`} checked={compare.includes(k)} onChange={() => toggle(k)} className="accent-[#8b7cff]" /></td>
                  <td className="td">{names[k]}</td>
                  <td className="td">benchmark</td>
                  <td className="td"><StatusTag /></td>
                  <td className="td num text-right">{fmtPct(x.cagr)}</td>
                  <td className="td num text-right">{fmtNum(x.sharpe)}</td>
                  <td className="td num text-right">{fmtPct(x.max_drawdown)}</td>
                  <td className="td" colSpan={5} />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Historical curves" className="mt-4" right={
        <div className="flex flex-wrap items-center gap-2">
          <Seg options={["equity", "drawdown", "rolling_sharpe"] as const} value={view} onChange={setView} labels={{ equity: "Growth of 1", drawdown: "Drawdown", rolling_sharpe: "Rolling 1-year Sharpe" }} />
          {view === "equity" && <Seg options={["log", "linear"] as const} value={scale} onChange={setScale} labels={{ log: "Log", linear: "Linear" }} />}
        </div>
      }>
        {curveOption ? <EChart option={curveOption} height={340} /> : <Loading />}
        <p className="note mt-2">Tick rows above to add or remove lines. Click a legend entry to hide it, hover a line to isolate it, drag the slider or scroll to zoom.</p>
      </Card>

      {sel && selMeta && (
        <div className="mt-4 grid gap-4 xl:grid-cols-3">
          <Card title={selMeta.name} right={<StatusTag s={sel.validation_status?.status} />}>
            <div className="space-y-2.5 text-[12.5px] leading-relaxed">
              <p><span className="text-faint">Hypothesis. </span>{selMeta.hypothesis}</p>
              <p><span className="text-faint">Definition. </span>{selMeta.definition}</p>
              <p><span className="text-faint">Assumptions. </span>{selMeta.assumptions}.</p>
              {sel.validation_status && (
                <div>
                  <span className="text-faint">Validation against the {sel.validation_status.yardstick}. </span>
                  {sel.validation_status.reasons.length === 0 ? "Passed every check after costs." : <ul className="mt-1 list-disc space-y-0.5 pl-4 text-dim">{sel.validation_status.reasons.map((r: string) => <li key={r}>{r}</li>)}</ul>}
                </div>
              )}
            </div>
          </Card>
          <Card title="Train, validation, out-of-sample" pad={false}>
            <table className="w-full table-fixed">
              <thead><tr className="border-b border-line/40"><th className="th w-[36%]">Segment</th><th className="th text-right">CAGR</th><th className="th text-right">Sharpe</th><th className="th text-right">Max DD</th><th className="th text-right">vs univ.</th></tr></thead>
              <tbody>
                {SEGMENTS.map((s) => {
                  const g = sel.segments[s];
                  return (
                    <tr key={s} className="border-b border-line/30">
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
                ["Deflated Sharpe Ratio", sel.deflated_sharpe ? fmtNum(sel.deflated_sharpe.dsr) : "—"],
                ["Excess vs universe, adjusted p-value", fmtNum(sel.excess_vs_universe_test?.p_adj, 3)],
                ["Information ratio vs universe", fmtNum(sel.vs_universe?.information_ratio)],
                ["Alpha / beta vs SPY", `${fmtPct(sel.metrics.alpha)} / ${fmtNum(sel.metrics.beta)}`],
                ["Closed positions, avg win / loss", `${sel.trade_stats.n_trades} · ${fmtPct(sel.trade_stats.avg_win)} / ${fmtPct(sel.trade_stats.avg_loss)}`],
              ]} />
            </div>
          </Card>
          <Card title="Costs, regimes and current picks">
            <div className="sub">Return at different trading costs (each way)</div>
            <table className="mt-1 w-full">
              <tbody>
                {Object.entries(sel.cost_sensitivity ?? {}).map(([bps, v]: [string, J]) => (
                  <tr key={bps} className="border-b border-line/30"><td className="td pl-0 text-dim">{bps} bps</td><td className="td num text-right">{fmtPct(v.cagr)} CAGR</td><td className="td num pr-0 text-right text-dim">{fmtNum(v.sharpe)} Sharpe</td></tr>
                ))}
              </tbody>
            </table>
            <div className="sub mt-3">By market regime (annualised)</div>
            <table className="mt-1 w-full">
              <tbody>
                {Object.entries(sel.by_regime ?? {}).map(([g, v]: [string, J]) => (
                  <tr key={g} className="border-b border-line/30"><td className="td pl-0 text-dim">{titleCase(g)} · {v.days} days</td><td className={`td num text-right ${signClass(v.ann_return)}`}>{fmtPct(v.ann_return, 1, true)}</td><td className="td num pr-0 text-right text-dim">{fmtNum(v.sharpe)} Sharpe</td></tr>
                ))}
              </tbody>
            </table>
            <div className="sub mt-3">Stocks qualifying now ({sel.current_holdings.length})</div>
            <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[12px]">
              {sel.current_holdings.length ? sel.current_holdings.map((h: J) => <SymbolLink key={h.symbol} symbol={h.symbol} />) : <span className="text-faint">In cash: nothing qualifies right now.</span>}
            </div>
          </Card>
        </div>
      )}
    </>
  );
}

/** Information-coefficient table and monthly series for a subset of factors. */
export function FactorIC({ factors, initial }: { factors: string[]; initial?: string }) {
  const { data } = useApi("/api/factors");
  const [active, setActive] = useState(initial ?? factors[0]);
  const fr = data?.ic ? data : null;

  const icOption = useMemo(() => {
    if (!fr?.ic?.[active]) return null;
    const s: [string, number][] = fr.ic[active].series;
    let acc = 0;
    return baseOption({
      xAxis: timeAxis(),
      yAxis: [valueAxis(), valueAxis({ splitLine: { show: false } })],
      dataZoom: zoom(),
      grid: { left: 44, right: 44, top: 32, bottom: 44 },
      series: [
        { name: "Monthly rank IC", type: "bar", data: s.map(([d, v]) => ({ value: [d, v], itemStyle: { color: v >= 0 ? C.up : C.down, opacity: 0.75, borderRadius: 1 } })) },
        { name: "Cumulative IC", type: "line", yAxisIndex: 1, showSymbol: false, lineStyle: { width: 1.8 }, color: C.warn, data: s.map(([d, v]) => [d, (acc += v)]) },
      ],
    });
  }, [fr, active]);

  if (!data) return <Loading />;
  if (!fr) return <Card><Empty title="No factor research stored yet">It is computed with the backtests during a scan.</Empty></Card>;
  const list = factors.filter((f) => fr.ic[f]);
  return (
    <div className="mt-4 grid gap-4 xl:grid-cols-3">
      <Card title="Predictive power of each factor" pad={false} right={<Tag tone="warn">Backtested</Tag>}>
        <table className="w-full">
          <thead><tr className="border-b border-line/40"><th className="th">Factor</th><th className="th text-right">Mean IC</th><th className="th text-right">t-stat</th><th className="th text-right">Months above 0</th></tr></thead>
          <tbody>
            {list.map((f) => {
              const x = fr.ic[f];
              return (
                <tr key={f} onClick={() => setActive(f)} className={`cursor-pointer border-b border-line/30 hover:bg-raised/40 ${active === f ? "bg-accent/15" : ""}`} title={(fr.definitions[f] ?? []).join(", ")}>
                  <td className="td">{titleCase(f)}</td>
                  <td className={`td num text-right ${signClass(x.mean)}`}>{fmtNum(x.mean, 3)}</td>
                  <td className="td num text-right">{fmtNum(x.t_stat)}</td>
                  <td className="td num text-right text-dim">{fmtPct(x.hit_rate, 0)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="note px-4 py-2">{fr.ic_note} A t-stat above about 2 is conventionally significant. Hover a row for the factor&apos;s inputs.</p>
      </Card>
      <Card title={`${titleCase(active)}: information coefficient by month`} className="xl:col-span-2">
        {icOption ? <EChart option={icOption} height={300} /> : <Empty title="No series" />}
      </Card>
    </div>
  );
}

export function FactorCorrelation() {
  const { data } = useApi("/api/factors");
  const option = useMemo(() => {
    if (!data?.correlation) return null;
    const labels: string[] = data.factors.map((f: string) => titleCase(f));
    const d: [number, number, number][] = [];
    data.correlation.forEach((row: number[], i: number) => row.forEach((v, j) => d.push([j, i, v])));
    return baseOption({
      grid: { left: 124, right: 12, top: 8, bottom: 90 },
      tooltip: { trigger: "item", formatter: (p: J) => `${labels[p.value[1]]} / ${labels[p.value[0]]}: ${p.value[2].toFixed(2)}` },
      xAxis: catAxis(labels, { axisLabel: { color: C.faint, fontSize: 10.5, rotate: 45, interval: 0 }, axisLine: { show: false } }),
      yAxis: catAxis(labels, { inverse: true, axisLine: { show: false }, axisLabel: { color: C.faint, fontSize: 10.5, interval: 0 } }),
      visualMap: { show: false, min: -1, max: 1, inRange: { color: ["#d0456b", "#11163c", "#2fd0aa"] } },
      series: [{ type: "heatmap", data: d, label: { show: true, fontSize: 10, color: C.ink, formatter: (p: J) => p.value[2].toFixed(2) }, itemStyle: { borderColor: C.panel, borderWidth: 2, borderRadius: 3 }, emphasis: { itemStyle: { borderColor: C.ink } } }],
    });
  }, [data]);
  return <Card title="How the factors overlap today">{option ? <EChart option={option} height={340} /> : <Empty title="No data yet" />}<p className="note mt-1">Rank correlation of factor scores across the current universe. Low overlap is what makes combining them worthwhile.</p></Card>;
}
