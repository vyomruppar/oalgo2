"use client";

import { ColorType, CrosshairMode, LineStyle, createChart, type IChartApi, type Time } from "lightweight-charts";
import { useEffect, useRef } from "react";
import { C } from "./EChart";

export type Overlay = { key: string; label: string; color: string; dashed?: boolean };

export const OVERLAYS: Overlay[] = [
  { key: "sma_20", label: "SMA 20", color: "#5ec8ff" },
  { key: "sma_50", label: "SMA 50", color: "#8b7cff" },
  { key: "sma_200", label: "SMA 200", color: "#c586c0" },
  { key: "ema_12", label: "EMA 12", color: "#7fb8b0" },
  { key: "ema_26", label: "EMA 26", color: "#e8915a" },
  { key: "bb_upper", label: "Bollinger upper", color: "#8c96a5", dashed: true },
  { key: "bb_lower", label: "Bollinger lower", color: "#8c96a5", dashed: true },
  { key: "vwap_20", label: "VWAP 20d (approx.)", color: "#5fc4d6" },
  { key: "ichi_tenkan", label: "Ichimoku tenkan", color: "#e86868" },
  { key: "ichi_kijun", label: "Ichimoku kijun", color: "#9aa4f2" },
  { key: "ichi_span_a", label: "Ichimoku span A", color: "#4abe8e", dashed: true },
  { key: "ichi_span_b", label: "Ichimoku span B", color: "#d88aa6", dashed: true },
];

type Props = {
  dates: string[];
  ohlcv: { open: (number | null)[]; high: (number | null)[]; low: (number | null)[]; close: (number | null)[]; volume: (number | null)[] };
  indicators: Record<string, (number | null)[]>;
  active: string[];
  mode: "candles" | "line" | "area";
  height?: number;
};

export default function CandleChart({ dates, ohlcv, indicators, active, mode, height = 420 }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart: IChartApi = createChart(ref.current, {
      height,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: C.dim, fontSize: 11 },
      grid: { vertLines: { color: "rgba(52,60,122,0.5)" }, horzLines: { color: "rgba(52,60,122,0.5)" } },
      rightPriceScale: { borderColor: C.line, scaleMargins: { top: 0.06, bottom: 0.24 } },
      timeScale: { borderColor: C.line, rightOffset: 4 },
      crosshair: { mode: CrosshairMode.Normal },
    });
    const t = (i: number) => dates[i] as Time;

    if (mode === "candles") {
      const s = chart.addCandlestickSeries({ upColor: C.up, downColor: C.down, borderUpColor: C.up, borderDownColor: C.down, wickUpColor: C.up, wickDownColor: C.down });
      s.setData(
        dates.flatMap((_, i) => {
          const [o, h, l, c] = [ohlcv.open[i], ohlcv.high[i], ohlcv.low[i], ohlcv.close[i]];
          return o == null || h == null || l == null || c == null ? [] : [{ time: t(i), open: o, high: h, low: l, close: c }];
        }),
      );
    } else {
      const data = dates.flatMap((_, i) => (ohlcv.close[i] == null ? [] : [{ time: t(i), value: ohlcv.close[i] as number }]));
      if (mode === "area") chart.addAreaSeries({ lineColor: C.accent, topColor: "rgba(139,124,255,0.25)", bottomColor: "rgba(139,124,255,0.0)", lineWidth: 2 }).setData(data);
      else chart.addLineSeries({ color: C.accent, lineWidth: 2 }).setData(data);
    }

    const vol = chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "vol" });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    vol.setData(
      dates.flatMap((_, i) => {
        const v = ohlcv.volume[i];
        if (v == null) return [];
        const up = (ohlcv.close[i] ?? 0) >= (ohlcv.open[i] ?? 0);
        return [{ time: t(i), value: v, color: up ? "rgba(61,242,196,0.35)" : "rgba(255,92,122,0.35)" }];
      }),
    );

    for (const o of OVERLAYS) {
      if (!active.includes(o.key) || !indicators[o.key]) continue;
      const line = chart.addLineSeries({ color: o.color, lineWidth: 1, lineStyle: o.dashed ? LineStyle.Dashed : LineStyle.Solid, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      line.setData(dates.flatMap((_, i) => (indicators[o.key][i] == null ? [] : [{ time: t(i), value: indicators[o.key][i] as number }])));
    }

    chart.timeScale().fitContent();
    const ro = new ResizeObserver((e) => chart.applyOptions({ width: e[0].contentRect.width }));
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, [dates, ohlcv, indicators, active, mode, height]);

  return <div ref={ref} style={{ height, width: "100%" }} />;
}
