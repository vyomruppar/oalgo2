import { NextResponse } from "next/server";
import { status } from "@/lib/ops";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    return NextResponse.json(await status());
  } catch (e) {
    return NextResponse.json({ detail: e instanceof Error ? e.message : String(e) }, { status: 502 });
  }
}
