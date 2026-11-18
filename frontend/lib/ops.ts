/**
 * Server-side helpers for the free hosted setup (GitHub Actions + Vercel). Dashboard changes are
 * encrypted and stored as files in the repository's `oalgo-queue` branch, then a GitHub Actions run
 * is started to apply them. Must match backend/app/queue.py.
 *
 * Format: base64( iv[12] | AES-256-GCM ciphertext | tag[16] ), key = QUEUE_KEY (hex, 32 bytes).
 */
export type Op = { method: "POST" | "PUT" | "DELETE"; path: string; body?: unknown; ts?: string };

export const QUEUE_BRANCH = "oalgo-queue";
export const WORKFLOW = "update.yml";

/** Changes the dashboard may queue; anything else (paper trading included) is refused. */
const ALLOWED: [string, RegExp][] = [
  ["POST", /^\/api\/scans$/],
  ["POST", /^\/api\/holdings$/],
  ["PUT", /^\/api\/holdings\/\d+$/],
  ["DELETE", /^\/api\/holdings\/\d+$/],
  ["POST", /^\/api\/holdings\/import$/],
  ["PUT", /^\/api\/config$/],
  ["POST", /^\/api\/news\/refresh(\?symbol=[A-Za-z.-]{1,12})?$/],
];

export function allowed(method: string, path: string): boolean {
  return ALLOWED.some(([m, re]) => m === method && re.test(path));
}

function hexToBytes(hex: string): Uint8Array {
  if (!/^[0-9a-f]{64}$/i.test(hex)) throw new Error("QUEUE_KEY must be 64 hex characters");
  return Uint8Array.from(hex.match(/../g)!.map((h) => parseInt(h, 16)));
}

function b64(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s);
}

/** HMAC-SHA256(secret, purpose) as hex: how the workflow derives QUEUE_KEY and AUTH_SECRET. */
export async function deriveHex(secret: string, purpose: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(purpose)));
  return Array.from(sig, (b) => b.toString(16).padStart(2, "0")).join("");
}

export async function encryptOp(op: Op, keyHex: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", hexToBytes(keyHex) as BufferSource, "AES-GCM", false, ["encrypt"]);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, new TextEncoder().encode(JSON.stringify(op))));
  const out = new Uint8Array(iv.length + ct.length);
  out.set(iv);
  out.set(ct, iv.length);
  return b64(out);
}

// ---- GitHub ---------------------------------------------------------------------------------------------
function gh(path: string, init: RequestInit = {}) {
  const token = process.env.GH_DISPATCH_TOKEN;
  const repo = process.env.GH_REPO;
  if (!token || !repo) throw new Error("GH_DISPATCH_TOKEN and GH_REPO must be set on the dashboard server");
  return fetch(`${process.env.GH_API_URL ?? "https://api.github.com"}/repos/${repo}${path}`, {
    ...init,
    cache: "no-store",
    headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "oalgo2-dashboard", ...(init.headers ?? {}) },
  });
}

async function ensureQueueBranch(): Promise<void> {
  const r = await gh(`/git/ref/heads/${QUEUE_BRANCH}`);
  if (r.ok) return;
  const repo = await (await gh("")).json();
  const head = await (await gh(`/git/ref/heads/${repo.default_branch}`)).json();
  const c = await gh("/git/refs", { method: "POST", body: JSON.stringify({ ref: `refs/heads/${QUEUE_BRANCH}`, sha: head.object.sha }) });
  if (!c.ok && c.status !== 422) throw new Error(`could not create the queue branch (GitHub ${c.status})`);
}

export async function enqueue(op: Op): Promise<void> {
  const keyHex = process.env.QUEUE_KEY;
  if (!keyHex) throw new Error("QUEUE_KEY must be set on the dashboard server");
  await ensureQueueBranch();
  const name = `${Date.now()}-${crypto.getRandomValues(new Uint32Array(1))[0].toString(36)}.enc`;
  const content = btoa(await encryptOp({ ...op, ts: new Date().toISOString() }, keyHex));
  const r = await gh(`/contents/queue/${name}`, { method: "PUT", body: JSON.stringify({ message: "Queue a dashboard change", content, branch: QUEUE_BRANCH }) });
  if (!r.ok) throw new Error(`could not save the change (GitHub ${r.status})`);
}

export async function dispatch(): Promise<void> {
  const repo = await (await gh("")).json();
  const r = await gh(`/actions/workflows/${WORKFLOW}/dispatches`, { method: "POST", body: JSON.stringify({ ref: repo.default_branch }) });
  if (!r.ok) throw new Error(`could not start an update (GitHub ${r.status})`);
}

export type UpdateStatus = { running: boolean; started_at: string | null; queued_changes: number; last_finished_at: string | null; last_conclusion: string | null };

export async function status(): Promise<UpdateStatus> {
  const [runsR, queueR] = await Promise.all([gh(`/actions/workflows/${WORKFLOW}/runs?per_page=5`), gh(`/contents/queue?ref=${QUEUE_BRANCH}`)]);
  const runs = runsR.ok ? (await runsR.json()).workflow_runs ?? [] : [];
  const active = runs.find((r: { status: string }) => r.status !== "completed");
  const done = runs.find((r: { status: string }) => r.status === "completed");
  const files = queueR.ok ? await queueR.json() : [];
  return {
    running: Boolean(active),
    started_at: active?.run_started_at ?? null,
    queued_changes: Array.isArray(files) ? files.filter((f: { name: string }) => f.name.endsWith(".enc")).length : 0,
    last_finished_at: done?.updated_at ?? null,
    last_conclusion: done?.conclusion ?? null,
  };
}
