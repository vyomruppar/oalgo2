"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { SWRConfig } from "swr";
import { fetcher } from "@/lib/api";
import { regimeLabel, timeAgo } from "@/lib/format";
import { LiveProvider, stageLabel, useLive } from "@/lib/live";
import { useApi } from "./ui";

const NAV = [
  { href: "/", label: "Overview", hint: "Scan activity and top signals" },
  { href: "/market", label: "Market", hint: "Indexes, breadth, sectors" },
  { href: "/strategies", label: "Strategies & Factors", hint: "Backtests and validation" },
  { href: "/ml", label: "Model Monitor", hint: "Walk-forward ML results" },
  { href: "/stocks", label: "Stock Explorer", hint: "Research every stock" },
  { href: "/portfolio", label: "Portfolio & Risk", hint: "Paper trading" },
  { href: "/alerts", label: "Alerts", hint: "Signal and risk notices" },
  { href: "/settings", label: "Settings", hint: "Screens, weights, data" },
];

function StatusBar() {
  const { mode, scan } = useLive();
  const { data } = useApi("/api/overview", 60000);
  const regime = regimeLabel(data?.regime?.regime);
  const last = data?.scan?.last_success;
  const modeCls = mode === "stream" ? "bg-up" : mode === "polling" ? "bg-warn" : mode === "offline" ? "bg-down" : "bg-faint";
  const modeText = { stream: "Live updates", polling: "Polling every 5s", offline: "Backend unreachable", connecting: "Connecting" }[mode];
  return (
    <div className="sticky top-0 z-20 border-b border-line bg-bg/95 backdrop-blur">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 px-5 py-2 text-[11.5px]">
        <span className="flex items-center gap-1.5 text-dim" title="How this page receives updates from the research backend">
          <span className={`h-1.5 w-1.5 rounded-full ${modeCls}`} />
          {modeText}
        </span>
        <span className="text-dim">
          Scan: <span className={scan.running ? "text-accent" : "text-ink"}>{scan.running ? `${stageLabel(scan.stage)} ${Math.round(scan.progress * 100)}%` : "idle"}</span>
        </span>
        <span className="text-dim">
          Last successful scan: <span className="text-ink">{timeAgo(last?.finished_at)}</span>
        </span>
        <span className="text-dim">
          Regime: <span className={regime.cls}>{regime.label}</span>
        </span>
        <span className="ml-auto flex items-center gap-3">
          <span className="chip border-warn/40 text-warn" title="Prices are daily bars from a delayed source. Nothing here is real-time.">
            End-of-day data
          </span>
          <Link href="/alerts" className="text-dim hover:text-accent">
            Alerts{" "}
            {data?.unread_alerts ? <span className="num rounded-sm bg-accent/20 px-1.5 py-[1px] text-accent">{data.unread_alerts}</span> : <span className="num text-faint">0</span>}
          </Link>
        </span>
      </div>
      {scan.running && (
        <div className="h-[2px] w-full bg-line">
          <div className="h-full bg-accent transition-[width] duration-700" style={{ width: `${Math.max(2, scan.progress * 100)}%` }} />
        </div>
      )}
    </div>
  );
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  return (
    <SWRConfig value={{ fetcher }}>
      <LiveProvider>
        <div className="flex min-h-screen">
          <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-line bg-panel md:flex">
            <div className="border-b border-line px-4 py-4">
              <div className="text-[13px] font-semibold tracking-tight">
                oalgo<span className="text-accent">2</span>
              </div>
              <div className="mt-0.5 text-[10.5px] uppercase tracking-[0.14em] text-faint">Research command center</div>
            </div>
            <nav className="flex-1 overflow-y-auto py-2">
              {NAV.map((n) => {
                const on = n.href === "/" ? path === "/" : path.startsWith(n.href);
                return (
                  <Link key={n.href} href={n.href} aria-current={on ? "page" : undefined} className={`block border-l-2 px-4 py-2 transition-colors ${on ? "border-accent bg-raised" : "border-transparent hover:bg-raised/60"}`}>
                    <div className={`text-[12.5px] font-medium ${on ? "text-accent" : "text-ink"}`}>{n.label}</div>
                    <div className="text-[10.5px] text-faint">{n.hint}</div>
                  </Link>
                );
              })}
            </nav>
            <div className="border-t border-line px-4 py-3 text-[10.5px] leading-relaxed text-faint">
              Research and paper trading only. Not investment advice. This platform cannot place real orders.
            </div>
          </aside>
          <div className="min-w-0 flex-1">
            <StatusBar />
            <nav className="flex gap-1 overflow-x-auto border-b border-line px-3 py-2 md:hidden">
              {NAV.map((n) => (
                <Link key={n.href} href={n.href} className="whitespace-nowrap rounded px-2 py-1 text-[11.5px] text-dim hover:text-accent">
                  {n.label}
                </Link>
              ))}
            </nav>
            <main className="mx-auto max-w-[1500px] px-5 py-5">{children}</main>
          </div>
        </div>
      </LiveProvider>
    </SWRConfig>
  );
}
