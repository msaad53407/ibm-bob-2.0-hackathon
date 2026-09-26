import { NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";

/**
 * Traffic-runner trigger forwarder: browser calls same-origin
 * POST /api/traffic/run, the server forwards to the internal
 * traffic-runner POST /run with ADMIN_TOKEN. Requires a logged-in
 * session (401 otherwise). Mirrors the agent forwarder pattern so
 * ADMIN_TOKEN never leaves the server.
 */

const TRAFFIC_RUNNER_URL = (
  process.env.TRAFFIC_RUNNER_URL ?? "http://traffic-runner:8004"
).replace(/\/$/, "");

export async function POST(req: NextRequest) {
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
  const token = process.env.ADMIN_TOKEN;
  if (!token) {
    return NextResponse.json({ error: "server misconfigured" }, { status: 500 });
  }
  // Optional { target_id } passes through for external-target runs;
  // absent body preserves the demo-batch behavior.
  let body: string | undefined;
  try {
    const raw = await req.text();
    body = raw || undefined;
  } catch {
    body = undefined;
  }
  const upstream = await fetch(`${TRAFFIC_RUNNER_URL}/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body,
  });
  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
