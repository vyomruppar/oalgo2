import { describe, expect, it } from "vitest";
import { fmtCompact, fmtMoney, fmtNum, fmtPct, regimeLabel, scoreColor, signalStyle, signClass, timeAgo, titleCase } from "@/lib/format";

describe("number formatting", () => {
  it("never renders missing values as zero", () => {
    for (const v of [null, undefined, NaN, Infinity]) {
      expect(fmtNum(v as number)).toBe("—");
      expect(fmtPct(v as number)).toBe("—");
      expect(fmtCompact(v as number)).toBe("—");
      expect(fmtMoney(v as number)).toBe("—");
    }
  });
  it("formats percentages and signs", () => {
    expect(fmtPct(0.1234)).toBe("12.3%");
    expect(fmtPct(0.1234, 2, true)).toBe("+12.34%");
    expect(fmtPct(-0.05, 1, true)).toBe("-5.0%");
  });
  it("formats compact magnitudes", () => {
    expect(fmtCompact(3.859e12, "$")).toBe("$3.86T");
    expect(fmtCompact(431e9)).toBe("431.00B");
    expect(fmtCompact(-5.2e6)).toBe("-5.2M");
    expect(fmtCompact(950)).toBe("950");
  });
  it("formats money", () => {
    expect(fmtMoney(1234.5)).toBe("$1,234.50");
    expect(fmtMoney(-12)).toBe("-$12.00");
  });
});

describe("labels", () => {
  it("maps every signal to a label", () => {
    expect(signalStyle("STRONG BUY").label).toBe("Strong buy");
    expect(signalStyle("NO_ACTION").label).toBe("No action");
    expect(signalStyle(null).label).toBe("Screened out");
  });
  it("maps regimes", () => {
    expect(regimeLabel("risk_off").label).toBe("Risk-off");
    expect(regimeLabel(undefined).label).toBe("Unknown");
  });
  it("colours by sign and score", () => {
    expect(signClass(0.1)).toBe("text-up");
    expect(signClass(-0.1)).toBe("text-down");
    expect(signClass(null)).toBe("text-dim");
    expect(scoreColor(100)).toBe("rgb(74 190 142)");
    expect(scoreColor(0)).toBe("rgb(232 104 104)");
    expect(scoreColor(null)).toBe("rgb(98 107 121)");
  });
  it("relative time", () => {
    const now = Date.parse("2026-11-16T12:00:00Z");
    expect(timeAgo("2026-11-16T11:59:30Z", now)).toBe("30s ago");
    expect(timeAgo("2026-11-16T09:00:00Z", now)).toBe("3h ago");
    expect(timeAgo(null, now)).toBe("never");
  });
  it("title case", () => expect(titleCase("out_of_sample")).toBe("Out Of Sample"));
});
