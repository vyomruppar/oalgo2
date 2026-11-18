import { NextResponse, type NextRequest } from "next/server";
import { authEnabled, COOKIE, verifySession } from "@/lib/auth";

/**
 * Hosted deployments (APP_PASSWORD set):
 *   - every page and API call needs a valid login cookie
 *   - /api/* is forwarded to the research backend (BACKEND_URL) with the shared X-Backend-Key header,
 *     so the browser never sees the backend's address or key
 * Local use (APP_PASSWORD unset): no login; next.config.mjs forwards /api to the local backend.
 */
export async function middleware(req: NextRequest) {
  if (!authEnabled()) return NextResponse.next();
  const { pathname, search } = req.nextUrl;
  if (pathname === "/login" || pathname.startsWith("/auth/")) return NextResponse.next();

  const ok = await verifySession(req.cookies.get(COOKIE)?.value);
  const isApi = pathname.startsWith("/api/");
  if (!ok) {
    if (isApi) return NextResponse.json({ detail: "Sign in to use the dashboard." }, { status: 401 });
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = pathname === "/" ? "" : `?next=${encodeURIComponent(pathname + search)}`;
    return NextResponse.redirect(url);
  }

  if (isApi) {
    const backend = process.env.BACKEND_URL;
    if (!backend) return NextResponse.json({ detail: "BACKEND_URL is not configured on the dashboard server." }, { status: 503 });
    const headers = new Headers(req.headers);
    headers.set("x-backend-key", process.env.BACKEND_API_KEY ?? "");
    headers.delete("cookie"); // the backend has no use for the dashboard's session cookie
    return NextResponse.rewrite(new URL(pathname + search, backend), { request: { headers } });
  }
  return NextResponse.next();
}

export const config = {
  // everything except Next's own static files and the favicon
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
