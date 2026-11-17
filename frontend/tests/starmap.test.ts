import { describe, expect, it } from "vitest";
import { hash01, layoutStars, nearestStar, type StarInput } from "@/lib/starmap";

const mk = (symbol: string, sector: string, cap: number, extra: Partial<StarInput> = {}): StarInput => ({
  symbol, sector, market_cap: cap, score: 50, signal: "HOLD", price: 10, ret_1d: 0, held: false, screen_pass: true, company: symbol, ...extra,
});

const universe: StarInput[] = [
  mk("AAA", "Technology", 3e12), mk("AAB", "Technology", 5e10), mk("AAC", "Technology", 2e9),
  mk("BBA", "Energy", 4e11), mk("BBB", "Energy", 1e10),
  mk("CCA", "Financials", 8e11, { held: true, signal: "BUY", score: 90 }),
];

describe("star map layout", () => {
  it("is deterministic", () => {
    expect(layoutStars(universe, 900, 520)).toEqual(layoutStars([...universe].reverse(), 900, 520));
    expect(hash01("AAPL", 1)).toBe(hash01("AAPL", 1));
    expect(hash01("AAPL", 1)).not.toBe(hash01("AAPL", 2));
  });

  it("keeps every star inside the canvas", () => {
    for (const [w, h] of [[900, 520], [360, 420], [1400, 600]]) {
      const { stars } = layoutStars(universe, w, h);
      for (const s of stars) {
        expect(s.x).toBeGreaterThan(0);
        expect(s.x).toBeLessThan(w);
        expect(s.y).toBeGreaterThan(0);
        expect(s.y).toBeLessThan(h);
      }
    }
  });

  it("puts one arm per sector, largest sector first, and bigger companies nearer the core", () => {
    const { stars, arms } = layoutStars(universe, 900, 520);
    expect(arms.map((a) => a.sector)).toEqual(["Technology", "Energy", "Financials"]);
    const dist = (sym: string) => {
      const s = stars.find((x) => x.symbol === sym)!;
      return Math.hypot(s.x - 450, (s.y - 260) / Math.min(0.62, (520 * 0.46) / Math.min(900 * 0.47, 520 * 0.8)));
    };
    expect(dist("AAA")).toBeLessThan(dist("AAB"));
    expect(dist("AAB")).toBeLessThan(dist("AAC"));
  });

  it("encodes size, glow and colour from the data", () => {
    const { stars } = layoutStars(universe, 900, 520);
    const get = (sym: string) => stars.find((x) => x.symbol === sym)!;
    expect(get("AAA").r).toBeGreaterThan(get("AAC").r);
    expect(get("CCA").alpha).toBeGreaterThan(get("AAA").alpha);
    expect(get("CCA").color).toBe("#3df2c4");
    const unscored = layoutStars([mk("ZZZ", "Other", 1e9, { score: null, signal: null })], 900, 520).stars[0];
    expect(unscored.alpha).toBeLessThan(0.3);
    expect(unscored.color).toBe("#565e93");
  });

  it("finds the nearest star and ignores far clicks", () => {
    const { stars } = layoutStars(universe, 900, 520);
    const target = stars[2];
    expect(stars[nearestStar(stars, target.x + 2, target.y - 2)].symbol).toBe(target.symbol);
    expect(nearestStar(stars, -500, -500)).toBe(-1);
  });
});
