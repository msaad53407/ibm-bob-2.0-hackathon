import express from "express";
import { createProxyMiddleware, fixRequestBody } from "http-proxy-middleware";
import { ServiceName } from "@guardrail/contracts";
import { parseEnv } from "./config.js";
import { createAdminAuth } from "./auth.js";
import { createSupabaseClient } from "./supabase.js";
import { createLogger } from "./logger.js";

// ── Proxy module: route + flip behind one interface ─────────────────────────

const env = parseEnv(process.env);

const PORT = env.PORT;
const targets = { stable: env.STABLE_URL, canary: env.CANARY_URL };

const logger = createLogger(
  createSupabaseClient(env.SUPABASE_URL, env.SUPABASE_SERVICE_KEY)
);

let target = "stable";
const getTarget = () => target;
const requireAdmin = createAdminAuth(env.ADMIN_TOKEN);

const app = express();
app.use(express.json());

app.get("/health", (_req, res) => res.json({ ok: true, target }));

app.get("/admin/route", (_req, res) => res.json({ target }));

// Execution endpoint: the only promote/rollback mechanism (ADR-0002).
// Gated by ADMIN_TOKEN (Slice A) — GET stays open for status display.
app.post("/admin/route", requireAdmin, async (req, res) => {
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
