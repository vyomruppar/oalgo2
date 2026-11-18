import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { authEnabled, checkPassword, createSession, safeEqual, verifySession } from "@/lib/auth";

describe("login sessions", () => {
  beforeEach(() => {
    process.env.APP_PASSWORD = "correct horse battery";
    process.env.AUTH_SECRET = "a".repeat(48);
  });
  afterEach(() => {
    delete process.env.APP_PASSWORD;
    delete process.env.AUTH_SECRET;
  });

  it("is off when no password is configured", () => {
    delete process.env.APP_PASSWORD;
    expect(authEnabled()).toBe(false);
    expect(checkPassword("")).toBe(false);
  });

  it("checks the password exactly", () => {
    expect(checkPassword("correct horse battery")).toBe(true);
    expect(checkPassword("correct horse batter")).toBe(false);
    expect(checkPassword("correct horse battery ")).toBe(false);
    expect(safeEqual("abc", "abc")).toBe(true);
    expect(safeEqual("abc", "abd")).toBe(false);
    expect(safeEqual("abc", "ab")).toBe(false);
  });

  it("accepts its own sessions and rejects tampered, expired or foreign ones", async () => {
    const t = await createSession();
    expect(await verifySession(t)).toBe(true);
    const [exp, sig] = t.split(".");
    expect(await verifySession(`${Number(exp) + 999999}.${sig}`)).toBe(false); // extended expiry
    expect(await verifySession(`${exp}.${sig.replace(/^./, sig[0] === "0" ? "1" : "0")}`)).toBe(false);
    expect(await verifySession(undefined)).toBe(false);
    expect(await verifySession("garbage")).toBe(false);
    expect(await verifySession(t, Date.now() + 31 * 86400 * 1000)).toBe(false); // past 30 days
    process.env.AUTH_SECRET = "b".repeat(48);
    expect(await verifySession(t)).toBe(false); // signed with another secret
  });

  it("refuses to run with a weak secret", async () => {
    process.env.AUTH_SECRET = "short";
    await expect(createSession()).rejects.toThrow(/AUTH_SECRET/);
  });
});
