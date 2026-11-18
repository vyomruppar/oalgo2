import { NextResponse, type NextRequest } from "next/server";
import { allowed, dispatch, enqueue, type Op } from "@/lib/ops";

/**
 * Free hosted setup: accept a dashboard change, store it encrypted in the queue, and start an update
 * run. The login middleware has already checked the session before this runs.
 */
export async function POST(req: NextRequest) {
  let op: Op;
  try {
    const b = await req.json();
    op = { method: String(b.method).toUpperCase() as Op["method"], path: String(b.path), body: b.body ?? undefined };
  } catch {
    return NextResponse.json({ detail: "The request could not be read." }, { status: 400 });
  }
  if (!allowed(op.method, op.path)) {
    return NextResponse.json({ detail: "This change is not available in the free hosted version." }, { status: 400 });
  }
  if (JSON.stringify(op.body ?? null).length > 100_000) {
    return NextResponse.json({ detail: "That is too much data for one change." }, { status: 413 });
  }
  try {
    await enqueue(op);
    await dispatch();
  } catch (e) {
    return NextResponse.json({ detail: `The change was not saved: ${e instanceof Error ? e.message : String(e)}` }, { status: 502 });
  }
  const what = op.path === "/api/scans" ? "The scan has started" : "Saved";
  const wait = op.path === "/api/scans" ? "about 15 minutes" : "about 5 minutes";
  return NextResponse.json({ queued: true, message: `${what}. It will show here after the next update, in ${wait}.` });
}
