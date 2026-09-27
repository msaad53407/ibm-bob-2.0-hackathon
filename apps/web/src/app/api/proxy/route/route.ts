import { NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";

/**
 * Proxy status forwarder (Slices A+B): browser calls same-origin
 * /api/proxy/route, the server reads the internal proxy target.
 * Requires a logged-in session. GET /admin/route stays open on the proxy,
 * but the browser no longer needs the internal hostname — and stays working
 * once proxy ports close.
 */

const PROXY_BASE_URL = (process.env.PROXY_BASE_URL ?? "http://proxy:8080").replace(/\/$/, "");

export async function GET(req: NextRequest) {
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { cookies: { getAll: () => req.cookies.getAll(), setAll: () => {} } },
  );
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const res = await fetch(`${PROXY_BASE_URL}/admin/route`);
  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("content-type") ?? "application/json" },
  });
}
