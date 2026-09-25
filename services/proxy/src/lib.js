import { createClient } from "@supabase/supabase-js";
import { ServiceName, isError, makeLogRow } from "@guardrail/contracts";
import { z } from "zod";

// Side-effect-free Proxy internals: importable without binding a port.
// index.js wires these into the running module; lib.test.js covers them.

// ── Config adapter ──────────────────────────────────────────────────────────
// Fails fast at startup with a clear message rather than a cryptic runtime error.
export const EnvSchema = z.object({
  PORT:                 z.coerce.number().int().positive().default(8080),
  STABLE_URL:           z.string().url().default("http://stable:8000"),
  CANARY_URL:           z.string().url().default("http://canary:8000"),
  SUPABASE_URL:         z.string().url({ message: "SUPABASE_URL must be a valid URL" }),
  SUPABASE_SERVICE_KEY: z.string().min(1, { message: "SUPABASE_SERVICE_KEY is required" }),
});

export function parseEnv(source) {
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

export function createSupabaseClient(url, key) {
  return url && key ? createClient(url, key) : null;
}

// ── Logging adapter ─────────────────────────────────────────────────────────
// Audit trail writes live here, behind the Proxy interface. Logging never
// blocks proxying: failures are swallowed by design.

/** Typed flip event: an admin action recorded in note, never in error_message. */
export function makeFlipRow(target) {
  return makeLogRow({
    service: ServiceName.PROXY_EVENT,
    endpoint: "/admin/route",
    status_code: 200,
    latency_ms: 0,
    note: `traffic flip to ${target}`,
  });
}

export function createLogger(client) {
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
