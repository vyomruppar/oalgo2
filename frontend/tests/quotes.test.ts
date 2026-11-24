import { describe, expect, it } from "vitest";
import { applyQuotes, weekdaysBetween } from "@/lib/quotes";

const holdings = {
  positions: [
    { symbol: "MU", shares: 30, invested: 2892, value: 21570.6, price: 719.02, day_change_pct: -0.076, day_change: -1778, gain: 18679, gain_pct: 6.45, weight: 0.5 },
    { symbol: "KO", shares: 100, invested: 6000, value: 10017, price: 100.17, day_change_pct: 0.001, day_change: 10, gain: 4017, gain_pct: 0.67, weight: 0.5 },
  ],
  value: 31587.6, invested: 8892, gain: 22695, n_positions: 2,
};
const quote = (price: number, prev: number, open = true) => ({ price, prev_close: prev, change: price - prev, change_pct: price / prev - 1, time: "2026-11-24T17:27:00Z", market_open: open });

describe("live quotes", () => {
  it("re-prices holdings, today's change, gain, weights and totals", () => {
    const out = applyQuotes(holdings, { quotes: { MU: quote(632.55, 707.7) }, market_open: true, returned: 1, requested: 2, fetched_at: "2026-11-24T17:28:00Z" });
    const mu = out.positions.find((p: any) => p.symbol === "MU");
    expect(mu.price).toBe(632.55);
    expect(mu.value).toBeCloseTo(18976.5);
    expect(mu.day_change_pct).toBeCloseTo(-0.10619, 4);
    expect(mu.day_change).toBeCloseTo(-2254.5);
    expect(mu.gain).toBeCloseTo(18976.5 - 2892);
    expect(out.positions.find((p: any) => p.symbol === "KO").price).toBe(100.17);  // no quote: keeps the stored price
    expect(out.value).toBeCloseTo(18976.5 + 10017);
    const w = out.positions.map((p: any) => p.weight).reduce((a: number, b: number) => a + b, 0);
    expect(w).toBeCloseTo(1);
    expect(out.day_change).toBeCloseTo(-2254.5 + 10);
    expect(out.live).toBe(true);
  });

  it("leaves holdings untouched when there are no quotes", () => {
    expect(applyQuotes(holdings, undefined)).toBe(holdings);
    expect(applyQuotes(holdings, { quotes: {}, market_open: false, returned: 0, requested: 2, fetched_at: "" })).toBe(holdings);
  });

  it("counts whole weekdays since a date", () => {
    expect(weekdaysBetween("2026-11-16", new Date(2026, 10, 24))).toBe(6);   // Mon 16th -> Tue 24th
    expect(weekdaysBetween("2026-11-20", new Date(2026, 10, 23))).toBe(1);   // Fri -> Mon
    expect(weekdaysBetween("2026-11-24", new Date(2026, 10, 24))).toBe(0);
    expect(weekdaysBetween(null)).toBe(0);
  });
});
