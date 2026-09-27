import { NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";

/**
 * Traffic-runner forwarder (BYO-API): browser calls same-origin
 * /api/runner/*, the server injects ADMIN_TOKEN and forwards to the
 * internal runner. Requires a logged-in session (401 otherwise).
 * On POST /targets the session email is stamped as owner_email —
 * the client-sent value is ignored.
 */

const RUNNER_URL = (
  process.env.TRAFFIC_RUNNER_URL ?? "http://traffic-runner:8004"
).replace(/\/$/, "");

// Runner paths exposed through the dashboard.
const ALLOWED = new Set(["targets", "run", "health"]);

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
  // Targets sub-routes: /targets and /targets/{id}/cases only.
  if (first === "targets" && rest.length > 2) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  if (first === "targets" && rest.length === 1 && rest[0] === "cases") {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  const token = process.env.ADMIN_TOKEN;
  if (!token) {
    return NextResponse.json({ error: "server misconfigured" }, { status: 500 });
  }

  const res = NextResponse.next({ request: req });
  const email = await authedEmail(req, res);
  if (!email) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const url = `${RUNNER_URL}/${[first, ...rest].join("/")}${new URL(req.url).search}`;
  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  let body: ArrayBuffer | string | undefined;
  if (hasBody) {
    if (first === "targets" && rest.length === 0) {
      // Authoritative owner: session email replaces whatever was sent.
      const raw = (await req.json()) as Record<string, unknown>;
      raw.owner_email = email;
      body = JSON.stringify(raw);
    } else {
      body = await req.arrayBuffer();
    }
  } else if (first === "targets" && rest.length === 0) {
    // Owner-scoped listing: runner filters by owner email.
    let upstream: Response;
    try {
      upstream = await fetch(
        `${RUNNER_URL}/targets?owner=${encodeURIComponent(email)}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
    } catch {
      return runnerDown();
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
  let upstream: Response;
  try {
    upstream = await fetch(url, {
      method: req.method,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body,
    });
  } catch {
    return runnerDown();
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

/** Name the service that is down instead of surfacing a bare 500. */
function runnerDown(): NextResponse {
  return NextResponse.json(
    {
      error: "traffic-runner unreachable",
      detail:
        "workers/traffic-runner is not responding — docker compose ps -a, then docker compose logs traffic-runner",
    },
    { status: 503 },
  );
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  return forward(req, (await ctx.params).path);
}

export async function POST(req: NextRequest, ctx: Ctx) {
  return forward(req, (await ctx.params).path);
}
