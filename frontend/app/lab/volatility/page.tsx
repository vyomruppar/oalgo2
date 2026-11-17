"use client";

import { useMemo, useState } from "react";
import EChart, { C, baseOption, catAxis, timeAxis, valueAxis, zoom } from "@/components/EChart";
import { FactorIC, StrategyLab } from "@/components/Lab";
import { Card, Empty, Loading, PageTitle, Seg, Stat, Tag, useApi } from "@/components/ui";
import type { J } from "@/lib/api";
import { fmtPct, regimeLabel, titleCase } from "@/lib/format";

const REGIME_COLOR: Record<string, string> = { risk_on: "rgba(61,242,196,0.16)", neutral: "rgba(255,196,107,0.10)", risk_off: "rgba(255,92,122,0.20)" };

export default function Volatility() {
  const [years, setYears] = useState<"2" | "5" | "10">("5");
  const hist = useApi(`/api/lab/regime-history?years=${years}`);
  const strat = useApi("/api/strategies");
  const market = useApi("/api/market/indexes?range=2y");
  const h = hist.data;

  const regimeOption = useMemo(() => {
    if (!h?.available) return null;
    const areas: J[] = [];
    let start = 0;
    for (let i = 1; i <= h.dates.length; i++) {
      if (i === h.dates.length || h.regime[i] !== h.regime[start]) {
        areas.push([{ xAxis: h.dates[start], itemStyle: { color: REGIME_COLOR[h.regime[start]] } }, { xAxis: h.dates[i - 1] }]);
        start = i;
      }
    }
    return baseOption({
      xAxis: timeAxis(),
      yAxis: [valueAxis(), valueAxis({ splitLine: { show: false }, axisLabel: { color: C.faint, fontSize: 10.5, formatter: (v: number) => `${(v * 100).toFixed(0)}%` } })],
      dataZoom: zoom(),
      grid: { left: 52, right: 48, top: 32, bottom: 44 },
      series: [
        { name: "S&P 500", type: "line", showSymbol: false, lineStyle: { width: 1.8, color: C.ink }, itemStyle: { color: C.ink }, data: h.dates.map((d: string, i: number) => [d, h.close[i]]), markArea: { silent: true, data: areas } },
        { name: "21-day realised volatility", type: "line", yAxisIndex: 1, showSymbol: false, lineStyle: { width: 1.2, color: C.accent }, itemStyle: { color: C.accent }, data: h.dates.map((d: string, i: number) => [d, h.realized_vol[i]]) },
      ],
    });
  }, [h]);

  const byRegime = useMemo(() => {
    const R = strat.data?.results;
    if (!R) return null;
    const keys: string[] = strat.data.strategies.map((s: J) => s.key);
    const names = strat.data.strategies.map((s: J) => s.name.replace(" with market filter", "").replace("moving-average ", "MA "));
    return baseOption({
      grid: { left: 84, right: 12, top: 32, bottom: 112 },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v) => (v == null ? "n/a" : `${(Number(v) * 100).toFixed(1)}%`) },
      xAxis: catAxis(names, { axisLabel: { color: C.faint, fontSize: 10.5, rotate: 35, interval: 0 } }),
      yAxis: valueAxis({ scale: false, axisLabel: { color: C.faint, fontSize: 10.5, formatter: (v: number) => `${(v * 100).toFixed(0)}%` } }),
      series: (["risk_on", "neutral", "risk_off"] as const).map((g) => ({ name: regimeLabel(g).label, type: "bar", itemStyle: { color: g === "risk_on" ? C.up : g === "neutral" ? C.warn : C.down, borderRadius: [2, 2, 0, 0] }, emphasis: { focus: "series" }, data: keys.map((k) => R[k]?.by_regime?.[g]?.ann_return ?? null) })),
    });
  }, [strat.data]);

  const volOption = useMemo(() => {
    const ix = market.data?.indexes;
    if (!ix?.VIX?.available || !ix?.SP500?.available) return null;
    return baseOption({
      xAxis: timeAxis(),
      yAxis: valueAxis(),
      dataZoom: zoom(),
      grid: { left: 40, right: 16, top: 32, bottom: 44 },
      series: [
        { name: "VIX (implied)", type: "line", showSymbol: false, lineStyle: { width: 1.6 }, areaStyle: { opacity: 0.12 }, data: ix.VIX.dates.map((d: string, i: number) => [d, ix.VIX.ohlc.close[i]]) },
        { name: "S&P 500 realised, 21-day (annualised %)", type: "line", showSymbol: false, lineStyle: { width: 1.6 }, data: ix.SP500.dates.map((d: string, i: number) => [d, ix.SP500.realized_vol_21[i] == null ? null : ix.SP500.realized_vol_21[i] * 100]) },
      ],
    });
  }, [market.data]);

  return (
    <>
      <PageTitle title="Volatility and regime" sub="How turbulent the market is, which regime the rule set reads, how long each regime has lasted, and how every strategy behaved in each." right={<Seg options={["2", "5", "10"] as const} value={years} onChange={setYears} labels={{ "2": "2 years", "5": "5 years", "10": "10 years" }} />} />
      {h?.available && (
        <div className="mb-4 grid grid-cols-3 gap-3">
          {(["risk_on", "neutral", "risk_off"] as const).map((g) => (
            <Stat key={g} label={`${regimeLabel(g).label} days`} value={fmtPct(h.share_of_days[g] ?? 0, 0)} cls={regimeLabel(g).cls} sub={`of the last ${years} years`} />
          ))}
        </div>
      )}
      <Card title="Regime history on the S&P 500" right={<Tag>Rule-based</Tag>}>
        {!h ? <Loading /> : regimeOption ? <EChart option={regimeOption} height={340} /> : <Empty title="No index history stored">Run a scan first.</Empty>}
        <p className="note mt-1">Green bands are risk-on, amber neutral, red risk-off. {h?.method ? `${titleCase(h.method.split(":")[0])}: ${h.method.split(":")[1]}.` : ""} The history uses index data only; the live reading on the Market page also uses breadth.</p>
      </Card>
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="Implied against realised volatility">{volOption ? <EChart option={volOption} height={280} /> : <Empty title="No volatility data stored" />}</Card>
        <Card title="Every strategy by regime (annualised return)" right={<Tag tone="warn">Backtested</Tag>}>{byRegime ? <EChart option={byRegime} height={280} /> : <Empty title="No backtests yet" />}</Card>
      </div>
      <div className="mt-4">
        <StrategyLab keys={["low_vol", "trend"]} />
      </div>
      <FactorIC factors={["low_vol"]} />
    </>
  );
}
