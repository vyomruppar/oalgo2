"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import EChart, { C, baseOption, valueAxis } from "@/components/EChart";
import { FactorIC, StrategyLab } from "@/components/Lab";
import { Card, Empty, Loading, PageTitle, Seg, SignalChip, SymbolLink, Tag, useApi } from "@/components/ui";
import type { J } from "@/lib/api";
import { fmtNum, fmtPct, signClass } from "@/lib/format";
import { SIGNAL_COLOR } from "@/lib/starmap";

export default function MeanReversion() {
  const router = useRouter();
  const { data } = useApi("/api/lab/mean-reversion");
  const [side, setSide] = useState<"oversold" | "overbought">("oversold");
  const items: J[] = data?.items ?? [];

  const scatter = useMemo(() => {
    if (!items.length) return null;
    return baseOption({
      grid: { left: 48, right: 20, top: 16, bottom: 40 },
      legend: { show: false },
      tooltip: { trigger: "item", formatter: (p: J) => `<b>${p.data.name}</b><br/>Bollinger z-score ${p.value[0].toFixed(2)}<br/>RSI(14) ${p.value[1].toFixed(0)}<br/>1 month ${(p.data.ret * 100).toFixed(1)}%` },
      xAxis: valueAxis({ name: "Distance from 20-day average, in standard deviations", nameLocation: "middle", nameGap: 26, nameTextStyle: { color: C.faint, fontSize: 11 } }),
      yAxis: valueAxis({ name: "RSI (14)", min: 0, max: 100, scale: false, nameTextStyle: { color: C.faint, fontSize: 11 } }),
      dataZoom: [{ type: "inside", xAxisIndex: 0 }, { type: "inside", yAxisIndex: 0 }],
      series: [{
        type: "scatter",
        symbolSize: (v: number[]) => 6 + Math.min(10, Math.abs(v[0]) * 3),
        data: items.map((x) => ({ name: x.symbol, value: [x.bb_z, x.rsi_14], ret: x.ret_1m ?? 0, itemStyle: { color: SIGNAL_COLOR[x.signal ?? "NONE"] ?? SIGNAL_COLOR.NONE, opacity: 0.8 } })),
        emphasis: { scale: 1.6, itemStyle: { borderColor: C.ink, borderWidth: 1 }, label: { show: true, formatter: (p: J) => p.data.name, color: C.ink, position: "top", fontSize: 11 } },
        markArea: { silent: true, itemStyle: { opacity: 0.08 }, data: [[{ xAxis: -10, yAxis: 0, itemStyle: { color: C.up } }, { xAxis: -2, yAxis: 30 }], [{ xAxis: 2, yAxis: 70, itemStyle: { color: C.down } }, { xAxis: 10, yAxis: 100 }]] },
        markLine: { silent: true, symbol: "none", lineStyle: { color: C.faint, type: "dashed" }, label: { show: false }, data: [{ yAxis: 30 }, { yAxis: 70 }, { xAxis: -2 }, { xAxis: 2 }] },
      }],
    });
  }, [items]);

  const ranked = useMemo(() => [...items].sort((a, b) => (side === "oversold" ? a.bb_z - b.bb_z : b.bb_z - a.bb_z)).slice(0, 12), [items, side]);

  return (
    <>
      <PageTitle title="Mean reversion" sub="How far each stock has stretched from its own recent average, and whether betting on a snap-back has paid. Stretch is measured with the Bollinger z-score and RSI." right={<Tag tone="warn">Backtested</Tag>} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <Card title={`Where every scored stock sits now${data?.as_of ? ` (${data.as_of})` : ""}`}>
          {!data ? <Loading /> : scatter ? <EChart option={scatter} height={380} onClick={(p) => typeof p.name === "string" && p.name && router.push(`/stocks/${p.name}`)} /> : <Empty title="No readings yet">They are stored with the next scan.</Empty>}
          <p className="note mt-1">Bottom-left is stretched down (oversold), top-right stretched up (overbought). Colour is the current signal. Scroll to zoom, click a point to open the stock.</p>
        </Card>
        <Card title="Most stretched" pad={false} right={<Seg options={["oversold", "overbought"] as const} value={side} onChange={setSide} labels={{ oversold: "Down", overbought: "Up" }} />}>
          {ranked.length === 0 ? <Empty title="No readings yet" /> : (
            <table className="w-full">
              <thead><tr className="border-b border-line/40"><th className="th">Stock</th><th className="th text-right">z-score</th><th className="th text-right">RSI</th><th className="th text-right">1 month</th><th className="th">Signal</th></tr></thead>
              <tbody>
                {ranked.map((x) => (
                  <tr key={x.symbol} className="border-b border-line/30 hover:bg-raised/40">
                    <td className="td"><SymbolLink symbol={x.symbol} /></td>
                    <td className={`td num text-right ${signClass(x.bb_z)}`}>{fmtNum(x.bb_z)}</td>
                    <td className="td num text-right">{fmtNum(x.rsi_14, 0)}</td>
                    <td className={`td num text-right ${signClass(x.ret_1m)}`}>{fmtPct(x.ret_1m, 1, true)}</td>
                    <td className="td"><SignalChip signal={x.signal} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {data?.note && <p className="note border-t border-line/40 px-4 py-2">{data.note}</p>}
        </Card>
      </div>
      <div className="mt-4">
        <StrategyLab keys={["reversal"]} />
      </div>
      <FactorIC factors={["reversal"]} />
    </>
  );
}
