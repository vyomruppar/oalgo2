/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import useSWR from "swr";
import { useMemo } from "react";
import { fetcher, SNAPSHOT, type J } from "./api";

export type Quote = { price: number; prev_close: number; change: number; change_pct: number; time: string; market_open: boolean };
export type Quotes = { quotes: Record<string, Quote>; market_open: boolean; returned: number; requested: number; fetched_at: string } | undefined;

/** Delayed (about 15 minute) prices. Polls every 30s while the market is open, every 5 minutes otherwise. */
export function useQuotes(symbols: string[] | null): Quotes {
  const key = symbols && symbols.length && !SNAPSHOT ? `/api/quotes?symbols=${[...new Set(symbols)].sort().join(",")}` : null;
  const { data } = useSWR<J>(key, fetcher, {
    revalidateOnFocus: true,
    refreshInterval: (d) => (!d || d.returned < d.requested ? 10_000 : d.market_open ? 30_000 : 300_000), // retry quickly after a throttled reply
    errorRetryCount: 2,
    keepPreviousData: true,
  });
  return data;
}

/** Re-price holdings with live quotes: price, today's change, value, gain, weights and totals. */
export function applyQuotes(h: J, q: Quotes): J {
  if (!h || !q || !q.returned) return h;
  const positions = h.positions.map((p: J) => {
    const x = q.quotes[p.symbol];
    if (!x) return p;
    const value = x.price * p.shares;
    return { ...p, price: x.price, price_date: x.time.slice(0, 10), live: true, market_open: x.market_open, value,
             day_change_pct: x.change_pct, day_change: x.change * p.shares, gain: value - p.invested,
             gain_pct: p.invested > 0 ? value / p.invested - 1 : null };
  });
  const priced = positions.filter((p: J) => p.value != null);
  const value = priced.reduce((a: number, p: J) => a + p.value, 0);
  const invested = priced.reduce((a: number, p: J) => a + p.invested, 0);
  const day = positions.reduce((a: number, p: J) => a + (p.day_change ?? 0), 0);
  return {
    ...h,
    positions: positions.map((p: J) => ({ ...p, weight: p.value != null && value > 0 ? p.value / value : null })),
    value, gain: value - invested, gain_pct: invested > 0 ? value / invested - 1 : null,
    day_change: day, day_change_pct: value - day > 0 ? day / (value - day) : null,
    live: true, live_time: q.fetched_at, market_open: q.market_open,
  };
}

/** Whole weekdays between two ISO dates (a stored price date and today). */
export function weekdaysBetween(fromIso: string | null | undefined, to: Date = new Date()): number {
  if (!fromIso) return 0;
  const d = new Date(`${fromIso}T00:00:00`);
  let n = 0;
  while (d < new Date(to.getFullYear(), to.getMonth(), to.getDate())) {
    d.setDate(d.getDate() + 1);
    if (d.getDay() !== 0 && d.getDay() !== 6) n++;
  }
  return n;
}

export function useLiveHoldings(h: J): { h: J; q: Quotes } {
  const q = useQuotes(h ? h.positions.map((p: J) => p.symbol) : null);
  return { h: useMemo(() => applyQuotes(h, q), [h, q]), q };
}
