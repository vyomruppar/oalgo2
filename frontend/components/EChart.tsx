"use client";

import * as echarts from "echarts";
import { useEffect, useRef } from "react";

export const C = {
  ink: "#e2e6ec",
  dim: "#949daa",
  faint: "#626b79",
  line: "#262c36",
  panel: "#111419",
  accent: "#d6a85c",
  up: "#4abe8e",
  down: "#e86868",
  series: ["#d6a85c", "#6ea8d8", "#4abe8e", "#c586c0", "#e8915a", "#7fb8b0", "#e86868", "#9aa4f2", "#b9c26a", "#d88aa6", "#8c96a5", "#5fc4d6"],
};

const axisBase = {
  axisLine: { lineStyle: { color: C.line } },
  axisTick: { show: false },
  axisLabel: { color: C.faint, fontSize: 10.5 },
  splitLine: { lineStyle: { color: C.line, opacity: 0.6 } },
};

/** Shared option defaults so every chart reads as one system. */
export function baseOption(extra: echarts.EChartsOption = {}): echarts.EChartsOption {
  return {
    backgroundColor: "transparent",
    color: C.series,
    textStyle: { fontFamily: "var(--font-sans), ui-sans-serif, system-ui", color: C.dim },
    grid: { left: 52, right: 16, top: 28, bottom: 28 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#181c23",
      borderColor: C.line,
      textStyle: { color: C.ink, fontSize: 11.5 },
      axisPointer: { type: "cross", lineStyle: { color: C.faint }, crossStyle: { color: C.faint }, label: { backgroundColor: "#262c36" } },
    },
    legend: { textStyle: { color: C.dim, fontSize: 11 }, top: 0, left: 0, icon: "roundRect", itemWidth: 10, itemHeight: 3, inactiveColor: C.faint },
    ...extra,
  };
}

export const timeAxis = (extra: object = {}) => ({ type: "time" as const, ...axisBase, splitLine: { show: false }, ...extra });
export const valueAxis = (extra: object = {}) => ({ type: "value" as const, scale: true, ...axisBase, ...extra });
export const catAxis = (data: string[], extra: object = {}) => ({ type: "category" as const, data, ...axisBase, splitLine: { show: false }, ...extra });
export const zoom = (): echarts.DataZoomComponentOption[] => [
  { type: "inside", throttle: 40 },
  { type: "slider", height: 16, bottom: 4, borderColor: C.line, backgroundColor: "transparent", fillerColor: "rgba(214,168,92,0.12)", handleSize: 10, textStyle: { color: C.faint, fontSize: 10 }, dataBackground: { lineStyle: { color: C.faint }, areaStyle: { color: C.line } } },
];

export default function EChart({ option, height = 260, onClick }: { option: echarts.EChartsOption; height?: number; onClick?: (p: echarts.ECElementEvent) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const c = echarts.init(ref.current, undefined, { renderer: "canvas" });
    chart.current = c;
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      c.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    chart.current?.setOption(option, { notMerge: true });
  }, [option]);

  useEffect(() => {
    const c = chart.current;
    if (!c || !onClick) return;
    c.on("click", onClick);
    return () => {
      c.off("click", onClick);
    };
  }, [onClick]);

  return <div ref={ref} style={{ height, width: "100%" }} />;
}
