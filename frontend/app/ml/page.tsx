"use client";

import { useMemo, useState } from "react";
import EChart, { C, baseOption, catAxis, timeAxis, valueAxis, zoom } from "@/components/EChart";
import { Banner, Card, Empty, ErrorBox, KV, Loading, PageTitle, Seg, SymbolLink, Tag, useApi } from "@/components/ui";
import type { J } from "@/lib/api";
import { fmtDateTime, fmtNum, fmtPct, signClass, titleCase } from "@/lib/format";

export default function ModelMonitor() {
  const { data, error } = useApi("/api/ml");
  const [model, setModel] = useState("gradient_boosting");
  const m = data?.models?.[model];

  const calOption = useMemo(() => {
    if (!m?.calibration?.length) return null;
    return baseOption({
      grid: { left: 44, right: 16, top: 28, bottom: 36 },
      xAxis: valueAxis({ name: "Model score", nameLocation: "middle", nameGap: 22, nameTextStyle: { color: C.faint, fontSize: 10.5 }, min: 0.3, max: 0.7 }),
      yAxis: valueAxis({ min: 0.3, max: 0.7 }),
      tooltip: { trigger: "item", formatter: (p: J) => (p.seriesName === "Observed" ? `score ${p.value[0].toFixed(3)} → beat median ${(p.value[1] * 100).toFixed(1)}% of the time (n=${p.value[2]})` : "perfect calibration") },
      series: [
        { name: "Perfect calibration", type: "line", showSymbol: false, color: C.faint, lineStyle: { type: "dashed", color: C.faint, width: 1 }, data: [[0.3, 0.3], [0.7, 0.7]] },
        { name: "Observed", type: "line", color: C.accent, symbol: "circle", itemStyle: { color: C.accent }, symbolSize: (v: number[]) => Math.max(5, Math.min(14, Math.sqrt(v[2]) / 8)), data: m.calibration.map((c: J) => [c.predicted, c.actual, c.n]) },
      ],
    });
  }, [m]);

  const icOption = useMemo(() => {
    if (!m?.ic_by_date?.length) return null;
    return baseOption({
      xAxis: timeAxis(),
      yAxis: valueAxis(),
      dataZoom: zoom(),
      grid: { left: 44, right: 16, top: 12, bottom: 44 },
      legend: { show: false },
      series: [{ name: "Rank IC", type: "bar", data: m.ic_by_date.map(([d, v]: [string, number]) => ({ value: [d, v], itemStyle: { color: v >= 0 ? C.up : C.down, opacity: 0.75 } })) }],
    });
  }, [m]);

  const impOption = useMemo(() => {
    const imp: J[] = m?.feature_importance ?? [];
    if (!imp.length) return null;
    const rows = [...imp].reverse();
    return baseOption({
      grid: { left: 120, right: 30, top: 6, bottom: 20 },
      legend: { show: false },
      tooltip: { trigger: "item" },
      xAxis: valueAxis({ scale: false }),
      yAxis: catAxis(rows.map((r) => titleCase(r.feature)), { axisLine: { show: false } }),
      series: [{ type: "bar", barWidth: 10, data: rows.map((r) => ({ value: +r.importance.toFixed(4), itemStyle: { color: r.direction == null ? C.accent : r.direction >= 0 ? C.up : C.down, borderRadius: 2 } })) }],
    });
  }, [m]);

  const errOption = useMemo(() => {
    const e: J[] = m?.error_by_year ?? [];
    if (!e.length) return null;
    return baseOption({
      grid: { left: 44, right: 16, top: 12, bottom: 24 },
      legend: { show: false },
      xAxis: catAxis(e.map((x) => String(x.year))),
      yAxis: valueAxis({ min: 0.4, max: 0.6, axisLabel: { color: C.faint, fontSize: 10.5, formatter: (v: number) => `${(v * 100).toFixed(0)}%` } }),
      series: [{ type: "bar", barWidth: 18, data: e.map((x) => ({ value: x.accuracy, itemStyle: { color: x.accuracy >= 0.5 ? C.up : C.down, opacity: 0.8 } })), markLine: { symbol: "none", lineStyle: { color: C.faint, type: "dashed" }, data: [{ yAxis: 0.5 }], label: { formatter: "coin flip", color: C.faint, fontSize: 10, position: "insideEndTop" } } }],
    });
  }, [m]);

  if (error && !data) return <ErrorBox error={error} />;
  if (!data) return <Loading rows={6} />;
  if (data.status !== "ok")
    return (
      <>
        <PageTitle title="Model Monitor" />
        <Card>
          <Empty title={data.status === "insufficient_history" ? "Not enough history to train" : "No model has been trained yet"}>
            {data.detail ?? "Models are trained with walk-forward validation as part of a scan. Nothing is shown here until real results exist."}
          </Empty>
        </Card>
      </>
    );

  const names = Object.keys(data.models);
  const oos = m?.out_of_sample ?? {};

  return (
    <>
      <PageTitle title="Model Monitor" sub={`Target: ${data.target}. Expanding-window walk-forward, retrained every 12 months with a one-month purge.`} right={<Seg options={names as string[]} value={model} onChange={setModel} labels={Object.fromEntries(names.map((n) => [n, titleCase(n)]))} />} />
      <Banner>
        {data.active_model ? (
          <>The <strong>{titleCase(data.active_model)}</strong> model passed out-of-sample validation and contributes to scores where its weight is above zero.</>
        ) : (
          <><strong className="font-semibold">No model is used in scores.</strong> Neither model showed a statistically reliable out-of-sample ranking ability (rank IC t-stat above 2), so their output is displayed for monitoring only.</>
        )}{" "}
        {data.note}
      </Banner>

      <div className="mt-3 grid gap-3 xl:grid-cols-3">
        <Card title="Models and versions" pad={false}>
          <table className="w-full">
            <thead><tr className="border-b border-line"><th className="th">Model</th><th className="th text-right" title="Out-of-sample rank information coefficient">OOS IC</th><th className="th text-right">t-stat</th><th className="th">Status</th></tr></thead>
            <tbody>
              {names.map((n) => {
                const o = data.models[n].out_of_sample;
                return (
                  <tr key={n} onClick={() => setModel(n)} className={`cursor-pointer border-b border-line/50 hover:bg-raised/50 ${n === model ? "bg-raised" : ""}`}>
                    <td className="td">{titleCase(n)}</td>
                    <td className={`td num text-right ${signClass(o.rank_ic_mean)}`}>{fmtNum(o.rank_ic_mean, 3)}</td>
                    <td className="td num text-right">{fmtNum(o.rank_ic_t)}</td>
                    <td className="td">{data.active_model === n ? <Tag tone="up">In score</Tag> : data.models[n].validated ? <Tag tone="accent">Validated</Tag> : <Tag>Not validated</Tag>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="p-4">
            <KV rows={[
              ["Version", data.version],
              ["Last trained", fmtDateTime(data.trained_at)],
              ["Trained through (labels)", data.trained_through ?? "—"],
              ["Training rows", fmtNum(data.n_training_rows, 0)],
              ["Walk-forward folds", data.folds.length],
              ["Features", data.features.length],
            ]} />
          </div>
        </Card>
        <Card title={`${titleCase(model)} · train vs validation vs out-of-sample`} pad={false}>
          <table className="w-full">
            <thead><tr className="border-b border-line"><th className="th">Metric</th><th className="th text-right">Train</th><th className="th text-right">Valid.</th><th className="th text-right" title="Out-of-sample">Unseen</th></tr></thead>
            <tbody>
              {[["AUC", "auc", 3], ["Accuracy", "accuracy", 3], ["Brier score", "brier", 3], ["Rank IC", "rank_ic_mean", 3]].map(([label, k, d]) => (
                <tr key={k as string} className="border-b border-line/50">
                  <td className="td text-dim">{label}</td>
                  <td className="td num text-right">{fmtNum(m?.train_mean?.[k as string], d as number)}</td>
                  <td className="td num text-right">{fmtNum(m?.validation_mean?.[k as string], d as number)}</td>
                  <td className="td num text-right font-semibold">{fmtNum(oos[k as string], d as number)}</td>
                </tr>
              ))}
              <tr><td className="td whitespace-normal text-dim" colSpan={3}>Top minus bottom decile, next 21 days</td><td className={`td num text-right ${signClass(oos.top_minus_bottom_decile_21d)}`}>{fmtPct(oos.top_minus_bottom_decile_21d, 2, true)}</td></tr>
            </tbody>
          </table>
          <p className="note px-4 py-3">Train and validation are averages over folds; out-of-sample pools {fmtNum(oos.n, 0)} predictions across {oos.n_dates} months that the model never saw. A gap between train and out-of-sample is the size of the overfit. AUC 0.5 and IC 0 mean no skill.</p>
        </Card>
        <Card title="Calibration of model scores">
          {calOption ? <EChart option={calOption} height={230} /> : <Empty title="Not enough predictions per bucket" />}
          <p className="note mt-1">Share of stocks that beat the universe median, by model score. This is calibration to &ldquo;beat the median&rdquo;, not a probability of making money.</p>
        </Card>
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-3">
        <Card title="Out-of-sample rank IC by month">{icOption ? <EChart option={icOption} height={240} /> : <Empty title="No data" />}</Card>
        <Card title="Feature importance" right={<Tag>{model === "logistic" ? "|coefficient|, colour = sign" : "permutation, last 12 months"}</Tag>}>{impOption ? <EChart option={impOption} height={240} /> : <Empty title="No data" />}</Card>
        <Card title="Prediction accuracy by year (out-of-sample)">{errOption ? <EChart option={errOption} height={240} /> : <Empty title="No data" />}</Card>
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-3">
        <Card title="Feature drift vs training data" pad={false}>
          <table className="w-full">
            <thead><tr className="border-b border-line"><th className="th">Feature</th><th className="th text-right">PSI</th><th className="th">Level</th></tr></thead>
            <tbody>
              {(data.drift ?? []).map((d: J) => (
                <tr key={d.feature} className="border-b border-line/50">
                  <td className="td">{titleCase(d.feature)}</td>
                  <td className="td num text-right">{fmtNum(d.psi, 3)}</td>
                  <td className="td">{d.level === "stable" ? <Tag tone="up">Stable</Tag> : d.level === "moderate" ? <Tag tone="warn">Moderate</Tag> : d.level === "significant" ? <Tag tone="down">Significant</Tag> : <Tag>n/a</Tag>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="note px-4 py-2">Population Stability Index of today&apos;s cross-section against the training distribution. Below 0.10 stable, above 0.25 significant drift.</p>
        </Card>
        <Card title={`Walk-forward folds · data from ${data.folds[0]?.train[0].slice(0, 7)}`} pad={false}>
          <div className="max-h-80 overflow-y-auto">
            <table className="w-full">
              <thead><tr className="border-b border-line"><th className="th">Fit to</th><th className="th">Validation to</th><th className="th">Test (unseen)</th><th className="th text-right">Test IC</th></tr></thead>
              <tbody>
                {data.folds.map((f: J, i: number) => (
                  <tr key={i} className="border-b border-line/50 text-[11.5px]">
                    <td className="td num text-dim">{f.train[1].slice(0, 7)}</td>
                    <td className="td num text-dim">{f.validation[1].slice(0, 7)}</td>
                    <td className="td num">{f.test[0].slice(2, 7)} to {f.test[1].slice(2, 7)}</td>
                    <td className={`td num text-right ${signClass(f.models[model]?.out_of_sample?.rank_ic_mean)}`}>{fmtNum(f.models[model]?.out_of_sample?.rank_ic_mean, 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card title={`Highest current model scores · ${data.as_of}`} pad={false} right={m?.validated ? <Tag tone="up">Validated</Tag> : <Tag tone="warn">Unvalidated</Tag>}>
          <div className="max-h-72 overflow-y-auto">
            <table className="w-full">
              <tbody>
                {(m?.current_predictions ?? []).map((p: J) => (
                  <tr key={p.symbol} className="border-b border-line/50"><td className="td"><SymbolLink symbol={p.symbol} /></td><td className="td num text-right">{fmtNum(p.model_score, 3)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="note border-t border-line px-4 py-2">{m?.validated ? "Scores rank stocks; they are not probabilities of profit." : "This model failed validation. These scores are shown for monitoring and are not used anywhere else."}</p>
        </Card>
      </div>
    </>
  );
}
