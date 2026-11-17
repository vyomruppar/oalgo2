"use client";

import { useEffect, useState } from "react";
import { Banner, Card, ErrorBox, Loading, PageTitle, Tag, useApi } from "@/components/ui";
import { send, type J } from "@/lib/api";
import { fmtNum, timeAgo, titleCase } from "@/lib/format";

const SCREEN_FIELDS: { key: string; label: string; step: number; scale?: number; unit?: string }[] = [
  { key: "min_price", label: "Minimum share price", step: 1, unit: "$" },
  { key: "min_market_cap", label: "Minimum market cap", step: 50, scale: 1e6, unit: "$M" },
  { key: "min_adv_dollar", label: "Minimum 63-day avg dollar volume", step: 1, scale: 1e6, unit: "$M" },
  { key: "min_history_bars", label: "Minimum trading history", step: 21, unit: "days" },
  { key: "max_volatility", label: "Maximum 1-year volatility", step: 5, scale: 0.01, unit: "%" },
  { key: "max_stale_bars", label: "Maximum age of last price bar", step: 1, unit: "business days" },
];
const SECTORS = ["Technology", "Health Care", "Financials", "Industrials", "Consumer Discretionary", "Consumer Staples", "Energy", "Materials", "Utilities", "Communication Services", "Real Estate", "Other", "Unknown"];

export default function Settings() {
  const { data, error, mutate } = useApi("/api/config");
  const prov = useApi("/api/providers", 60000);
  const [screen, setScreen] = useState<J | null>(null);
  const [score, setScore] = useState<J | null>(null);
  const [size, setSize] = useState(300);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (data && !screen) {
      setScreen(data.screen);
      setScore(data.score);
      setSize(data.scan_max_symbols);
    }
  }, [data, screen]);

  if (error && !data) return <ErrorBox error={error} />;
  if (!data || !screen || !score) return <Loading rows={8} />;

  const total = Object.values(score.weights as Record<string, number>).reduce((a, b) => a + b, 0);
  const dirty = JSON.stringify(screen) !== JSON.stringify(data.screen) || JSON.stringify(score) !== JSON.stringify(data.score) || size !== data.scan_max_symbols;

  const save = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await send("PUT", "/api/config", { screen, score, scan_max_symbols: size, rescore: true });
      await mutate();
      setMsg({ ok: true, text: r.rescore_started ? "Saved. Re-screening and re-scoring from stored data now; watch the status bar." : "Saved. A scan is already running, so the new settings apply on the next one." });
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };
  const revert = () => {
    setScreen(data.screen);
    setScore(data.score);
    setSize(data.scan_max_symbols);
    setMsg(null);
  };

  return (
    <>
      <PageTitle
        title="Settings"
        sub="Screening thresholds, score weights and signal thresholds. Saving re-screens and re-scores every scanned stock from stored data, without downloading anything."
        right={<div className="flex items-center gap-2"><button className="btn" disabled={!dirty || busy} onClick={revert}>Discard changes</button><button className="btn btn-primary" disabled={!dirty || busy || total <= 0} onClick={save}>Save and re-score</button></div>}
      />
      {msg && <div className={`mb-3 rounded border px-3 py-2 text-xs ${msg.ok ? "border-up/40 bg-up/5 text-up" : "border-down/40 bg-down/5 text-down"}`}>{msg.text}</div>}

      <div className="grid gap-3 xl:grid-cols-3">
        <Card title="Stock screener">
          <div className="space-y-3">
            {SCREEN_FIELDS.map((f) => {
              const sc = f.scale ?? 1;
              return (
                <label key={f.key} className="flex items-center justify-between gap-3 text-[12.5px]" title={data.screen_schema[f.key]}>
                  <span className="text-dim">{f.label}</span>
                  <span className="flex items-center gap-1.5">
                    <input type="number" min={0} step={f.step} className="input num w-24 text-right" value={+(screen[f.key] / sc).toFixed(4)} onChange={(e) => setScreen({ ...screen, [f.key]: Math.max(0, Number(e.target.value)) * sc })} />
                    <span className="w-20 text-[11px] text-faint">{f.unit}</span>
                  </span>
                </label>
              );
            })}
            <label className="flex items-center justify-between gap-3 text-[12.5px]">
              <span className="text-dim">Require recent SEC fundamentals</span>
              <input type="checkbox" checked={screen.require_fundamentals} onChange={(e) => setScreen({ ...screen, require_fundamentals: e.target.checked })} className="accent-[#d6a85c]" />
            </label>
            <div>
              <div className="mb-1.5 text-[12.5px] text-dim">Excluded sectors</div>
              <div className="flex flex-wrap gap-1.5">
                {SECTORS.map((s) => {
                  const on = screen.excluded_sectors.includes(s);
                  return (
                    <button key={s} type="button" aria-pressed={on} onClick={() => setScreen({ ...screen, excluded_sectors: on ? screen.excluded_sectors.filter((x: string) => x !== s) : [...screen.excluded_sectors, s] })} className={`rounded-sm border px-1.5 py-[2px] text-[11px] ${on ? "border-down/50 bg-down/10 text-down" : "border-line text-dim hover:text-ink"}`}>
                      {s}
                    </button>
                  );
                })}
              </div>
            </div>
            <label className="flex items-center justify-between gap-3 border-t border-line pt-3 text-[12.5px]">
              <span className="text-dim">Stocks per scan (most liquid first)</span>
              <input type="number" min={20} max={6000} step={50} className="input num w-24 text-right" value={size} onChange={(e) => setSize(Math.max(20, Math.min(6000, Number(e.target.value))))} />
            </label>
            <p className="note">The free price source is rate limited to about two requests a second, and each stock needs one price and two SEC requests. 300 stocks take roughly ten minutes on a first scan; the scan size takes effect on the next full scan.</p>
          </div>
        </Card>

        <Card title="Score weights" right={<span className="num text-[11px] text-faint">total {fmtNum(total, 0)}</span>}>
          <div className="space-y-2.5">
            {Object.keys(data.component_labels).map((k) => {
              const w = score.weights[k] ?? 0;
              return (
                <div key={k}>
                  <div className="flex items-baseline justify-between gap-3 text-[12px]">
                    <label htmlFor={`w-${k}`} className="text-dim" title={data.component_labels[k]}>{titleCase(k)}</label>
                    <span className="num">{fmtNum(w, 0)} <span className="text-faint">({total > 0 ? ((100 * w) / total).toFixed(0) : 0}%)</span></span>
                  </div>
                  <input id={`w-${k}`} type="range" min={0} max={40} step={1} value={w} onChange={(e) => setScore({ ...score, weights: { ...score.weights, [k]: Number(e.target.value) } })} className="w-full accent-[#d6a85c]" />
                </div>
              );
            })}
          </div>
          <Banner tone="info">{data.weights_note} Weights are relative; only their proportions matter. The machine-learning weight has no effect unless a model has passed out-of-sample validation.</Banner>
        </Card>

        <Card title="Signal thresholds">
          <div className="space-y-3">
            {[["strong_buy", "Strong buy at or above"], ["buy", "Buy at or above"], ["sell", "Sell at or below"], ["score_change_alert", "Alert when score moves by"]].map(([k, label]) => (
              <label key={k} className="flex items-center justify-between gap-3 text-[12.5px]">
                <span className="text-dim">{label}</span>
                <span className="flex items-center gap-1.5"><input type="number" min={0} max={100} step={1} className="input num w-20 text-right" value={score[k]} onChange={(e) => setScore({ ...score, [k]: Number(e.target.value) })} /><span className="w-10 text-[11px] text-faint">points</span></span>
              </label>
            ))}
          </div>
          <div className="mt-4 space-y-1.5 text-[12px] leading-relaxed text-dim">
            <p>A score above the buy threshold is not enough on its own. The signal is held at <span className="text-accent">Watchlist</span> when the price is below its 200-day average, the market regime is risk-off, data quality is C, or a severe financial red flag is present.</p>
            <p><span className="text-up">Strong buy</span> also needs data quality A, a risk-on regime and no warnings at all.</p>
            <p>Stocks with too little data to score are labelled <span className="text-ink">No action</span>.</p>
          </div>
        </Card>
      </div>

      <Card title="Data providers" className="mt-3" pad={false}>
        {!prov.data ? <Loading /> : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead><tr className="border-b border-line">{["Provider", "Used for", "Freshness", "Cost", "Status", "Last success", "Requests ok / failed", "Limitations"].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
              <tbody>
                {prov.data.map((p: J) => (
                  <tr key={p.key} className="border-b border-line/50 align-top text-[12px]">
                    <td className="td font-medium">{p.name}</td>
                    <td className="td text-dim">{p.use}</td>
                    <td className="td text-dim">{p.freshness}</td>
                    <td className="td text-dim">{p.cost}</td>
                    <td className="td">{p.status === "ok" ? <Tag tone="up">OK</Tag> : p.status === "failing" ? <Tag tone="down">Failing</Tag> : p.status === "degraded" ? <Tag tone="warn">Degraded</Tag> : <Tag>Unknown</Tag>}</td>
                    <td className="td num text-dim">{p.last_success ? timeAgo(p.last_success) : "never"}</td>
                    <td className="td num text-dim">{p.success_count} / {p.failure_count}</td>
                    <td className="td whitespace-normal text-faint" style={{ minWidth: 280 }}>{p.limits}{p.last_error ? ` Last error: ${p.last_error}` : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="note border-t border-line px-4 py-2">All sources are free and none is real-time. Paid providers (Financial Modeling Prep, Polygon) would add delisted-stock history, analyst estimates and an earnings calendar; see docs/data-providers.md.</p>
      </Card>
    </>
  );
}
