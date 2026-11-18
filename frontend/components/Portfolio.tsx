"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import EChart, { C, baseOption, timeAxis, valueAxis, zoom } from "./EChart";
import { Card, Empty, Loading, ScoreBar, Seg, SentimentBadge, SignalChip, Sparkline, useApi } from "./ui";
import { READ_ONLY, send, SNAPSHOT, type J } from "@/lib/api";
import { fmtMoney, fmtNum, fmtPct, signClass } from "@/lib/format";

const RANGES = ["1m", "3m", "6m", "1y", "2y", "all"] as const;

/** Value of the recorded holdings over time, against the money put in and the same dollars in SPY. */
export function PortfolioTracker({ height = 260, compact = false }: { height?: number; compact?: boolean }) {
  const [range, setRange] = useState<(typeof RANGES)[number]>("1y");
  const [mode, setMode] = useState<"value" | "gain">("value");
  const { data } = useApi(`/api/holdings/history?range=${range}`, 120000);

  const option = useMemo(() => {
    if (!data || data.empty) return null;
    const rows: J[] = data.series;
    const pct = mode === "gain";
    const val = (r: J, i: number) => (pct ? (r[2] > 0 ? ((r[i] + (i === 1 ? r[3] : 0)) / r[2] - 1) * 100 : null) : r[i]);
    return baseOption({
      xAxis: timeAxis(),
      yAxis: valueAxis({ axisLabel: { color: C.faint, fontSize: 10.5, formatter: (v: number) => (pct ? `${v.toFixed(0)}%` : v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : `$${(v / 1e3).toFixed(0)}k`) } }),
      dataZoom: compact ? [{ type: "inside" }] : zoom(),
      grid: { left: 52, right: 14, top: 30, bottom: compact ? 22 : 44 },
      tooltip: { trigger: "axis", valueFormatter: (v) => (v == null ? "n/a" : pct ? `${Number(v).toFixed(2)}%` : fmtMoney(Number(v), 0)) },
      series: [
        {
          name: pct ? "Your holdings (incl. dividends)" : "Market value",
          type: "line",
          showSymbol: false,
          smooth: 0.15,
          lineStyle: { width: 2.2, color: C.accent, shadowColor: "rgba(139,124,255,0.7)", shadowBlur: 12 },
          itemStyle: { color: C.accent },
          areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: "rgba(139,124,255,0.38)" }, { offset: 1, color: "rgba(139,124,255,0)" }] } as never },
          data: rows.map((r) => [r[0], val(r, 1)]),
        },
        ...(pct ? [] : [{ name: "Amount invested", type: "line" as const, step: "end" as const, showSymbol: false, lineStyle: { width: 1.2, type: "dashed" as const, color: C.dim }, itemStyle: { color: C.dim }, data: rows.map((r) => [r[0], r[2]]) }]),
        { name: pct ? "Same dollars in SPY" : "Same dollars in SPY", type: "line", showSymbol: false, lineStyle: { width: 1.3, color: "#5ec8ff" }, itemStyle: { color: "#5ec8ff" }, data: rows.map((r) => [r[0], r[4] == null ? null : val(r, 4)]) },
      ],
    });
  }, [data, mode, compact]);

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <Seg options={["value", "gain"] as const} value={mode} onChange={setMode} labels={{ value: "Value", gain: "Return %" }} />
        <Seg options={RANGES} value={range} onChange={setRange} labels={{ all: "All" }} />
      </div>
      {!data ? <Loading /> : data.empty ? <Empty title="Nothing to chart yet">{data.note ?? "Add the stocks you own to see their value over time."}</Empty> : option && <EChart option={option} height={height} />}
      {data && !data.empty && !compact && (
        <p className="note mt-2">
          Since {data.start}: holdings {fmtPct(data.total_return_pct, 1, true)} including {fmtMoney(data.dividends_received, 0)} of dividends, against {fmtPct(data.benchmark_return_pct, 1, true)} for the same dollars in SPY. {data.note}
        </p>
      )}
    </div>
  );
}

export function HoldingTile({ p }: { p: J }) {
  return (
    <Link href={`/stocks/${p.symbol}`} className="card group block min-w-[210px] flex-1 overflow-hidden p-3.5 transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/70 hover:bg-raised/50">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[15px] font-semibold leading-tight">{p.symbol}</div>
          <div className="truncate text-[11px] text-faint">{(p.company ?? "").replace(/ - .*$| Common Stock.*$| Class .*$/i, "")}</div>
        </div>
        <SignalChip signal={p.signal} />
      </div>
      <div className="mt-2 flex items-end justify-between gap-2">
        <div>
          <div className="num text-[17px] font-medium">{fmtMoney(p.price)}</div>
          <div className={`num text-[11.5px] ${signClass(p.day_change_pct)}`}>{fmtPct(p.day_change_pct, 2, true)} last session</div>
        </div>
        <Sparkline data={p.spark} />
      </div>
      <dl className="num mt-2.5 grid grid-cols-3 gap-1 border-t border-line/40 pt-2 text-[11.5px]">
        <div>
          <dt className="text-faint">Value</dt>
          <dd>{fmtMoney(p.value, 0)}</dd>
        </div>
        <div>
          <dt className="text-faint">Gain</dt>
          <dd className={signClass(p.gain_pct)}>{fmtPct(p.gain_pct, 1, true)}</dd>
        </div>
        <div>
          <dt className="text-faint">Weight</dt>
          <dd>{fmtPct(p.weight, 0)}</dd>
        </div>
      </dl>
      <div className="mt-2 flex items-center justify-between gap-2">
        {p.score != null ? <ScoreBar value={p.score} width={56} /> : <span className="text-[11px] text-faint">{p.researched ? "not scored" : "not scanned yet"}</span>}
        <SentimentBadge s={p.sentiment} compact />
      </div>
    </Link>
  );
}

const today = () => new Date().toISOString().slice(0, 10);

/** Add, edit, delete and import the lots the user owns. Bookkeeping only: nothing here places an order. */
export function HoldingsEditor({ lots, onChange }: { lots: J[]; onChange: () => void }) {
  const [form, setForm] = useState({ symbol: "", shares: "", cost: "", purchase_date: today(), note: "" });
  const [editing, setEditing] = useState<number | null>(null);
  const [csv, setCsv] = useState("");
  const [showCsv, setShowCsv] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState<number | null>(null);

  const run = async (fn: () => Promise<unknown>, okText: string) => {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
      setMsg({ ok: true, text: okText });
      onChange();
      return true;
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) });
      return false;
    } finally {
      setBusy(false);
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const body = { shares: Number(form.shares), cost: Number(form.cost), purchase_date: form.purchase_date, note: form.note || null };
    if (!(body.shares > 0) || !(body.cost >= 0) || form.cost === "") return setMsg({ ok: false, text: "Enter the number of shares and the price you paid per share." });
    const ok = editing != null
      ? await run(() => send("PUT", `/api/holdings/${editing}`, body), "Holding updated.")
      : await run(() => send("POST", "/api/holdings", { symbol: form.symbol, ...body }), `${form.symbol.toUpperCase()} added to your holdings.`);
    if (ok) {
      setForm({ symbol: "", shares: "", cost: "", purchase_date: today(), note: "" });
      setEditing(null);
    }
  };

  const edit = (l: J) => {
    setEditing(l.id);
    setForm({ symbol: l.symbol, shares: String(l.shares), cost: String(l.cost), purchase_date: l.purchase_date, note: l.note ?? "" });
  };

  return (
    <Card title={editing != null ? `Edit ${form.symbol} lot` : "Add a holding"} right={<button className="btn" type="button" onClick={() => setShowCsv((s) => !s)}>{showCsv ? "Hide import" : "Import CSV"}</button>}>
      <form onSubmit={submit} className="grid grid-cols-2 gap-2 md:grid-cols-[1fr_1fr_1fr_1.2fr_1.6fr_auto]">
        <label className="text-[11.5px] text-dim">
          Ticker
          <input className="input mt-1 w-full uppercase" required disabled={editing != null} value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })} placeholder="AAPL" />
        </label>
        <label className="text-[11.5px] text-dim">
          Shares
          <input className="input num mt-1 w-full" required inputMode="decimal" value={form.shares} onChange={(e) => setForm({ ...form, shares: e.target.value.replace(/[^0-9.]/g, "") })} placeholder="10" />
        </label>
        <label className="text-[11.5px] text-dim">
          Price paid per share
          <input className="input num mt-1 w-full" required inputMode="decimal" value={form.cost} onChange={(e) => setForm({ ...form, cost: e.target.value.replace(/[^0-9.]/g, "") })} placeholder="150.00" />
        </label>
        <label className="text-[11.5px] text-dim">
          Purchase date
          <input type="date" className="input num mt-1 w-full" required max={today()} value={form.purchase_date} onChange={(e) => setForm({ ...form, purchase_date: e.target.value })} />
        </label>
        <label className="text-[11.5px] text-dim">
          Note (optional)
          <input className="input mt-1 w-full" maxLength={300} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
        </label>
        <div className="col-span-2 flex items-end gap-2 md:col-span-1">
          <button className="btn btn-primary" disabled={busy || SNAPSHOT} title={SNAPSHOT ? READ_ONLY : undefined} type="submit">{editing != null ? "Save changes" : "Add holding"}</button>
          {editing != null && <button className="btn" type="button" onClick={() => { setEditing(null); setForm({ symbol: "", shares: "", cost: "", purchase_date: today(), note: "" }); }}>Cancel</button>}
        </div>
      </form>
      {msg && <div className={`mt-2 text-[12px] ${msg.ok ? "text-up" : "text-down"}`} role="status">{msg.text}</div>}
      {showCsv && (
        <div className="mt-3 border-t border-line/40 pt-3">
          <label className="text-[11.5px] text-dim">
            One lot per line: <span className="num text-ink">ticker,shares,price paid,YYYY-MM-DD,note</span>. Nothing is saved if any line has a problem.
            <textarea className="input num mt-1 h-24 w-full" value={csv} onChange={(e) => setCsv(e.target.value)} placeholder={"AAPL,10,150.25,2024-03-14\nMSFT,4,410,2025-01-09,retirement account"} />
          </label>
          <button className="btn mt-2" disabled={busy || !csv.trim() || SNAPSHOT} title={SNAPSHOT ? READ_ONLY : undefined} type="button" onClick={async () => { if (await run(() => send("POST", "/api/holdings/import", { csv }), "Holdings imported.")) setCsv(""); }}>Import holdings</button>
        </div>
      )}
      {lots.length > 0 && (
        <div className="mt-3 overflow-x-auto border-t border-line/40 pt-2">
          <table className="w-full">
            <thead><tr>{["Ticker", "Shares", "Price paid", "Cost", "Purchased", "Note", ""].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
            <tbody>
              {lots.map((l) => (
                <tr key={l.id} className={`border-t border-line/30 ${editing === l.id ? "bg-accent/10" : ""}`}>
                  <td className="td font-semibold">{l.symbol}</td>
                  <td className="td num">{fmtNum(l.shares, l.shares % 1 ? 3 : 0)}</td>
                  <td className="td num">{fmtMoney(l.cost)}</td>
                  <td className="td num text-dim">{fmtMoney(l.shares * l.cost, 0)}</td>
                  <td className="td num text-dim">{l.purchase_date}</td>
                  <td className="td max-w-[220px] truncate text-faint">{l.note}</td>
                  <td className="td text-right">
                    {SNAPSHOT ? null : removing === l.id ? (
                      <>
                        <button className="mr-3 text-[12px] font-semibold text-down" type="button" onClick={() => { setRemoving(null); run(() => send("DELETE", `/api/holdings/${l.id}`), "Holding removed."); }}>Confirm remove</button>
                        <button className="text-[12px] text-dim hover:text-ink" type="button" onClick={() => setRemoving(null)}>Keep</button>
                      </>
                    ) : (
                      <>
                        <button className="mr-3 text-[12px] text-dim hover:text-accent" type="button" onClick={() => edit(l)}>Edit</button>
                        <button className="text-[12px] text-dim hover:text-down" type="button" onClick={() => setRemoving(l.id)}>Remove</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {SNAPSHOT && <p className="mt-2 text-[12px] text-warn">These are sample holdings in a read-only snapshot. To track your own, run the app on your computer.</p>}
      <p className="note mt-2">This is a record of what you already own. Adding or removing a holding here never buys or sells anything.</p>
    </Card>
  );
}
