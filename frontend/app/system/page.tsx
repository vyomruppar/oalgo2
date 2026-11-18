"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import EChart, { C, baseOption, catAxis, valueAxis } from "@/components/EChart";
import { Card, Empty, ErrorBox, Loading, PageTitle, ScoreBar, SignalChip, Stat, SymbolLink, Tag, useApi } from "@/components/ui";
import { NO_WRITES, QUEUED, READ_ONLY, send, type J } from "@/lib/api";
import { fmtCompact, fmtDateTime, fmtMoney, fmtNum, regimeLabel, timeAgo, titleCase } from "@/lib/format";
import { stageLabel, useLive } from "@/lib/live";

const SIGNAL_ORDER = ["STRONG BUY", "BUY", "WATCHLIST", "HOLD", "SELL", "NO_ACTION", "None"];
const SIGNAL_COLOR: Record<string, string> = { "STRONG BUY": C.up, BUY: "#23b894", WATCHLIST: C.accent, HOLD: "#4a5296", SELL: C.down, NO_ACTION: "#2a3070", None: "#1c2156" };
const RULE_LABEL: Record<string, string> = {
  min_market_cap: "Market cap below minimum",
  fundamentals_available: "No usable SEC fundamentals",
  max_volatility: "Volatility above maximum",
  min_price: "Price below minimum",
  min_history: "Too little trading history",
  min_adv_dollar: "Dollar volume below minimum",
  sector: "Sector excluded",
  price_data_quality: "Price data failed validation",
  fresh_prices: "Stale prices",
};

function ChangeLog() {
  const { data } = useApi("/api/ops-log");
  const entries: J[] = data?.entries ?? [];
  return (
    <Card title="Recent changes from the dashboard" className="mt-3" pad={false}>
      {entries.length === 0 ? (
        <Empty title="No changes yet">Holdings, settings and scan requests you make here are applied by the next update and listed below.</Empty>
      ) : (
        <table className="w-full">
          <thead>
            <tr className="border-b border-line/40">
              <th className="th">Requested</th>
              <th className="th">Change</th>
              <th className="th">Result</th>
            </tr>
          </thead>
          <tbody>
            {entries.slice(0, 30).map((e) => (
              <tr key={e.file} className="border-b border-line/30">
                <td className="td text-dim">{fmtDateTime(e.queued_at ?? e.at)}</td>
                <td className="td">{e.what ?? "Unreadable change"}</td>
                <td className={`td whitespace-normal ${e.status === "applied" ? "text-up" : "text-down"}`}>{e.status === "applied" ? "Applied" : `Not applied: ${e.reason}`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

export default function Overview() {
  const { data, error, mutate } = useApi("/api/overview", 30000);
  const { scan, events } = useLive();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const run = async (fetch: boolean) => {
    setBusy(true);
    setMsg(null);
    try {
      await send("POST", "/api/scans", { fetch, force_research: false });
      mutate();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const signalOption = useMemo(() => {
    const s: Record<string, number> = data?.signals ?? {};
    const keys = SIGNAL_ORDER.filter((k) => s[k]);
    return baseOption({
      grid: { left: 96, right: 36, top: 6, bottom: 6 },
      tooltip: { trigger: "item" },
      xAxis: valueAxis({ show: false, scale: false }),
      yAxis: catAxis(keys.map((k) => (k === "None" ? "Screened out" : titleCase(k.toLowerCase()))).reverse(), { axisLine: { show: false } }),
      series: [{ type: "bar", barWidth: 12, data: keys.map((k) => ({ value: s[k], itemStyle: { color: SIGNAL_COLOR[k], borderRadius: 2 } })).reverse(), label: { show: true, position: "right", color: C.dim, fontSize: 11 } }],
    });
  }, [data]);

  if (error && !data) return <ErrorBox error={error} />;
  if (!data) return <Loading rows={6} />;
  const u = data.universe;
  const last = data.scan.last;
  const ok = data.scan.last_success;
  const regime = regimeLabel(data.regime?.regime);
  const running = scan.running || data.scan.running;
  const failReasons: [string, number][] = Object.entries(u.screen_fail_reasons ?? {});
  const exclusions: [string, number][] = Object.entries(u.listing_exclusions ?? {});
  const stats = running ? scan.stats : (ok?.stats ?? {});

  return (
    <>
      <PageTitle
        title="Scans and data"
        sub="What the research engine is doing now, what it found on the last scan, and how healthy its data sources are. Every figure on this page comes from the backend; nothing is illustrative."
        right={
          <div className="flex items-center gap-2">
            <button className="btn" disabled={busy || running || NO_WRITES} onClick={() => run(false)} title={NO_WRITES ? READ_ONLY : "Re-screen and re-score from stored data without downloading"}>
              Re-score stored data
            </button>
            <button className="btn btn-primary" disabled={busy || running || NO_WRITES} title={NO_WRITES ? READ_ONLY : undefined} onClick={() => run(true)}>
              {running ? "Scan running" : "Run scan now"}
            </button>
          </div>
        }
      />
      {msg && <div className="mb-3 rounded border border-down/40 bg-down/5 px-3 py-2 text-xs text-down">{msg}</div>}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Exchange listings" value={fmtNum(u.listed, 0)} sub="NYSE and NASDAQ directory" />
        <Stat label="Eligible common stocks" value={fmtNum(u.eligible_listings, 0)} sub="after security-type exclusions" />
        <Stat label="Scanned" value={fmtNum(u.scanned, 0)} sub="most liquid first" />
        <Stat label="Passed screen" value={fmtNum(u.passed, 0)} cls="text-up" sub={u.scanned ? `${Math.round((100 * (u.passed ?? 0)) / u.scanned)}% of scanned` : undefined} />
        <Stat label="Failed screen" value={fmtNum(u.failed, 0)} cls="text-down" sub="with recorded reasons" />
        <Stat label="Market regime" value={regime.label} cls={regime.cls} sub={data.regime?.as_of ? `as of ${data.regime.as_of}` : "no scan yet"} />
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-3">
        <Card title="Scan activity" className="xl:col-span-1" right={running ? <Tag tone="accent">Running</Tag> : last?.status === "failed" ? <Tag tone="down">Last run failed</Tag> : <Tag>Idle</Tag>}>
          <div className="space-y-3">
            <div>
              <div className="flex items-baseline justify-between text-[12.5px]">
                <span className={running ? "text-accent" : "text-dim"}>{running ? stageLabel(scan.stage ?? last?.stage) : last ? stageLabel(last.stage) : "No scan has run yet"}</span>
                <span className="num text-dim">{running ? `${Math.round(scan.progress * 100)}%` : ""}</span>
              </div>
              <div className="mt-1.5 h-1.5 rounded-sm bg-line">
                <div className={`h-full rounded-sm transition-[width] duration-700 ${running ? "bg-accent" : "bg-faint/50"}`} style={{ width: `${running ? Math.max(2, scan.progress * 100) : last ? 100 : 0}%` }} />
              </div>
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[12px]">
              <dt className="text-dim">Last successful scan</dt>
              <dd className="num text-right">{ok ? `${fmtDateTime(ok.finished_at)} (${timeAgo(ok.finished_at)})` : "never"}</dd>
              <dt className="text-dim">Next scheduled scan</dt>
              <dd className="num text-right">{data.scan.next_scheduled ? fmtDateTime(data.scan.next_scheduled) : "scheduler off"}</dd>
              <dt className="text-dim">Prices as of</dt>
              <dd className="num text-right">{stats.price_as_of ?? "—"}</dd>
              <dt className="text-dim">Stocks with SEC fundamentals</dt>
              <dd className="num text-right">{fmtNum(stats.with_fundamentals, 0)}</dd>
              <dt className="text-dim">Price / filing fetch failures</dt>
              <dd className="num text-right">
                {fmtNum(stats.price_failures, 0)} / {fmtNum(stats.fundamentals_failures, 0)}
              </dd>
              <dt className="text-dim">Alerts from last scan</dt>
              <dd className="num text-right">{fmtNum(stats.alerts_generated, 0)}</dd>
            </dl>
            {last?.status === "failed" && <div className="rounded border border-down/40 bg-down/5 px-2 py-1.5 text-[11.5px] text-down">{last.error}</div>}
            <div>
              <div className="mb-1 sub">Live event log</div>
              <ul className="max-h-36 space-y-0.5 overflow-y-auto text-[11.5px]" aria-live="polite">
                {events.length === 0 && <li className="text-faint">Waiting for backend events. Start a scan to watch it work.</li>}
                {events.slice(0, 30).map((e) => (
                  <li key={e.id} className="flex gap-2">
                    <span className="num shrink-0 text-faint">{new Date(e.ts * 1000).toLocaleTimeString("en-US", { hour12: false })}</span>
                    <span className="truncate text-dim">
                      {e.type === "scan_progress" ? `${stageLabel(e.data.stage)}${e.data.symbol ? ` · ${e.data.symbol}` : ""}` : e.type === "alert" ? `Alert: ${e.data.title}` : titleCase(e.type)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Card>

        <Card title="Top-ranked opportunities" className="xl:col-span-2" pad={false} right={<Link href="/stocks" className="text-[11px] text-dim hover:text-accent">Open explorer</Link>}>
          {data.top.length === 0 ? (
            <Empty title="No ranked stocks yet">Run a scan. Stocks appear here once they pass the screen and are scored.</Empty>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-line">
                    <th className="th">Symbol</th>
                    <th className="th">Company</th>
                    <th className="th">Exch.</th>
                    <th className="th">Sector</th>
                    <th className="th text-right">Price</th>
                    <th className="th text-right">Mkt cap</th>
                    <th className="th">Score</th>
                    <th className="th">Signal</th>
                    <th className="th">Data</th>
                  </tr>
                </thead>
                <tbody>
                  {data.top.map((r: J) => (
                    <tr key={r.symbol} className="border-b border-line/50 hover:bg-raised/50">
                      <td className="td"><SymbolLink symbol={r.symbol} /></td>
                      <td className="td max-w-[220px] truncate text-dim">{(r.company ?? "").replace(/ - .*$| Common Stock.*$/i, "")}</td>
                      <td className="td text-dim">{r.exchange}</td>
                      <td className="td text-dim">{r.sector}</td>
                      <td className="td num text-right">{fmtMoney(r.price)}</td>
                      <td className="td num text-right text-dim">{fmtCompact(r.market_cap, "$")}</td>
                      <td className="td"><ScoreBar value={r.score} /></td>
                      <td className="td"><SignalChip signal={r.signal} /></td>
                      <td className="td num text-dim" title="Share of score components with data (A is best)">{r.data_quality}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="note border-t border-line px-4 py-2">A score ranks stocks on evidence-backed characteristics. It is not a probability of profit, and a high score is not a recommendation to buy. Prices as of each stock&apos;s last completed session.</p>
        </Card>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2 xl:grid-cols-4">
        <Card title="Current signals">
          {Object.keys(data.signals).length ? <EChart option={signalOption} height={170} /> : <Empty title="No signals yet" />}
        </Card>
        <Card title="Why stocks failed the screen">
          {failReasons.length ? (
            <ul className="space-y-1.5 text-[12.5px]">
              {failReasons.map(([k, n]) => (
                <li key={k} className="flex justify-between gap-3">
                  <span className="text-dim">{RULE_LABEL[k] ?? k}</span>
                  <span className="num">{n}</span>
                </li>
              ))}
            </ul>
          ) : (
            <Empty title="No rejections recorded" />
          )}
          <p className="note mt-3">A stock can fail several rules. Open any stock to see each rule, the observed value and the threshold.</p>
        </Card>
        <Card title="Listings excluded before screening">
          {exclusions.length ? (
            <ul className="max-h-44 space-y-1.5 overflow-y-auto text-[12.5px]">
              {exclusions.map(([k, n]) => (
                <li key={k} className="flex justify-between gap-3">
                  <span className="truncate text-dim" title={k}>{titleCase(k.replace("security type: ", "").replace(/ \(.*\)$/, ""))}</span>
                  <span className="num">{n}</span>
                </li>
              ))}
            </ul>
          ) : (
            <Empty title="No scan yet" />
          )}
          <p className="note mt-3">Only NYSE and NASDAQ listings enter the universe. OTC and other venues are never loaded.</p>
        </Card>
        <Card title="New signals" right={<Link href="/alerts" className="text-[11px] text-dim hover:text-accent">All alerts</Link>}>
          {data.new_signals.length ? (
            <ul className="space-y-2 text-[12px]">
              {data.new_signals.slice(0, 6).map((a: J) => (
                <li key={a.id} className="flex items-start justify-between gap-2">
                  <span className="min-w-0">
                    {a.symbol && <SymbolLink symbol={a.symbol} />} <span className="text-dim">{(a.payload?.company ?? "").replace(/ - .*$| Common Stock.*$| Class .*$/i, "")}</span>
                  </span>
                  <span className="shrink-0"><SignalChip signal={a.payload?.signal} /></span>
                </li>
              ))}
            </ul>
          ) : (
            <Empty title="No signal changes">Alerts fire only when a signal changes, not on every scan.</Empty>
          )}
        </Card>
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-3">
        <Card title="Active strategies" pad={false} right={<Link href="/lab/validation" className="text-[11px] text-dim hover:text-accent">Research</Link>}>
          <table className="w-full">
            <tbody>
              {data.strategies.map((s: J) => (
                <tr key={s.key} className="border-b border-line/50 last:border-0">
                  <td className="td whitespace-normal">{s.name}<div className="text-[10.5px] text-faint">{s.family}</div></td>
                  <td className="td text-right">
                    {s.status === "supported" ? <Tag tone="up">Supported</Tag> : s.status === "mixed" ? <Tag tone="accent">Mixed</Tag> : s.status ? <Tag tone="down">Not supported</Tag> : <Tag>Not tested</Tag>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="note border-t border-line px-4 py-2">Status reflects backtested results after costs against the equal-weight universe.</p>
        </Card>
        <Card title="Models" right={<Link href="/lab/ml" className="text-[11px] text-dim hover:text-accent">Monitor</Link>}>
          {data.models.length ? (
            <ul className="space-y-2 text-[12.5px]">
              {data.models.map((m: J) => (
                <li key={m.name} className="flex items-center justify-between gap-2">
                  <span>{titleCase(m.name)}</span>
                  <span className="flex items-center gap-2">
                    <span className="num text-dim" title="Out-of-sample rank information coefficient">IC {fmtNum(m.oos_rank_ic, 3)}</span>
                    {m.active ? <Tag tone="up">In score</Tag> : m.validated ? <Tag tone="accent">Validated</Tag> : <Tag>Not validated</Tag>}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <Empty title={data.ml_status === "insufficient_history" ? "Not enough history to train" : "No model trained yet"} />
          )}
          <p className="note mt-3">A model contributes to scores only after it passes out-of-sample validation. Version {data.ml_version ?? "—"}.</p>
        </Card>
        <Card title="Data provider health" pad={false}>
          <table className="w-full">
            <tbody>
              {data.providers.map((p: J) => (
                <tr key={p.key} className="border-b border-line/50 last:border-0" title={p.limits}>
                  <td className="td">
                    <div className="max-w-[230px] truncate">{p.name}</div>
                    <div className="text-[10.5px] text-faint">{p.freshness}</div>
                  </td>
                  <td className="td text-right text-[11px] text-dim">{p.last_success ? timeAgo(p.last_success) : "not used yet"}</td>
                  <td className="td text-right">
                    {p.status === "ok" ? <Tag tone="up">OK</Tag> : p.status === "failing" ? <Tag tone="down">Failing</Tag> : p.status === "degraded" ? <Tag tone="warn">Degraded</Tag> : <Tag>Unknown</Tag>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
      {QUEUED && <ChangeLog />}
    </>
  );
}
