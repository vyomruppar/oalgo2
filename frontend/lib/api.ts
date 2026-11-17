/* eslint-disable @typescript-eslint/no-explicit-any */
// Same-origin by default: Next forwards /api to the backend (see next.config.mjs).
// Set NEXT_PUBLIC_API_URL only to call a backend on another address directly.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export type J = any;

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

export const fetcher = (path: string): Promise<J> => fetch(`${API_URL}${path}`, { cache: "no-store" }).then(parse);

export function send(method: "POST" | "PUT" | "DELETE", path: string, body?: unknown): Promise<J> {
  return fetch(`${API_URL}${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).then(parse);
}
