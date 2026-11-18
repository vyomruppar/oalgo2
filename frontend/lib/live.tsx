"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useSWRConfig } from "swr";
import { API_URL, SNAPSHOT, type J } from "./api";

export type LiveEvent = { id: number; type: string; ts: number; data: J };
type Mode = "connecting" | "stream" | "polling" | "offline" | "snapshot";
type ScanState = { running: boolean; stage: string | null; progress: number; stats: J };

type Live = { mode: Mode; scan: ScanState; events: LiveEvent[]; notifications: NotificationPermission | "unsupported"; enableNotifications: () => void };

const Ctx = createContext<Live>({
  mode: "connecting",
  scan: { running: false, stage: null, progress: 0, stats: {} },
  events: [],
  notifications: "unsupported",
  enableNotifications: () => {},
});

export const useLive = () => useContext(Ctx);

const STAGES: Record<string, string> = {
  listings: "Verifying exchange listings",
  liquidity: "Ranking liquidity",
  prices: "Updating prices",
  fundamentals: "Reading SEC filings",
  panel: "Building factor panel",
  screening: "Screening",
  backtests: "Backtesting strategies",
  machine_learning: "Training models",
  scoring: "Scoring and classifying",
  alerts: "Evaluating alerts",
  complete: "Complete",
};

export function stageLabel(stage: string | null | undefined): string {
  if (!stage) return "Idle";
  if (stage.startsWith("backtest:")) return `Backtesting: ${stage.slice(9).replace(/_/g, " ")}`;
  return STAGES[stage] ?? stage;
}

export function LiveProvider({ children }: { children: React.ReactNode }) {
  const { mutate } = useSWRConfig();
  const [mode, setMode] = useState<Mode>("connecting");
  const [scan, setScan] = useState<ScanState>({ running: false, stage: null, progress: 0, stats: {} });
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [notifications, setNotifications] = useState<Live["notifications"]>("unsupported");
  const lastId = useRef(0);

  const refresh = useCallback(
    (prefixes: string[] | null) =>
      mutate((key) => typeof key === "string" && (prefixes === null || prefixes.some((p) => key.startsWith(p))), undefined, { revalidate: true }),
    [mutate],
  );

  const handle = useCallback(
    (ev: LiveEvent) => {
      if (ev.id <= lastId.current) return;
      lastId.current = ev.id;
      setEvents((prev) => [ev, ...prev].slice(0, 60));
      if (ev.type === "scan_started") {
        setScan({ running: true, stage: "starting", progress: 0, stats: {} });
        refresh(["/api/overview"]);
      } else if (ev.type === "scan_progress") {
        setScan({ running: true, stage: ev.data.stage, progress: ev.data.progress, stats: ev.data.stats ?? {} });
      } else if (ev.type === "scan_finished") {
        setScan((s) => ({ ...s, running: false, stage: ev.data.status === "ok" ? "complete" : "failed", progress: 1 }));
        refresh(null);
      } else if (ev.type === "alert") {
        refresh(["/api/alerts", "/api/overview"]);
        if (typeof Notification !== "undefined" && Notification.permission === "granted" && ["medium", "high", "critical"].includes(ev.data.severity)) {
          try {
            new Notification(ev.data.title, { body: ev.data.message, tag: `oalgo-${ev.data.id}` });
          } catch {
            /* notifications unavailable in this context */
          }
        }
      } else if (ev.type === "portfolio") {
        refresh(["/api/portfolio"]);
      }
    },
    [refresh],
  );

  useEffect(() => {
    if (SNAPSHOT) {
      setMode("snapshot"); // no backend: nothing to stream or poll
      return;
    }
    if (typeof Notification !== "undefined") setNotifications(Notification.permission);
    // seed scan state so a page opened mid-scan shows progress immediately
    fetch(`${API_URL}/api/overview`)
      .then((r) => r.json())
      .then((o) => {
        const last = o?.scan?.last;
        if (o?.scan?.running && last) setScan({ running: true, stage: last.stage, progress: last.progress, stats: last.stats ?? {} });
      })
      .catch(() => {});

    let es: EventSource | null = null;
    let poll: ReturnType<typeof setInterval> | null = null;
    let closed = false;

    const startPolling = () => {
      if (poll || closed) return;
      setMode("polling");
      poll = setInterval(async () => {
        try {
          const r = await fetch(`${API_URL}/api/events/recent?after=${lastId.current}`);
          if (!r.ok) throw new Error(String(r.status));
          const list: LiveEvent[] = await r.json();
          list.forEach(handle);
          setMode("polling");
        } catch {
          setMode("offline");
        }
      }, 5000);
    };

    if (typeof EventSource === "undefined") {
      startPolling();
    } else {
      es = new EventSource(`${API_URL}/api/events`);
      es.onopen = () => {
        setMode("stream");
        if (poll) {
          clearInterval(poll);
          poll = null;
        }
      };
      es.onerror = () => startPolling(); // EventSource retries on its own; polling covers the gap
      const types = ["scan_started", "scan_progress", "scan_finished", "alert", "portfolio"];
      types.forEach((t) => es!.addEventListener(t, (e) => handle(JSON.parse((e as MessageEvent).data))));
    }
    return () => {
      closed = true;
      es?.close();
      if (poll) clearInterval(poll);
    };
  }, [handle]);

  const enableNotifications = useCallback(() => {
    if (typeof Notification === "undefined") return;
    Notification.requestPermission().then(setNotifications);
  }, []);

  const value = useMemo(() => ({ mode, scan, events, notifications, enableNotifications }), [mode, scan, events, notifications, enableNotifications]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
