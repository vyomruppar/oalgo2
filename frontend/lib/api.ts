/* eslint-disable @typescript-eslint/no-explicit-any */
// Same-origin by default: Next forwards /api to the backend (see next.config.mjs).
// Set NEXT_PUBLIC_API_URL only to call a backend on another address directly.
import { SnapshotMissing, snapshotFetch } from "./snapshot";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export type J = any;

/** True in the static, read-only build (no backend): data comes from exported JSON files. */
export const SNAPSHOT = process.env.NEXT_PUBLIC_SNAPSHOT === "1";
/** Free hosted setup: data comes from files published by GitHub Actions; changes are queued for the next run. */
export const QUEUED = SNAPSHOT && process.env.NEXT_PUBLIC_QUEUE === "1";
/** No way to save anything: a plain read-only copy. */
export const NO_WRITES = SNAPSHOT && !QUEUED;
export const READ_ONLY = "This is a read-only snapshot. Run the app on your computer to do this.";
export const NOT_IN_FREE = "Paper trading is not available in the free hosted version. Run the app on your computer to use it.";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function parse(r: Response): Promise<J> {
  if (r.ok) return r.json();
  let detail = r.statusText;
  try {
    const body = await r.json();
    detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
  } catch {
    /* keep status text */
  }
  throw new ApiError(r.status, detail);
}

export const fetcher = (path: string): Promise<J> =>
  SNAPSHOT
    ? snapshotFetch(path).catch((e) => {
        throw new ApiError(e instanceof SnapshotMissing ? 404 : 500, e instanceof Error ? e.message : String(e));
      })
    : fetch(`${API_URL}${path}`, { cache: "no-store" }).then(parse);

export function send(method: "POST" | "PUT" | "DELETE", path: string, body?: unknown): Promise<J> {
  if (QUEUED) {
    // queued for the next GitHub Actions run; the server encrypts it and starts the run
    return fetch("/ops", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ method, path, body }) }).then(parse);
  }
  if (SNAPSHOT) return Promise.reject(new ApiError(405, READ_ONLY));
  return fetch(`${API_URL}${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).then(parse);
}
