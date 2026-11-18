import { describe, expect, it } from "vitest";
import { allowed, deriveHex, encryptOp } from "@/lib/ops";

describe("queued changes", () => {
  it("allows only the changes the update run will replay", () => {
    expect(allowed("POST", "/api/scans")).toBe(true);
    expect(allowed("POST", "/api/holdings")).toBe(true);
    expect(allowed("DELETE", "/api/holdings/7")).toBe(true);
    expect(allowed("PUT", "/api/config")).toBe(true);
    expect(allowed("POST", "/api/news/refresh?symbol=BRK-B")).toBe(true);
    expect(allowed("POST", "/api/portfolio/orders")).toBe(false);
    expect(allowed("POST", "/api/portfolio/reset")).toBe(false);
    expect(allowed("PUT", "/api/holdings/1/../x")).toBe(false);
    expect(allowed("GET", "/api/holdings")).toBe(false);
  });

  it("derives keys the same way as the update run", async () => {
    // value from backend: queue.derive_hex("s" * 40, "oalgo2-queue-v1")
    const k = await deriveHex("s".repeat(40), "oalgo2-queue-v1");
    expect(k).toBe("8badf0cc3b60c07eded5fb4b25950d0aba4ec22014d11e663263d607345331f2");
    expect(await deriveHex("s".repeat(40), "oalgo2-queue-v1")).toBe(k);
    expect(await deriveHex("s".repeat(40), "oalgo2-auth-v1")).not.toBe(k);
  });

  it("encrypts with a fresh nonce and no readable content", async () => {
    const key = "ab".repeat(32);
    const op = { method: "POST" as const, path: "/api/holdings", body: { symbol: "AAPL" } };
    const a = await encryptOp(op, key);
    const b = await encryptOp(op, key);
    expect(a).not.toBe(b);
    expect(atob(a)).not.toContain("AAPL");
    expect(atob(a).length).toBe(12 + JSON.stringify(op).length + 16);
    await expect(encryptOp(op, "short")).rejects.toThrow(/QUEUE_KEY/);
  });
});
