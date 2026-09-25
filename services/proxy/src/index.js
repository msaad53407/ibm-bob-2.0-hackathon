import express from "express";
import { createProxyMiddleware, fixRequestBody } from "http-proxy-middleware";
import { createClient } from "@supabase/supabase-js";
import { randomUUID } from "node:crypto";
import { z } from "zod";

// ── Env validation ────────────────────────────────────────────────────────────
// Fails fast at startup with a clear message rather than a cryptic runtime error.
const EnvSchema = z.object({
  PORT:                 z.coerce.number().int().positive().default(8080),
  STABLE_URL:           z.string().url().default("http://stable:8000"),
  CANARY_URL:           z.string().url().default("http://canary:8000"),
  SUPABASE_URL:         z.string().url({ message: "SUPABASE_URL must be a valid URL" }),
  SUPABASE_SERVICE_KEY: z.string().min(1, { message: "SUPABASE_SERVICE_KEY is required" }),
});

const envResult = EnvSchema.safeParse(process.env);
if (!envResult.success) {
  console.error("❌  Missing or invalid environment variables:\n");
  for (const issue of envResult.error.issues) {
    console.error(`  ${issue.path.join(".")}: ${issue.message}`);
  }
  process.exit(1);
}
const env = envResult.data;

const PORT        = env.PORT;
const STABLE_URL  = env.STABLE_URL;
const CANARY_URL  = env.CANARY_URL;
const SUPABASE_URL  = env.SUPABASE_URL;
const SUPABASE_KEY  = env.SUPABASE_SERVICE_KEY;

// ── ServiceName — mirrors packages/contracts/src/index.ts ────────────────────
const SERVICE = {
  STABLE: "stable",
  CANARY: "canary",
  PROXY_EVENT: "proxy",
  proxyTraffic: (t) => `proxy->${t}`,
};
const ERROR_THRESHOLD = 500;
const ERROR_MSG_MAX_LEN = 500;

/** Constructs a LogRow using the shared convention. */
function makeLogRow({ service, endpoint, status_code, latency_ms, error_text = null }) {
  const isError = status_code >= ERROR_THRESHOLD;
  return {
    timestamp: new Date().toISOString(),
    service,
    endpoint,
    status_code,
    latency_ms,
    error_message: isError
      ? (error_text ? String(error_text).slice(0, ERROR_MSG_MAX_LEN) : `error status ${status_code}`)
      : null,
    trace_id: randomUUID(),
  };
}

let target = "stable";
const targets = { stable: STABLE_URL, canary: CANARY_URL };

const supabase =
  SUPABASE_URL && SUPABASE_KEY
    ? createClient(SUPABASE_URL, SUPABASE_KEY)
    : null;

async function logRow(row) {
  if (!supabase) return;
  try {
    await supabase.from("logs").insert(row);
  } catch {
    // never block proxying on logging
  }
}

const app = express();
app.use(express.json());

app.get("/health", (_req, res) => res.json({ ok: true, target }));

app.get("/admin/route", (_req, res) => res.json({ target }));

// Execution endpoint: the only promote/rollback mechanism (ADR-0002)
app.post("/admin/route", async (req, res) => {
  const next = req.body?.target;
  if (next !== SERVICE.STABLE && next !== SERVICE.CANARY) {
    return res.status(400).json({ error: 'target must be "stable" | "canary"' });
  }
  target = next;
  // Log the flip as a PROXY_EVENT (not proxy traffic — this is an admin action)
  await logRow({
    ...makeLogRow({
      service: SERVICE.PROXY_EVENT,
      endpoint: "/admin/route",
      status_code: 200,
      latency_ms: 0,
      error_text: `traffic flip to ${target}`,
    }),
    // Override error_message: flips are not errors even though we carry a message
    error_message: `traffic flip to ${target}`,
  });
  res.json({ target });
});

app.use(async (req, res, next) => {
  const started = Date.now();
  res.on("finish", () => {
    void logRow(makeLogRow({
      service: SERVICE.proxyTraffic(target),
      endpoint: req.originalUrl,
      status_code: res.statusCode,
      latency_ms: Date.now() - started,
      error_text: res.statusCode >= ERROR_THRESHOLD ? `proxy saw ${res.statusCode}` : null,
    }));
  });
  next();
});

app.use(
  "/",
  createProxyMiddleware({
    router: () => targets[target],
    changeOrigin: true,
    on: { proxyReq: fixRequestBody },
    logger: console,
  })
);

app.listen(PORT, () => console.log(`proxy on :${PORT} -> ${target}`));
