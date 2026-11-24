"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import CandleChart, { OVERLAYS } from "@/components/CandleChart";
import EChart, { C, baseOption, catAxis, timeAxis, valueAxis, zoom } from "@/components/EChart";
import { Banner, Card, Empty, ErrorBox, KV, Loading, Seg, SignalChip, Tag, useApi } from "@/components/ui";
import NewsFeed from "@/components/NewsFeed";
import { PriceSource } from "@/components/ui";
import { useQuotes } from "@/lib/quotes";
import { ApiError, send, SNAPSHOT, type J } from "@/lib/api";
import { fmtCompact, fmtDateTime, fmtMoney, fmtNum, fmtPct, scoreColor, signClass, titleCase } from "@/lib/format";

// the snapshot stores two years of prices per stock
const RANGES = (SNAPSHOT ? ["3m", "6m", "1y", "2y"] : ["3m", "6m", "1y", "2y", "5y", "max"]) as readonly ("3m" | "6m" | "1y" | "2y" | "5y" | "max")[];
const SUB = ["rsi_14", "macd", "mfi_14", "obv", "atr_14", "rel_strength", "rvol_21"] as const;
const SUB_LABEL: Record<string, string> = { rsi_14: "RSI 14", macd: "MACD", mfi_14: "Money Flow 14", obv: "On-balance volume", atr_14: "ATR 14", rel_strength: "Rel. strength vs SPY", rvol_21: "Realised vol 21d" };

function PaperTicket({ symbol, price, eligible }: { symbol: string; price: number | null; eligible: boolean }) {
  const size = useApi(price && !SNAPSHOT ? `/api/portfolio/size/${symbol}` : null);
  const [qty, setQty] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const place = async (side: "BUY" | "SELL") => {
    const n = Number(qty || size.data?.shares);
    if (!n || n <= 0) return setMsg({ ok: false, text: "Enter a share quantity." });
    setBusy(true);
    try {
      await send("POST", "/api/portfolio/orders", { symbol, side, quantity: n, note: "from research page" });
      setMsg({ ok: true, text: `Paper ${side.toLowerCase()} of ${n} shares recorded. It fills at the next session's open.` });
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };
  if (SNAPSHOT) return <Empty title="Paper trading is off here">Paper trading needs the app running on your computer.</Empty>;
  if (!eligible || !price) return <Empty title="Paper trading unavailable">Only verified, scanned NYSE and NASDAQ listings can be paper traded.</Empty>;
  return (
    <div className="space-y-3 text-[12.5px]">
      {size.data && (
        <KV rows={[
          ["Suggested size (1% monthly risk budget)", `${fmtNum(size.data.shares, 0)} sh · ${fmtPct(size.data.weight)} of equity`],
          ["Binding constraint", size.data.binding],
          ["Paper equity", fmtMoney(size.data.equity, 0)],
        ]} />
      )}
      <div className="flex items-center gap-2">
        <input className="input w-28" inputMode="numeric" placeholder={size.data ? String(size.data.shares) : "Shares"} value={qty} onChange={(e) => setQty(e.target.value.replace(/[^0-9.]/g, ""))} aria-label="Share quantity" />
        <button className="btn border-up/40 text-up" disabled={busy} onClick={() => place("BUY")}>Paper buy</button>
        <button className="btn border-down/40 text-down" disabled={busy} onClick={() => place("SELL")}>Paper sell</button>
      </div>
      {msg && <div className={`text-[11.5px] ${msg.ok ? "text-up" : "text-down"}`}>{msg.text} {msg.ok && <Link href="/portfolio" className="underline">Open portfolio</Link>}</div>}
      <p className="note">Hypothetical only. No order leaves this application.</p>
    </div>
  );
}

export default function StockPage() {
  const { symbol: raw } = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(raw).toUpperCase();
  const [range, setRange] = useState<(typeof RANGES)[number]>("1y");
  const [mode, setMode] = useState<"candles" | "line" | "area">("candles");
  const [active, setActive] = useState<string[]>(["sma_50", "sma_200"]);
  const [sub, setSub] = useState<(typeof SUB)[number]>("rsi_14");
  const [showData, setShowData] = useState(false);
  const info = useApi(`/api/stocks/${symbol}`);
  const prices = useApi(info.data?.researched ? `/api/stocks/${symbol}/prices?range=${range}` : null);
  const fund = useApi(info.data ? `/api/stocks/${symbol}/fundamentals` : null);
  const quotes = useQuotes([symbol]);
  const lq = quotes?.quotes?.[symbol];

  const p = prices.data;
  const subOption = useMemo(() => {
    if (!p) return null;
    const ind = p.indicators;
    const line = (name: string, key: string, color?: string) => ({ name, type: "line" as const, showSymbol: false, lineStyle: { width: 1.3 }, color, data: p.dates.map((d: string, i: number) => [d, ind[key]?.[i] ?? null]) });
    let series: J[] = [line(SUB_LABEL[sub], sub, C.accent)];
    let marks: number[] = [];
    if (sub === "macd") series = [line("MACD", "macd", C.accent), line("Signal", "macd_signal", "#5ec8ff"), { name: "Histogram", type: "bar", data: p.dates.map((d: string, i: number) => ({ value: [d, ind.macd_hist?.[i] ?? null], itemStyle: { color: (ind.macd_hist?.[i] ?? 0) >= 0 ? C.up : C.down, opacity: 0.6 } })) }];
    if (sub === "rsi_14") marks = [30, 70];
    if (sub === "mfi_14") marks = [20, 80];
    if (marks.length) series[0].markLine = { symbol: "none", silent: true, lineStyle: { color: C.faint, type: "dashed" }, label: { color: C.faint, fontSize: 10 }, data: marks.map((y) => ({ yAxis: y })) };
    return baseOption({ xAxis: timeAxis(), yAxis: valueAxis(marks.length ? { min: 0, max: 100, scale: false } : {}), dataZoom: zoom(), grid: { left: 52, right: 16, top: 26, bottom: 44 }, series });
  }, [p, sub]);

  const res = info.data?.result;
  const compOption = useMemo(() => {
    const comps: J[] = (res?.components ?? []).filter((c: J) => c.weight > 0);
    if (!comps.length) return null;
    const rows = [...comps].reverse();
    return baseOption({
      grid: { left: 150, right: 44, top: 4, bottom: 18 },
      legend: { show: false },
      tooltip: { trigger: "item", formatter: (x: J) => { const c = rows[x.dataIndex]; return `${c.label}<br/>percentile ${c.component_score == null ? "missing" : c.component_score.toFixed(0)} · weight ${c.weight} · adds ${c.contribution == null ? "0" : c.contribution.toFixed(1)} points`; } },
      xAxis: valueAxis({ min: 0, max: 100, scale: false }),
      yAxis: catAxis(rows.map((c) => titleCase(c.component)), { axisLine: { show: false } }),
      series: [{ type: "bar", barWidth: 10, data: rows.map((c) => ({ value: c.component_score ?? 0, itemStyle: { color: c.component_score == null ? C.line : scoreColor(c.component_score), borderRadius: 2 } })), label: { show: true, position: "right", color: C.dim, fontSize: 10.5, formatter: (x: J) => (rows[x.dataIndex].component_score == null ? "missing" : `+${rows[x.dataIndex].contribution.toFixed(1)}`) } }],
    });
  }, [res]);

  const histOption = useMemo(() => {
    const h: J[] = info.data?.score_history ?? [];
    if (h.length < 2) return null;
    return baseOption({ grid: { left: 36, right: 12, top: 10, bottom: 22 }, legend: { show: false }, xAxis: timeAxis(), yAxis: valueAxis({ min: 0, max: 100, scale: false }), series: [{ name: "Score", type: "line", step: "end", showSymbol: true, symbolSize: 4, color: C.accent, data: h.map((x) => [x.as_of, x.score]) }] });
  }, [info.data]);

  if (info.error) {
    const nf = info.error instanceof ApiError && info.error.status === 404;
    return nf ? (
      <Card><Empty title={SNAPSHOT ? `${symbol} was not part of the last scan` : `${symbol} is not in the verified NYSE/NASDAQ directory`}>{SNAPSHOT ? "Pages exist for the stocks in the last scan and the ones you own. Add it as a holding, or raise the scan size in Settings, and it appears after the next update. " : ""}This platform only researches securities whose listing on the NYSE or NASDAQ can be verified. OTC and other venues are excluded. <Link className="underline" href="/stocks">Back to the explorer</Link></Empty></Card>
    ) : <ErrorBox error={info.error} />;
  }
  if (!info.data) return <Loading rows={8} />;
  const sec = info.data.security;
  const f = res?.fundamentals ?? {};
  const toggle = (k: string) => setActive((a) => (a.includes(k) ? a.filter((x) => x !== k) : [...a, k]));

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="text-[11px] text-faint"><Link href="/stocks" className="hover:text-accent">Stock Explorer</Link> / {symbol}</div>
          <h1 className="mt-0.5 flex flex-wrap items-center gap-3 text-lg font-semibold tracking-tight">
            <span className="num">{symbol}</span>
            <span className="font-normal text-dim">{sec.name.replace(/ - .*$| Common Stock.*$/i, "")}</span>
            {res?.signal !== undefined && <SignalChip signal={res.signal} />}
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[11.5px] text-dim">
            <Tag tone={sec.eligible ? "up" : "down"}>{sec.exchange} · {sec.eligible ? "verified listing" : "excluded"}</Tag>
            <span>{sec.sector ?? "Sector unknown"}{sec.industry ? ` · ${sec.industry}` : ""}</span>
            <span className="text-faint">Listing verified from {sec.listing_source}, file dated {fmtDateTime(sec.listing_as_of)}</span>
          </div>
        </div>
        {res?.price != null && (
          <div className="text-right">
            <div className="num text-2xl font-medium">{fmtMoney(lq ? lq.price : res.price)}</div>
            {lq && <div className={`num text-[13px] ${signClass(lq.change_pct)}`}>{fmtMoney(lq.change)} ({fmtPct(lq.change_pct, 2, true)}) {lq.market_open ? "today" : "last session"}</div>}
            <div className="mt-1"><PriceSource live={Boolean(lq)} marketOpen={lq?.market_open} time={lq?.time} date={res.price_date} /></div>
            {lq && <div className="mt-1 text-[11px] text-faint">Score and signal use the stored close of {res.price_date}.</div>}
          </div>
        )}
      </div>

      {!sec.eligible && <Banner>This security is excluded from research: {sec.exclusion_reason}.</Banner>}
      {sec.eligible && !info.data.researched && <Banner tone="info">This listing is verified but has not been scanned yet. Scans cover the most liquid stocks first; raise the scan size in Settings to include it.</Banner>}

      {res && (
        <>
          <div className="grid gap-3 xl:grid-cols-3">
            <Card title="Price and volume" className="xl:col-span-2" right={
              <div className="flex flex-wrap items-center gap-2">
                <Seg options={["candles", "line", "area"] as const} value={mode} onChange={setMode} labels={{ candles: "Candles", line: "Line", area: "Area" }} />
                <Seg options={RANGES} value={range} onChange={setRange} />
              </div>
            }>
              {prices.error ? <ErrorBox error={prices.error} /> : !p ? <Loading rows={6} /> : (
                <>
                  {p.stale && <Banner>The last stored bar ({p.last_bar}) is {p.last_bar_age_business_days} business days old. This chart is stale.</Banner>}
                  <CandleChart dates={p.dates} ohlcv={p.ohlcv} indicators={p.indicators} active={active} mode={mode} height={380} />
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {OVERLAYS.map((o) => (
                      <button key={o.key} type="button" aria-pressed={active.includes(o.key)} onClick={() => toggle(o.key)} className={`rounded-sm border px-1.5 py-[2px] text-[10.5px] ${active.includes(o.key) ? "border-transparent text-bg" : "border-line text-dim hover:text-ink"}`} style={active.includes(o.key) ? { background: o.color } : undefined}>
                        {o.label}
                      </button>
                    ))}
                  </div>
                  <div className="mt-3 flex items-center justify-between">
                    <Seg options={SUB} value={sub} onChange={setSub} labels={SUB_LABEL} />
                    <button className="btn" onClick={() => setShowData((s) => !s)}>{showData ? "Hide data" : "Inspect data"}</button>
                  </div>
                  {subOption && <EChart option={subOption} height={190} />}
                  <p className="note">{p.freshness_note} Source: {p.source}. {p.indicator_notes.vwap_20}</p>
                  {showData && (
                    <div className="mt-2 max-h-64 overflow-auto rounded border border-line">
                      <table className="w-full">
                        <thead className="sticky top-0 bg-panel"><tr>{["Date", "Open", "High", "Low", "Close", "Volume", "RSI", "MACD", "ATR"].map((h) => <th key={h} className="th text-right first:text-left">{h}</th>)}</tr></thead>
                        <tbody>
                          {[...p.dates.keys()].reverse().slice(0, 120).map((i: number) => (
                            <tr key={p.dates[i]} className="border-t border-line/40 text-[11.5px]">
                              <td className="td num">{p.dates[i]}</td>
                              {(["open", "high", "low", "close"] as const).map((k) => <td key={k} className="td num text-right">{fmtNum(p.ohlcv[k][i])}</td>)}
                              <td className="td num text-right text-dim">{fmtCompact(p.ohlcv.volume[i])}</td>
                              <td className="td num text-right text-dim">{fmtNum(p.indicators.rsi_14?.[i], 1)}</td>
                              <td className="td num text-right text-dim">{fmtNum(p.indicators.macd?.[i])}</td>
                              <td className="td num text-right text-dim">{fmtNum(p.indicators.atr_14?.[i])}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </Card>

            <div className="space-y-3">
              <Card title="Research score" right={<span className="text-[11px] text-faint">data quality {res.data_quality ?? "—"}</span>}>
                {res.score == null ? (
                  <Empty title="Not scored">{(res.reasons ?? []).join(" ")}</Empty>
                ) : (
                  <>
                    <div className="flex items-baseline gap-2">
                      <span className="num text-4xl font-medium" style={{ color: scoreColor(res.score) }}>{fmtNum(res.score, 0)}</span>
                      <span className="text-dim">/ 100</span>
                    </div>
                    <p className="note mt-1">{res.score_note}</p>
                    {compOption && <EChart option={compOption} height={Math.max(150, res.components.filter((c: J) => c.weight > 0).length * 22)} />}
                    <p className="note">Bars show each component&apos;s percentile; labels show the points it adds. Missing components have their weight redistributed.</p>
                  </>
                )}
              </Card>
              <Card title="Paper trade"><PaperTicket symbol={symbol} price={res.price} eligible={sec.eligible && res.screen_pass} /></Card>
            </div>
          </div>

          {res.score != null && (
            <div className="mt-3 grid gap-3 xl:grid-cols-3">
              <Card title="Why this signal">
                <div className="space-y-3 text-[12.5px] leading-relaxed">
                  <div>
                    <div className="mb-1 sub !text-up">Supporting</div>
                    <ul className="list-disc space-y-0.5 pl-4">{res.reasons.map((r: string) => <li key={r}>{r}</li>)}</ul>
                  </div>
                  {res.weaknesses?.length > 0 && (
                    <div>
                      <div className="mb-1 sub !text-down">Against</div>
                      <ul className="list-disc space-y-0.5 pl-4 text-dim">{res.weaknesses.map((r: string) => <li key={r}>{r}</li>)}</ul>
                    </div>
                  )}
                  {res.gates?.length > 0 && (
                    <div>
                      <div className="mb-1 sub !text-accent">Why not a stronger signal</div>
                      <ul className="list-disc space-y-0.5 pl-4 text-dim">{res.gates.map((r: string) => <li key={r}>{r}</li>)}</ul>
                    </div>
                  )}
                  <div>
                    <div className="mb-1 sub">Technical checks</div>
                    <ul className="space-y-0.5">
                      {(res.technical_checks ?? []).map((c: J) => (
                        <li key={c.name} className="flex justify-between gap-3"><span className={c.passed == null ? "text-faint" : c.passed ? "text-ink" : "text-dim"}>{c.passed == null ? "n/a" : c.passed ? "Yes" : "No"} · {c.name}</span><span className="num text-[11px] text-faint">{c.detail}</span></li>
                      ))}
                    </ul>
                  </div>
                </div>
              </Card>
              <Card title="Entry, exit and invalidation">
                <div className="space-y-3 text-[12.5px] leading-relaxed">
                  {[["Entry conditions", res.entry_conditions, "No entry is suggested for this signal."], ["Exit conditions", res.exit_conditions, ""], ["What would invalidate the view", res.invalidation, ""]].map(([t, list, empty]) => (
                    <div key={t as string}>
                      <div className="mb-1 sub">{t as string}</div>
                      {(list as string[])?.length ? <ul className="list-disc space-y-0.5 pl-4">{(list as string[]).map((r) => <li key={r}>{r}</li>)}</ul> : <p className="text-faint">{empty as string}</p>}
                    </div>
                  ))}
                  <div>
                    <div className="mb-1 sub">Expected holding period</div>
                    <p>{res.holding_period}</p>
                  </div>
                  {(res.upcoming_events ?? []).length > 0 && (
                    <div>
                      <div className="mb-1 sub">Upcoming events</div>
                      <KV rows={(res.upcoming_events ?? []).map((e: J): [React.ReactNode, React.ReactNode] => [e.type, <span key={e.date} title={e.basis}>{e.date}</span>])} />
                      <p className="note mt-1">Estimated from last year&apos;s filing date; not a confirmed date.</p>
                    </div>
                  )}
                  {(res.upcoming_events ?? []).length === 0 && <p className="note">No upcoming event could be estimated. The free data sources carry no confirmed earnings calendar.</p>}
                </div>
              </Card>
              <Card title="Risk and scenarios">
                <KV rows={[
                  ["Volatility, 1 year / 3 months", `${fmtPct(res.risk.volatility_1y, 0)} / ${fmtPct(res.risk.volatility_3m, 0)}`],
                  ["Worst drawdown, last year", <span key="d" className="text-down">{fmtPct(res.risk.max_drawdown_1y)}</span>],
                  ["ATR (14 days)", fmtMoney(res.risk.atr_14)],
                  ["Stop reference", res.risk.stop_reference ? `${fmtMoney(res.risk.stop_reference)} (${fmtPct(res.risk.stop_distance_pct)})` : "—"],
                  ["Avg daily dollar volume (63d)", fmtCompact(res.risk.adv_dollar_63, "$")],
                  ["Market regime", titleCase(res.market_regime ?? "unknown")],
                ]} />
                {res.scenarios && (
                  <>
                    <div className="mt-3 sub">Price range over the holding period</div>
                    <div className="mt-1.5 grid grid-cols-4 gap-1 text-center text-[11.5px]">
                      {[["-2σ", res.scenarios.two_sigma_down, "text-down"], ["-1σ", res.scenarios.one_sigma_down, "text-down"], ["+1σ", res.scenarios.one_sigma_up, "text-up"], ["+2σ", res.scenarios.two_sigma_up, "text-up"]].map(([l, v, c]) => (
                        <div key={l as string} className="rounded border border-line py-1.5"><div className="text-faint">{l as string}</div><div className={`num ${c}`}>{fmtMoney(v as number)}</div></div>
                      ))}
                    </div>
                    <p className="note mt-2">{res.scenarios.basis}</p>
                  </>
                )}
                {res.strategy_performance && (
                  <>
                    <div className="mt-3 sub">Historical strategy performance <Tag tone="warn">Backtested</Tag></div>
                    <div className="mt-1.5">
                      <KV rows={[
                        [res.strategy_performance.strategy, `${fmtPct(res.strategy_performance.cagr)} CAGR · ${fmtNum(res.strategy_performance.sharpe)} Sharpe`],
                        ["Max drawdown", fmtPct(res.strategy_performance.max_drawdown)],
                        ["vs equal-weight universe (full / out-of-sample)", `${fmtPct(res.strategy_performance.excess_cagr_vs_universe, 1, true)} / ${fmtPct(res.strategy_performance.out_of_sample_excess_cagr_vs_universe, 1, true)}`],
                        ["Validation status", titleCase(res.strategy_performance.validation_status ?? "—")],
                      ]} />
                    </div>
                    <p className="note mt-1">{res.strategy_performance.caveat}</p>
                  </>
                )}
              </Card>
            </div>
          )}

          <div className="mt-3 grid gap-3 xl:grid-cols-3">
            <Card title="Screen results" pad={false} right={res.screen_pass ? <Tag tone="up">Passed</Tag> : <Tag tone="down">Failed</Tag>}>
              <ul>
                {res.screen.map((r: J) => (
                  <li key={r.rule} className="flex items-start gap-3 border-b border-line/50 px-4 py-2 text-[12px] last:border-0">
                    <span className={`mt-[1px] w-8 shrink-0 font-semibold ${r.passed ? "text-up" : "text-down"}`}>{r.passed ? "Pass" : "Fail"}</span>
                    <span className="text-dim">{r.detail}</span>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="Financial red flags" right={<Tag tone={res.red_flags?.length ? "warn" : "up"}>{res.red_flags?.length ?? 0}</Tag>}>
              {res.red_flags?.length ? (
                <ul className="space-y-2 text-[12.5px]">
                  {res.red_flags.map((r: J) => <li key={r.code} className="flex gap-2"><Tag tone={r.severity === "severe" ? "down" : "warn"}>{r.severity}</Tag><span className="text-dim">{r.text}</span></li>)}
                </ul>
              ) : res.score == null ? <Empty title="Not evaluated" /> : <Empty title="None raised">Altman Z, Piotroski, accruals, leverage, interest coverage, dilution and data-quality checks found nothing.</Empty>}
              <p className="note mt-3">Screening diagnostics, not proof of distress or manipulation.</p>
            </Card>
            <Card title="Model output and score history">
              <KV rows={[
                ["Active validated model", info.data.ml.active_model ? titleCase(info.data.ml.active_model) : "none"],
                ["Model score for this stock", info.data.ml.active_model ? fmtNum(info.data.ml.model_score, 3) : "not used"],
              ]} />
              <p className="note mt-2">{info.data.ml.note}</p>
              {histOption ? <EChart option={histOption} height={130} /> : <p className="note mt-3">Score history appears after two or more scans.</p>}
            </Card>
          </div>

          {res.score != null && (
            <Card title="Fundamentals and factor inputs" className="mt-3" right={<span className="text-[11px] text-faint">trailing twelve months unless stated</span>}>
              <div className="grid gap-x-10 gap-y-4 md:grid-cols-2 xl:grid-cols-4">
                <div><div className="mb-1.5 sub">Valuation</div><KV rows={[["Market cap", fmtCompact(f.market_cap, "$")], ["Enterprise value", fmtCompact(f.enterprise_value, "$")], ["P/E", fmtNum(f.pe, 1)], ["EV/EBITDA", fmtNum(f.ev_ebitda, 1)], ["P/B", fmtNum(f.pb, 1)], ["P/S", fmtNum(f.ps, 1)], ["EBIT / EV", fmtPct(f.ebit_ev)], ["FCF yield", fmtPct(f.fcf_yield)], ["Shareholder yield", fmtPct(f.shareholder_yield)]]} /></div>
                <div><div className="mb-1.5 sub">Profitability and quality</div><KV rows={[["Revenue", fmtCompact(f.revenue_ttm, "$")], ["Net income", fmtCompact(f.net_income_ttm, "$")], ["Free cash flow", fmtCompact(f.fcf_ttm, "$")], ["Gross margin", fmtPct(f.gross_margin)], ["Operating margin", fmtPct(f.operating_margin)], ["ROIC", fmtPct(f.roic)], ["ROE", fmtPct(f.roe)], ["Gross profit / assets", fmtPct(f.gross_profitability)], ["Accruals / assets", fmtPct(f.accruals)]]} /></div>
                <div><div className="mb-1.5 sub">Growth and strength</div><KV rows={[["Revenue growth (FY)", fmtPct(f.revenue_growth, 1, true)], ["Revenue growth (quarter, y/y)", fmtPct(f.revenue_growth_q, 1, true)], ["Earnings growth (FY)", fmtPct(f.earnings_growth, 1, true)], ["Asset growth", fmtPct(f.asset_growth, 1, true)], ["Current ratio", fmtNum(f.current_ratio)], ["Debt / equity", fmtNum(f.debt_to_equity)], ["Net debt / EBITDA", fmtNum(f.net_debt_to_ebitda, 1)], ["Interest coverage", fmtNum(f.interest_coverage, 1)], ["Days since last filing", fmtNum(f.days_since_filing, 0)]]} /></div>
                <div><div className="mb-1.5 sub">Scores and momentum</div><KV rows={[["Piotroski F-score", f.piotroski == null ? "—" : `${fmtNum(f.piotroski, 0)} of ${fmtNum(f.piotroski_n, 0)}`], ["Altman Z-score", fmtNum(f.altman_z)], ["Earnings surprise (SUE)", fmtNum(f.sue)], ["Momentum 12-1 month", <span key="m" className={signClass(f.mom_12_1)}>{fmtPct(f.mom_12_1, 1, true)}</span>], ["Momentum 6-1 month", <span key="n" className={signClass(f.mom_6_1)}>{fmtPct(f.mom_6_1, 1, true)}</span>], ["Last month", <span key="o" className={signClass(f.ret_1m)}>{fmtPct(f.ret_1m, 1, true)}</span>], ["From 52-week high", fmtPct(f.dist_52w_high)], ...Object.entries(res.factor_z ?? {}).slice(0, 3).map(([k, v]): [React.ReactNode, React.ReactNode] => [`${titleCase(k)} z-score`, fmtNum(v as number)])]} /></div>
              </div>
              <p className="note mt-3">Piotroski is shown out of the signals that could be evaluated (the share-dilution signal is not evaluated in this version). Altman Z is not computed for financial companies. Z-scores are sector-neutral for accounting factors.</p>
            </Card>
          )}
        </>
      )}

      <div className="mt-3 grid gap-3 xl:grid-cols-3">
        <Card title="Financial statements as filed" className="xl:col-span-2" pad={false} right={<Tag>{fund.data?.source ?? "SEC EDGAR"}</Tag>}>
          {!fund.data ? <Loading /> : !fund.data.available ? <Empty title="No fundamentals stored">{fund.data.reason}</Empty> : (
            <>
              <div className="max-h-96 overflow-auto">
                <table className="w-full">
                  <thead className="sticky top-0 bg-panel">
                    <tr className="border-b border-line">{["Filed", "Period end", "Basis", "Revenue", "Gross profit", "Op. income", "Net income", "Op. cash flow", "FCF", "Assets", "Equity", "Debt", "Cash", "Gross mgn", "ROIC", "F-score"].map((h) => <th key={h} className="th text-right first:text-left">{h}</th>)}</tr>
                  </thead>
                  <tbody>
                    {fund.data.rows.map((r: J) => (
                      <tr key={r.filed} className="border-b border-line/40 text-[11.5px]">
                        <td className="td num">{r.filed}</td>
                        <td className="td num text-right text-dim">{r.period_end ?? "—"}</td>
                        <td className="td text-right text-faint">{r.ttm_basis === "ttm" ? "TTM" : r.ttm_basis === "fiscal_year" ? "FY" : r.ttm_basis === "sum_4q" ? "4Q" : "—"}</td>
                        {["revenue_ttm", "gross_profit_ttm", "operating_income_ttm", "net_income_ttm", "ocf_ttm", "fcf_ttm", "assets", "equity", "total_debt", "cash"].map((k) => <td key={k} className={`td num text-right ${r[k] != null && r[k] < 0 ? "text-down" : ""}`}>{fmtCompact(r[k])}</td>)}
                        <td className="td num text-right text-dim">{fmtPct(r.gross_margin)}</td>
                        <td className="td num text-right text-dim">{fmtPct(r.roic)}</td>
                        <td className="td num text-right text-dim">{r.piotroski == null ? "—" : `${r.piotroski}/${r.piotroski_n}`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="note border-t border-line px-4 py-2">{fund.data.note} Values in US dollars.</p>
            </>
          )}
        </Card>
        <Card title="SEC filings" pad={false}>
          {!fund.data ? <Loading /> : fund.data.filings.length === 0 ? <Empty title="No filings stored" /> : (
            <ul className="max-h-[26rem] overflow-y-auto">
              {fund.data.filings.filter((x: J) => x.form !== "4").slice(0, 40).map((x: J) => (
                <li key={x.accession} className="flex items-center justify-between gap-3 border-b border-line/50 px-4 py-1.5 text-[12px]">
                  <span><span className="num mr-2 inline-block w-14 font-semibold">{x.form}</span><span className="text-dim">{x.description || (x.report_date ? `period ${x.report_date}` : "")}</span></span>
                  <span className="flex shrink-0 items-center gap-3"><span className="num text-faint">{x.filing_date}</span>{x.url && <a href={x.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">Open</a>}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {sec.eligible && (
        <Card title={`News and sentiment for ${symbol}`} className="mt-3">
          <NewsFeed symbol={symbol} limit={10} />
        </Card>
      )}

      {res?.sources?.length > 0 && (
        <Card title="Sources for this page" className="mt-3">
          <ul className="grid gap-x-8 gap-y-1 text-[12px] md:grid-cols-3">
            {res.sources.map((s: J) => <li key={s.name} className="flex justify-between gap-3"><span className="text-dim">{s.name}<span className="block text-[10.5px] text-faint">{s.use}</span></span><span className="num shrink-0">{(s.as_of ?? "").slice(0, 10)}</span></li>)}
          </ul>
          <p className="note mt-2">Researched {fmtDateTime(res.as_of)} in scan {res.scan_id}. Headlines come from an unofficial feed and are scored for tone only; earnings-call transcripts are not available.</p>
        </Card>
      )}
    </>
  );
}
