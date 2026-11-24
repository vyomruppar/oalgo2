"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import NewsFeed from "@/components/NewsFeed";
import { HoldingTile, PortfolioTracker } from "@/components/Portfolio";
import StarMap from "@/components/StarMap";
import { Card, CountUp, Empty, ErrorBox, Loading, PriceSource, SignalChip, SymbolLink, Tag, useApi } from "@/components/ui";
import { useLiveHoldings } from "@/lib/quotes";
import { NO_WRITES, READ_ONLY, send, type J } from "@/lib/api";
import { fmtMoney, fmtPct, regimeLabel, signClass, timeAgo, titleCase } from "@/lib/format";
import { stageLabel, useLive } from "@/lib/live";

export default function Command() {
  const { data, error, mutate } = useApi("/api/dashboard", 60000);
  const live = useLiveHoldings(data?.holdings);
  const { scan, events } = useLive();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 1023px)");
    const on = () => setNarrow(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);

  const runScan = async () => {
    setBusy(true);
    setMsg(null);
    try {
      await send("POST", "/api/scans", { fetch: true });
      mutate();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (error && !data) return <ErrorBox error={error} />;
  if (!data) return <Loading rows={8} />;
  const h = live.h;
  const has = h.n_positions > 0;
  const regime = regimeLabel(data.regime?.regime);
  const running = scan.running || data.scan.running;
  const scanned = data.stars.length;

  return (
    <>
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(340px,1fr)]">
        {/* The universe: bare, full-bleed, the one loud element on the page */}
        <section className="relative overflow-hidden rounded-2xl border border-line/30 bg-bg/30" aria-label="Stock universe map">
          <div className="pointer-events-none z-[1] px-4 pt-4 lg:absolute lg:left-4 lg:top-4 lg:p-0">
            <h1 className="display text-[26px] font-medium leading-none sm:text-[32px]">Your universe</h1>
            <p className="mt-1.5 max-w-xs text-[12px] text-dim">
              {scanned ? `${scanned} stocks from the last scan. The ringed ones are yours.` : "No scan yet. Run one to light up the map."}
            </p>
          </div>
          {scanned ? (
            <StarMap stars={data.stars} height={narrow ? 460 : 660} />
          ) : (
            <div className="flex h-[660px] items-center justify-center">
              <div className="text-center">
                <button className="btn btn-primary px-5 py-2.5 text-sm" disabled={busy || running} onClick={runScan}>
                  {running ? `${stageLabel(scan.stage)} ${Math.round(scan.progress * 100)}%` : "Run the first scan"}
                </button>
                <p className="note mt-3 max-w-xs">It verifies listings, downloads prices and filings, and scores about 300 stocks. Expect roughly ten minutes.</p>
              </div>
            </div>
          )}
        </section>

        <div className="flex flex-col gap-4">
          <Card title="My portfolio" right={<Link href="/portfolio" className="text-[12px] text-dim hover:text-accent">Manage holdings</Link>}>
            {has ? (
              <>
                <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
                  <div>
                    <div className="display num text-[30px] font-medium leading-none">
                      <CountUp value={h.value} format={(v) => fmtMoney(v, 0)} />
                    </div>
                    <div className="mt-1.5"><PriceSource live={h.live} marketOpen={h.market_open} time={h.live_time} date={h.as_of} /></div>
                  </div>
                  <dl className="num grid grid-cols-2 gap-x-5 text-right text-[12.5px]">
                    <dt className="text-faint">{h.live && h.market_open ? "Today" : "Last session"}</dt>
                    <dd className={signClass(h.day_change)}>
                      {fmtMoney(h.day_change, 0)} ({fmtPct(h.day_change_pct, 2, true)})
                    </dd>
                    <dt className="text-faint">Total gain</dt>
                    <dd className={signClass(h.gain)}>
                      {fmtMoney(h.gain, 0)} ({fmtPct(h.gain_pct, 1, true)})
                    </dd>
                  </dl>
                </div>
                <div className="mt-3">
                  <PortfolioTracker height={228} compact />
                </div>
              </>
            ) : (
              <Empty title="Add the stocks you own">
                Record your holdings to track their value, gains, risk, signals and news here.{" "}
                <Link href="/portfolio" className="text-accent underline">
                  Add holdings
                </Link>
              </Empty>
            )}
          </Card>
          <Card title="Conditions">
            <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5 text-[12.5px]">
              <dt className="text-dim">Market regime</dt>
              <dd className={`text-right font-semibold ${regime.cls}`}>{regime.label}</dd>
              <dt className="text-dim">Research engine</dt>
              <dd className="text-right">{running ? <span className="text-accent">{stageLabel(scan.stage)} {Math.round(scan.progress * 100)}%</span> : `idle · last scan ${timeAgo(data.scan.last_success?.finished_at)}`}</dd>
              <dt className="text-dim">Prices as of</dt>
              <dd className="num text-right">{data.scan.last_success?.stats?.price_as_of ?? "—"}</dd>
              <dt className="text-dim">Sentiment engine</dt>
              <dd className="text-right">{data.engine.is_ai ? "FinBERT (local AI)" : "Word list"}</dd>
            </dl>
            <div className="mt-3 flex items-center gap-2">
              <button className="btn btn-primary" disabled={busy || running || NO_WRITES} title={NO_WRITES ? READ_ONLY : undefined} onClick={runScan}>
                {running ? "Scan running" : "Run scan now"}
              </button>
              <Link href="/system" className="btn">
                Scan details
              </Link>
            </div>
            {msg && <div className="mt-2 text-[12px] text-down">{msg}</div>}
          </Card>
        </div>
      </div>

      {has && (
        <section className="mt-4" aria-label="Your holdings">
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="display text-[15px] font-medium">Holdings</h2>
            <span className="note">{h.n_positions} positions · click one for its research page</span>
          </div>
          <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))" }}>
            {h.positions.map((p: J) => (
              <HoldingTile key={p.symbol} p={p} />
            ))}
          </div>
          {h.missing_prices.length > 0 && <p className="note mt-2">No stored prices yet for {h.missing_prices.join(", ")}. They are valued after the next scan.</p>}
        </section>
      )}

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <Card title={has ? "News on your holdings" : "Latest headlines"} right={<Link href="/news" className="text-[12px] text-dim hover:text-accent">All news</Link>}>
          <NewsFeed scope={has ? "holdings" : "all"} limit={8} />
        </Card>
        <div className="flex flex-col gap-4">
          <Card title="What changed" right={<Link href="/alerts" className="text-[12px] text-dim hover:text-accent">{data.unread_alerts} unread</Link>}>
            {data.recent_alerts.length ? (
              <ul className="space-y-2 text-[12.5px]">
                {data.recent_alerts.map((a: J) => (
                  <li key={a.id} className="flex items-start justify-between gap-3">
                    <span className="min-w-0">
                      {a.symbol && <SymbolLink symbol={a.symbol} />} <span className="text-dim">{a.title.replace(/^(STRONG BUY|BUY|SELL): [A-Z-]+ /, "").replace(/^[A-Z-]+ /, "").replace(/\((.*?)( - .*| Common.*| Class.*)?\)$/, "$1")}</span>
                      <span className="block text-[11px] text-faint">{titleCase(a.kind)} · {timeAgo(a.created_at)}</span>
                    </span>
                    {a.payload?.signal && <span className="shrink-0"><SignalChip signal={a.payload.signal} /></span>}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty title="Nothing has changed">Alerts appear when a signal, score, risk flag or news tone changes.</Empty>
            )}
          </Card>
          <Card title="Live activity" right={running ? <Tag tone="accent">Scanning</Tag> : <Tag>Idle</Tag>}>
            <ul className="max-h-32 space-y-0.5 overflow-y-auto text-[12px]" aria-live="polite">
              {events.length === 0 && <li className="text-faint">Waiting for the research engine. Start a scan to watch it work.</li>}
              {events.slice(0, 24).map((e) => (
                <li key={e.id} className="flex gap-2">
                  <span className="num shrink-0 text-faint">{new Date(e.ts * 1000).toLocaleTimeString("en-US", { hour12: false })}</span>
                  <span className="truncate text-dim">{e.type === "scan_progress" ? `${stageLabel(e.data.stage)}${e.data.symbol ? ` ${e.data.symbol}` : ""}` : e.type === "alert" ? e.data.title : titleCase(e.type)}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
      <p className="note mt-4">{data.disclaimer} Prices are end-of-day; a score ranks stocks and is not a probability of profit.</p>
    </>
  );
}
