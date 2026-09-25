import express from "express";
import { createProxyMiddleware, fixRequestBody } from "http-proxy-middleware";
import { createClient } from "@supabase/supabase-js";
import { ServiceName, isError, makeLogRow } from "@guardrail/contracts";
import { z } from "zod";

// ── Config adapter ──────────────────────────────────────────────────────────
// Fails fast at startup with a clear message rather than a cryptic runtime error.
const EnvSchema = z.object({
  PORT:                 z.coerce.number().int().positive().default(8080),
  STABLE_URL:           z.string().url().default("http://stable:8000"),
  CANARY_URL:           z.string().url().default("http://canary:8000"),
  SUPABASE_URL:         z.string().url({ message: "SUPABASE_URL must be a valid URL" }),
  SUPABASE_SERVICE_KEY: z.string().min(1, { message: "SUPABASE_SERVICE_KEY is required" }),
});

function parseEnv(source) {
  const result = EnvSchema.safeParse(source);
  if (!result.success) {
    console.error("❌  Missing or invalid environment variables:\n");
    for (const issue of result.error.issues) {
      console.error(`  ${issue.path.join(".")}: ${issue.message}`);
    }
    process.exit(1);
  }
  return result.data;
}

// ── Logging adapter ─────────────────────────────────────────────────────────
// Audit trail writes live here, behind the Proxy interface. Logging never
// blocks proxying: failures are swallowed by design.

/** Typed flip event: an admin action, not an error. The logs table has no
 *  note column, so the message rides in error_message for Audit visibility. */
function makeFlipRow(target) {
  return {
    ...makeLogRow({
      service: ServiceName.PROXY_EVENT,
      endpoint: "/admin/route",
      status_code: 200,
      latency_ms: 0,
    }),
    error_message: `traffic flip to ${target}`,
  };
}

function createLogger(client) {
  async function logRow(row) {
    if (!client) return;
    try {
      await client.from("logs").insert(row);
    } catch {
      // never block proxying on logging
    }
  }

  async function logFlip(target) {
    await logRow(makeFlipRow(target));
  }

  function trafficMiddleware(getTarget) {
    return (req, res, next) => {
      const started = Date.now();
      res.on("finish", () => {
        void logRow(makeLogRow({
          service: ServiceName.PROXY_TRAFFIC(getTarget()),
          endpoint: req.originalUrl,
          status_code: res.statusCode,
          latency_ms: Date.now() - started,
          error_text: isError(res.statusCode) ? `proxy saw ${res.statusCode}` : null,
        }));
      });
      next();
    };
  }

  return { logRow, logFlip, trafficMiddleware };
}

// ── Proxy module: route + flip behind one interface ─────────────────────────

const env = parseEnv(process.env);

const PORT = env.PORT;
const targets = { stable: env.STABLE_URL, canary: env.CANARY_URL };

const supabase =
  env.SUPABASE_URL && env.SUPABASE_SERVICE_KEY
    ? createClient(env.SUPABASE_URL, env.SUPABASE_SERVICE_KEY)
    : null;
const logger = createLogger(supabase);

let target = "stable";
const getTarget = () => target;

const app = express();
app.use(express.json());

app.get("/health", (_req, res) => res.json({ ok: true, target }));

app.get("/admin/route", (_req, res) => res.json({ target }));

// Execution endpoint: the only promote/rollback mechanism (ADR-0002)
app.post("/admin/route", async (req, res) => {
  const next = req.body?.target;
  if (next !== ServiceName.STABLE && next !== ServiceName.CANARY) {
    return res.status(400).json({ error: 'target must be "stable" | "canary"' });
  }
  target = next;
  await logger.logFlip(target);
  res.json({ target });
});

app.use(logger.trafficMiddleware(getTarget));

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
