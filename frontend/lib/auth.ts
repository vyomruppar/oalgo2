/**
 * Single-password login for hosted deployments. A session is "<expiry>.<hmac>" signed with
 * AUTH_SECRET using Web Crypto, so it works in both the Edge middleware and Node route handlers.
 * When APP_PASSWORD is not set (local use) authentication is off.
 */
export const COOKIE = "oalgo_session";
export const SESSION_DAYS = 30;

export function authEnabled(): boolean {
  return Boolean(process.env.APP_PASSWORD);
}

function secret(): string {
  const s = process.env.AUTH_SECRET;
  if (!s || s.length < 32) throw new Error("AUTH_SECRET must be set to at least 32 random characters when APP_PASSWORD is set");
  return s;
}

const enc = new TextEncoder();

async function hmac(data: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret()), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(data)));
  return Array.from(sig, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Length-safe comparison that does not stop at the first differing character. */
export function safeEqual(a: string, b: string): boolean {
  const x = enc.encode(a);
  const y = enc.encode(b);
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) diff |= (x[i] ?? 0) ^ (y[i] ?? 0);
  return diff === 0;
}

export async function createSession(now: number = Date.now()): Promise<string> {
  const exp = Math.floor(now / 1000) + SESSION_DAYS * 86400;
  return `${exp}.${await hmac(`v1.${exp}`)}`;
}

export async function verifySession(token: string | undefined, now: number = Date.now()): Promise<boolean> {
  if (!token) return false;
  const [exp, sig] = token.split(".");
  if (!exp || !sig || !/^\d+$/.test(exp) || Number(exp) * 1000 < now) return false;
  return safeEqual(sig, await hmac(`v1.${exp}`));
}

export function checkPassword(given: string): boolean {
  const want = process.env.APP_PASSWORD ?? "";
  return want.length > 0 && safeEqual(given, want);
}
