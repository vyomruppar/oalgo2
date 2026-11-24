"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { SWRConfig } from "swr";
import useSWR from "swr";
import { useEffect, useRef, useState } from "react";
import { fetcher, QUEUED, SNAPSHOT } from "@/lib/api";
import { regimeLabel, timeAgo } from "@/lib/format";
import { weekdaysBetween } from "@/lib/quotes";
import { LiveProvider, stageLabel, useLive } from "@/lib/live";
import Backdrop from "./Backdrop";
import { useApi } from "./ui";

type Item = { href: string; label: string; match?: string };
const GROUPS: { title: string | null; items: Item[] }[] = [
  {
    title: null,
    items: [
      { href: "/", label: "Command" },
      { href: "/portfolio", label: "My portfolio" },
      { href: "/market", label: "Market" },
    ],
  },
  {
    title: "Quant lab",
    items: [
      { href: "/lab/factors", label: "Factors" },
      { href: "/lab/momentum", label: "Momentum and trend" },
      { href: "/lab/mean-reversion", label: "Mean reversion" },
      { href: "/lab/volatility", label: "Volatility and regime" },
      { href: "/lab/ml", label: "Machine learning" },
      { href: "/lab/validation", label: "Validation" },
    ],
  },
  {
    title: "Research",
    items: [
      { href: "/stocks", label: "Stock explorer" },
      { href: "/news", label: "News and sentiment" },
      { href: "/alerts", label: "Alerts" },
    ],
  },
  {
    title: "System",
    items: [
      { href: "/system", label: "Scans and data" },
      { href: "/settings", label: "Settings" },
    ],
  },
];
const FLAT = GROUPS.flatMap((g) => g.items);

function isOn(path: string, href: string) {
  return href === "/" ? path === "/" : path === href || path.startsWith(`${href}/`);
}

/** Free hosted setup: show whether a GitHub Actions update is running or waiting, and offer a reload when new data is published. */
function UpdateStatus() {
  const { data: st } = useSWR("/ops/status", (u: string) => fetch(u, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)), { refreshInterval: 20000 });
  const { data: meta } = useSWR("/data/meta.json", (u: string) => fetch(u, { cache: "no-store" }).then((r) => r.json()), { refreshInterval: 30000 });
  const first = useRef<string | null>(null);
  const [fresh, setFresh] = useState(false);
  useEffect(() => {
    if (!meta?.exported_at) return;
    if (first.current == null) first.current = meta.exported_at;
    else if (meta.exported_at !== first.current) setFresh(true);
  }, [meta]);
  return (
    <>
      {st?.running ? (
        <span className="text-accent" title="GitHub Actions is updating the data. The page offers a reload when it is done.">
          Update running, started {timeAgo(st.started_at)}
        </span>
      ) : st?.queued_changes ? (
        <span className="text-warn">{st.queued_changes} change{st.queued_changes > 1 ? "s" : ""} waiting for the next update</span>
      ) : null}
      {fresh && (
        <button type="button" className="chip border-up/50 text-up hover:bg-up/10" onClick={() => window.location.reload()}>
          New data is ready. Reload
        </button>
      )}
    </>
  );
}

function StatusBar() {
  const { mode, scan } = useLive();
  const { data } = useApi("/api/overview", 60000);
  const regime = regimeLabel(data?.regime?.regime);
  const last = data?.scan?.last_success;
  const modeCls = mode === "snapshot" ? "bg-warn" : mode === "stream" ? "bg-up shadow-[0_0_8px_rgb(61_242_196)]" : mode === "polling" ? "bg-warn" : mode === "offline" ? "bg-down" : "bg-faint";
  const modeText = { stream: "Live updates", polling: "Polling every 5s", offline: "Backend unreachable", connecting: "Connecting", snapshot: QUEUED ? `Prices as of ${last?.stats?.price_as_of ?? "the last scan"}` : `Read-only snapshot of ${last?.stats?.price_as_of ?? "the last scan"}` }[mode];
  return (
    <div className="sticky top-0 z-20 border-b border-line/40 bg-bg/70 backdrop-blur-xl">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 px-5 py-2 text-[12px]">
        <span className="flex items-center gap-2 text-dim" title="How this page receives updates from the research backend">
          <span className={`h-1.5 w-1.5 rounded-full ${modeCls}`} />
          {modeText}
        </span>
        {SNAPSHOT && !QUEUED && <span className="text-faint">Sample holdings. Scans, saving and live prices need the app running on your computer.</span>}
        {QUEUED && <UpdateStatus />}
        <span className={SNAPSHOT ? "hidden" : "text-dim"}>
          Scan <span className={scan.running ? "text-accent" : "text-ink"}>{scan.running ? `${stageLabel(scan.stage)} ${Math.round(scan.progress * 100)}%` : "idle"}</span>
        </span>
        <span className={SNAPSHOT ? "hidden" : "text-dim"}>
          Last scan <span className="text-ink">{timeAgo(last?.finished_at)}</span>
        </span>
        <span className="text-dim">
          Regime <span className={regime.cls}>{regime.label}</span>
        </span>
        <span className="ml-auto flex items-center gap-3">
          {(() => {
            const stale = weekdaysBetween(last?.stats?.price_as_of);
            return stale >= 2 ? (
              <Link href="/system" className="chip border-down/60 bg-down/10 text-down" title="Scores, signals and charts come from the last scan. Run a scan to refresh them.">
                Scan data is from {last?.stats?.price_as_of}. Refresh
              </Link>
            ) : (
              <span className="chip border-line text-dim" title="Scores and charts use stored end-of-day data from the last scan">Scores: end-of-day</span>
            );
          })()}
          {!SNAPSHOT && <span className="chip border-up/40 text-up" title="Holdings and stock pages show live prices from Yahoo Finance, delayed about 15 minutes">Quotes: ~15 min delayed</span>}
          <Link href="/alerts" className="text-dim hover:text-ink">
            Alerts {data?.unread_alerts ? <span className="num rounded-full bg-accent/30 px-1.5 py-[1px] text-ink">{data.unread_alerts}</span> : <span className="num text-faint">0</span>}
          </Link>
        </span>
      </div>
      {scan.running && (
        <div className="h-[2px] w-full bg-line/40">
          <div className="h-full bg-gradient-to-r from-accent via-[#5ec8ff] to-up transition-[width] duration-700" style={{ width: `${Math.max(2, scan.progress * 100)}%` }} />
        </div>
      )}
    </div>
  );
}

export default function Shell({ children, signOut = false }: { children: React.ReactNode; signOut?: boolean }) {
  const path = usePathname();
  if (path === "/login") {
    // the sign-in page has no navigation and makes no API calls
    return (
      <>
        <Backdrop />
        <main className="mx-auto max-w-[1560px] px-4 py-5 sm:px-5">{children}</main>
      </>
    );
  }
  return (
    <SWRConfig value={{ fetcher }}>
      <LiveProvider>
        <Backdrop />
        <div className="flex min-h-screen">
          <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-line/40 bg-panel/40 backdrop-blur-xl md:flex">
            <Link href="/" className="block border-b border-line/40 px-5 py-4">
              <div className="display text-[15px] font-medium">
                oalgo<span className="text-accent">2</span>
              </div>
              <div className="mt-0.5 text-[11px] text-faint">Observatory</div>
            </Link>
            <nav className="flex-1 overflow-y-auto py-3" aria-label="Sections">
              {GROUPS.map((g, gi) => (
                <div key={gi} className="mb-3">
                  {g.title && <div className="px-5 pb-1 pt-1 text-[11px] font-semibold text-faint">{g.title}</div>}
                  {g.items.map((n) => {
                    const on = isOn(path, n.href);
                    return (
                      <Link key={n.href} href={n.href} aria-current={on ? "page" : undefined} className={`group relative mx-2 flex items-center rounded-lg px-3 py-1.5 text-[13px] transition-colors ${on ? "bg-accent/20 text-ink" : "text-dim hover:bg-raised/50 hover:text-ink"}`}>
                        <span className={`mr-2.5 h-1.5 w-1.5 rounded-full transition-all ${on ? "bg-accent shadow-[0_0_10px_rgb(139_124_255)]" : "bg-line group-hover:bg-dim"}`} />
                        {n.label}
                      </Link>
                    );
                  })}
                </div>
              ))}
            </nav>
            <div className="border-t border-line/40 px-5 py-3 text-[11px] leading-relaxed text-faint">
              Research and tracking only. Not investment advice. This platform cannot place orders.
              {signOut && (
                <form method="post" action="/auth/logout" className="mt-2">
                  <button type="submit" className="text-[12px] text-dim underline-offset-2 hover:text-ink hover:underline">
                    Sign out
                  </button>
                </form>
              )}
            </div>
          </aside>
          <div className="min-w-0 flex-1">
            <StatusBar />
            <nav className="flex gap-1 overflow-x-auto border-b border-line/40 bg-bg/60 px-3 py-2 backdrop-blur md:hidden" aria-label="Sections">
              {FLAT.map((n) => (
                <Link key={n.href} href={n.href} aria-current={isOn(path, n.href) ? "page" : undefined} className={`whitespace-nowrap rounded-lg px-2.5 py-1 text-[12px] ${isOn(path, n.href) ? "bg-accent/25 text-ink" : "text-dim"}`}>
                  {n.label}
                </Link>
              ))}
            </nav>
            <main key={path} className="route-enter mx-auto max-w-[1560px] px-4 py-5 sm:px-5">
              {children}
            </main>
          </div>
        </div>
      </LiveProvider>
    </SWRConfig>
  );
}
