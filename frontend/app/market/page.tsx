"use client";

import { useMemo, useState } from "react";
import CandleChart from "@/components/CandleChart";
import EChart, { C, baseOption, catAxis, timeAxis, valueAxis, zoom } from "@/components/EChart";
import { Banner, Card, Empty, ErrorBox, Loading, PageTitle, Seg, Stat, Tag, useApi } from "@/components/ui";
import type { J } from "@/lib/api";
import { fmtNum, fmtPct, regimeLabel, signClass } from "@/lib/format";

const RANGES = ["3m", "6m", "1y", "2y", "5y", "max"] as const;
const INDEX_KEYS = ["SP500", "NASDAQ_COMPOSITE", "NASDAQ_100"] as const;
const HORIZONS = ["1d", "1w", "1m", "3m", "6m", "1y"] as const;

export default function Market() {
  const [range, setRange] = useState<(typeof RANGES)[number]>("1y");
  const [focus, setFocus] = useState<(typeof INDEX_KEYS)[number]>("SP500");
  const [mode, setMode] = useState<"candles" | "line" | "area">("candles");
  const [rs, setRs] = useState<"abs" | "rel">("abs");
  const idx = useApi(`/api/market/indexes?range=${range}`);
  const sum = useApi("/api/market/summary");

  const indexes = idx.data?.indexes;
  const f = indexes?.[focus];

  const compareOption = useMemo(() => {
    if (!indexes) return null;
    return baseOption({
      xAxis: timeAxis(),
      yAxis: valueAxis({ axisLabel: { color: C.faint, fontSize: 10.5, formatter: (v: number) => `${v.toFixed(0)}%` } }),
      dataZoom: zoom(),
      grid: { left: 48, right: 16, top: 28, bottom: 44 },
      tooltip: { trigger: "axis", valueFormatter: (v) => `${Number(v).toFixed(1)}%` },
      series: INDEX_KEYS.filter((k) => indexes[k]?.available).map((k) => ({
        name: indexes[k].name,
        type: "line",
        showSymbol: false,
        lineStyle: { width: 1.5 },
        data: indexes[k].dates.map((d: string, i: number) => [d, (indexes[k].ohlc.close[i] / indexes[k].ohlc.close[0] - 1) * 100]),
      })),
    });
  }, [indexes]);

  const volOption = useMemo(() => {
    const vix = indexes?.VIX;
    const sp = indexes?.SP500;
    if (!vix?.available || !sp?.available) return null;
    return baseOption({
      xAxis: timeAxis(),
      yAxis: valueAxis(),
      dataZoom: zoom(),
      grid: { left: 40, right: 16, top: 28, bottom: 44 },
      series: [
        { name: "VIX (implied)", type: "line", showSymbol: false, lineStyle: { width: 1.5 }, data: vix.dates.map((d: string, i: number) => [d, vix.ohlc.close[i]]) },
        { name: "S&P 500 21-day realised (annualised %)", type: "line", showSymbol: false, lineStyle: { width: 1.5 }, data: sp.dates.map((d: string, i: number) => [d, sp.realized_vol_21[i] == null ? null : sp.realized_vol_21[i] * 100]) },
      ],
    });
  }, [indexes]);

  const breadth = sum.data?.breadth;
  const breadthOption = useMemo(() => {
    if (!breadth) return null;
    const col = (name: string) => breadth.columns.indexOf(name) + 1;
    return baseOption({
      xAxis: timeAxis(),
      yAxis: [valueAxis({ min: 0, max: 100, scale: false, axisLabel: { color: C.faint, fontSize: 10.5, formatter: "{value}%" } }), valueAxis({ splitLine: { show: false } })],
      dataZoom: zoom(),
      grid: { left: 44, right: 52, top: 28, bottom: 44 },
      series: [
        { name: "% above 50-day average", type: "line", showSymbol: false, lineStyle: { width: 1.5 }, data: breadth.series.map((r: J[]) => [r[0], r[col("pct_above_50")]]) },
        { name: "% above 200-day average", type: "line", showSymbol: false, lineStyle: { width: 1.5 }, data: breadth.series.map((r: J[]) => [r[0], r[col("pct_above_200")]]) },
        { name: "Advance-decline line", type: "line", yAxisIndex: 1, showSymbol: false, lineStyle: { width: 1, type: "dashed" }, data: breadth.series.map((r: J[]) => [r[0], r[col("ad_line")]]) },
      ],
    });
  }, [breadth]);

  const sectors: J[] = sum.data?.sectors?.sectors ?? [];
  const heatOption = useMemo(() => {
    if (!sectors.length) return null;
    const rows = [...sectors].sort((a, b) => (b["1m"] ?? 0) - (a["1m"] ?? 0));
    const key = (h: string) => (rs === "rel" ? `rs_${h}` : h);
    const data: [number, number, number | null][] = [];
    rows.forEach((s, y) => HORIZONS.forEach((h, x) => data.push([x, y, s[key(h)] == null ? null : +(s[key(h)] * 100).toFixed(2)])));
    const vals = data.map((d) => Math.abs(d[2] ?? 0));
    const lim = Math.max(5, Math.min(40, Math.max(...vals)));
    return baseOption({
      grid: { left: 150, right: 16, top: 26, bottom: 8 },
      tooltip: { trigger: "item", formatter: (p: J) => `${rows[p.value[1]].sector} · ${HORIZONS[p.value[0]]}: ${p.value[2] == null ? "n/a" : `${p.value[2]}%`}` },
      xAxis: catAxis([...HORIZONS], { position: "top", axisLine: { show: false } }),
      yAxis: catAxis(rows.map((s) => `${s.sector} (${s.n})`), { inverse: true, axisLine: { show: false } }),
      visualMap: { show: false, min: -lim, max: lim, inRange: { color: ["#b84c4c", "#5a3336", "#1b2027", "#27503f", "#3fae80"] } },
      series: [{ type: "heatmap", data, label: { show: true, color: C.ink, fontSize: 10.5, formatter: (p: J) => (p.value[2] == null ? "" : `${p.value[2] > 0 ? "+" : ""}${p.value[2].toFixed(1)}`) }, itemStyle: { borderColor: C.panel, borderWidth: 2 } }],
    });
  }, [sectors, rs]);

  const macro = sum.data?.macro?.series;
  const macroOption = useMemo(() => {
    if (!macro) return null;
    const names: Record<string, string> = { DGS10: "10-year Treasury", DGS3MO: "3-month Treasury", T10Y2Y: "10y minus 2y spread" };
    return baseOption({
      xAxis: timeAxis(),
      yAxis: valueAxis({ axisLabel: { color: C.faint, fontSize: 10.5, formatter: "{value}%" } }),
      dataZoom: zoom(),
      grid: { left: 44, right: 16, top: 28, bottom: 44 },
      series: Object.keys(names).filter((k) => macro[k]).map((k) => ({ name: names[k], type: "line", showSymbol: false, lineStyle: { width: 1.5 }, data: macro[k].series })),
    });
  }, [macro]);

  if (idx.error && !idx.data) return <ErrorBox error={idx.error} />;
  const regime = sum.data?.regime;
  const rl = regimeLabel(regime?.regime);

  return (
    <>
      <PageTitle title="Market" sub="Index levels, volatility, breadth and sector performance. Index series are price-return levels from a delayed end-of-day source." right={<Seg options={RANGES} value={range} onChange={setRange} />} />
      {!indexes ? (
        <Loading rows={5} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
            {(["SP500", "NASDAQ_COMPOSITE", "NASDAQ_100", "VIX"] as const).map((k) => {
              const x = indexes[k];
              return x?.available ? (
                <Stat key={k} label={x.name} value={fmtNum(x.last)} sub={<span><span className={signClass(x.change_1d)}>{fmtPct(x.change_1d, 2, true)}</span> last session · <span className={signClass(x.change_range)}>{fmtPct(x.change_range, 1, true)}</span> {range} · {x.last_bar}</span>} />
              ) : (
                <Stat key={k} label={x?.name ?? k} value="—" sub="No data stored. Run a scan." />
              );
            })}
          </div>

          <div className="mt-3 grid gap-3 xl:grid-cols-3">
            <Card title={f?.available ? `${f.name} · daily` : "Index chart"} className="xl:col-span-2" right={
              <div className="flex items-center gap-2">
                <Seg options={INDEX_KEYS} value={focus} onChange={setFocus} labels={{ SP500: "S&P 500", NASDAQ_COMPOSITE: "Composite", NASDAQ_100: "NDX" }} />
                <Seg options={["candles", "line", "area"] as const} value={mode} onChange={setMode} labels={{ candles: "Candles", line: "Line", area: "Area" }} />
              </div>
            }>
              {f?.available ? <CandleChart dates={f.dates} ohlcv={{ ...f.ohlc, volume: f.volume }} indicators={{}} active={[]} mode={mode} height={340} /> : <Empty title="No index data stored yet">Run a scan to download index history.</Empty>}
            </Card>
            <Card title="Market regime" right={<span className={`text-xs font-semibold ${rl.cls}`}>{rl.label}</span>}>
              {regime?.components?.length ? (
                <>
                  <ul className="space-y-2 text-[12.5px]">
                    {regime.components.map((c: J) => (
                      <li key={c.name} className="flex items-start justify-between gap-3">
                        <span className="text-dim">{c.name}</span>
                        <span className="text-right">
                          <span className="num">{c.name === "VIX" ? fmtNum(c.value, 1) : fmtPct(c.value, 1, c.name.includes("vs"))}</span>
                          <span className="block text-[10.5px] text-faint">{c.reading}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                  <p className="note mt-3">Reading from trend, volatility percentile, VIX level and breadth rules. Score {fmtNum(regime.score, 1)}: 1 or more is risk-on, -1 or less is risk-off. A description of current conditions, not a forecast.</p>
                </>
              ) : (
                <Empty title="No regime reading yet" />
              )}
            </Card>
          </div>

          <div className="mt-3 grid gap-3 xl:grid-cols-2">
            <Card title={`Index performance · ${range}`}>{compareOption ? <EChart option={compareOption} height={260} /> : <Empty title="No data" />}</Card>
            <Card title="Volatility · implied vs realised">{volOption ? <EChart option={volOption} height={260} /> : <Empty title="No volatility data stored" />}</Card>
            <Card title="Market breadth" right={breadth && <Tag>{breadth.universe}</Tag>}>
              {breadthOption ? <EChart option={breadthOption} height={260} /> : <Empty title="No breadth data yet" />}
              <p className="note mt-2">Breadth is measured on the scanned stocks, not on every listed company.</p>
            </Card>
            <Card title="Treasury yields" right={macro && <Tag>FRED · {macro.DGS10?.as_of}</Tag>}>
              {macroOption ? <EChart option={macroOption} height={260} /> : <Empty title="No macro series stored">Fetched with the research refresh during a scan.</Empty>}
            </Card>
          </div>

          <Card title="Sector performance and relative strength" className="mt-3" right={<Seg options={["abs", "rel"] as const} value={rs} onChange={setRs} labels={{ abs: "Return", rel: "Relative to SPY" }} />}>
            {heatOption ? <EChart option={heatOption} height={Math.max(220, sectors.length * 30 + 40)} /> : <Empty title="No sector data yet" />}
            {sum.data?.sectors && <Banner tone="info">Equal-weight average return of the scanned stocks in each sector, as of {sum.data.sectors.as_of}. &ldquo;Relative to SPY&rdquo; subtracts the SPY return over the same window. Sectors are grouped from SEC SIC codes and will not match GICS exactly.</Banner>}
          </Card>
        </>
      )}
    </>
  );
}
