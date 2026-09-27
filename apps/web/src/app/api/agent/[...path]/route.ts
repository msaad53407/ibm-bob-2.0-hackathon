import { NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";

/**
 * Agent forwarder (Slices A+B): browser calls same-origin /api/agent/*.
 * Requires a logged-in session (401 otherwise), injects ADMIN_TOKEN for the
 * service-to-service leg, and stamps the session email as the approver on
 * /execute so the audit trail carries real identity. The client-sent
 * approver is ignored — the server value is authoritative.
 */

const AGENT_URL = (process.env.AGENT_URL ?? "http://localhost:8003").replace(/\/$/, "");

// Only these agent paths are exposed through the dashboard.
const ALLOWED = new Set(["decide", "propose", "execute", "proposals", "audit", "health"]);

async function authedEmail(req: NextRequest, res: NextResponse) {
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => req.cookies.getAll(),
        setAll: (cookiesToSet) => {
          cookiesToSet.forEach(({ name, value, options }) =>
            res.cookies.set(name, value, options),
          );
        },
      },
    },
  );
  const {
    data: { user },
  } = await supabase.auth.getUser();
  return user?.email ?? null;
}

async function forward(req: NextRequest, path: string[]) {
  const [first, ...rest] = path;
  if (!first || !ALLOWED.has(first)) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  const token = process.env.ADMIN_TOKEN;
  if (!token) {
    return NextResponse.json({ error: "server misconfigured" }, { status: 500 });
  }

  // Session gate + refresh holder (cookies propagate onto the response below).
  const res = NextResponse.next({ request: req });
  const email = await authedEmail(req, res);
  if (!email) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const url = `${AGENT_URL}/${[first, ...rest].join("/")}${new URL(req.url).search}`;
  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  let body: ArrayBuffer | string | undefined;
  if (hasBody) {
    if (first === "execute") {
      // Authoritative approver: session email replaces whatever the client sent.
      const raw = (await req.json()) as Record<string, unknown>;
      raw.approver = email;
      body = JSON.stringify(raw);
    } else {
      body = await req.arrayBuffer();
    }
  }
  const { res: upstream, reachable } = await fetchAgent(url, req.method, token, body);
  if (!reachable) {
    // Say which service is down — a bare 500 "fetch failed" sends you hunting
    // through the dashboard instead of straight to the container logs.
    return NextResponse.json(
      {
        error: "agent unreachable",
        detail: "workers/agent is not responding — docker compose ps -a, then docker compose logs agent",
      },
      { status: 503 },
    );
  }
  const text = await upstream.text();
  const out = new NextResponse(text, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") ?? "application/json",
    },
  });
  for (const c of res.cookies.getAll()) out.cookies.set(c.name, c.value);
  return out;
}

type Ctx = { params: Promise<{ path: string[] }> };

/**
 * Call the internal agent. A rejected connection means the container is gone
 * (it exits on an import error, and plain `docker compose ps` hides exited
 * containers — use `docker compose ps -a`), which is worth distinguishing
 * from a real upstream status.
 */
async function fetchAgent(
  url: string,
  method: string,
  token: string,
  body: ArrayBuffer | string | undefined,
): Promise<{ res: Response; reachable: boolean }> {
  try {
    const res = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body,
    });
    return { res, reachable: true };
  } catch {
    return { res: new Response(null, { status: 503 }), reachable: false };
  }
}

export async function GET(req: NextRequest, ctx: Ctx) {
  return forward(req, (await ctx.params).path);
}

export async function POST(req: NextRequest, ctx: Ctx) {
  return forward(req, (await ctx.params).path);
}
