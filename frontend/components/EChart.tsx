"use client";

import * as echarts from "echarts";
import { useEffect, useRef } from "react";

export const C = {
  ink: "#e8ebff",
  dim: "#a0a8d6",
  faint: "#6c75aa",
  line: "#343c7a",
  panel: "#0e1230",
  accent: "#8b7cff",
  up: "#3df2c4",
  down: "#ff5c7a",
  warn: "#ffc46b",
  series: ["#8b7cff", "#3df2c4", "#ffc46b", "#5ec8ff", "#ff7ad9", "#ff5c7a", "#b6f36a", "#ff9d5c", "#9aa4f2", "#7ff0ff", "#d7b4ff", "#8c96c5"],
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
    animationDuration: 900,
    animationEasing: "cubicOut",
    animationDurationUpdate: 500,
    textStyle: { fontFamily: "Hanken Grotesk Variable, ui-sans-serif, system-ui", color: C.dim },
    grid: { left: 52, right: 16, top: 28, bottom: 28 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(16,20,56,0.96)",
      borderColor: C.line,
      textStyle: { color: C.ink, fontSize: 11.5 },
      axisPointer: { type: "cross", lineStyle: { color: C.faint }, crossStyle: { color: C.faint }, label: { backgroundColor: "#343c7a" } },
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
  { type: "slider", height: 16, bottom: 4, borderColor: C.line, backgroundColor: "transparent", fillerColor: "rgba(139,124,255,0.12)", handleSize: 10, textStyle: { color: C.faint, fontSize: 10 }, dataBackground: { lineStyle: { color: C.faint }, areaStyle: { color: C.line } } },
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
