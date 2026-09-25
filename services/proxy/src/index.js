import express from "express";
import { createProxyMiddleware } from "http-proxy-middleware";
import { createClient } from "@supabase/supabase-js";
import { randomUUID } from "node:crypto";

const PORT = Number(process.env.PORT ?? 8080);
const STABLE_URL = process.env.STABLE_URL ?? "http://stable:8000";
const CANARY_URL = process.env.CANARY_URL ?? "http://canary:8000";
const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_KEY;

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
  if (next !== "stable" && next !== "canary") {
    return res.status(400).json({ error: 'target must be "stable" | "canary"' });
  }
  target = next;
  await logRow({
    timestamp: new Date().toISOString(),
    service: "proxy",
    endpoint: "/admin/route",
    status_code: 200,
    latency_ms: 0,
    error_message: `traffic flip to ${target}`,
    trace_id: randomUUID(),
  });
  res.json({ target });
});

app.use(async (req, res, next) => {
  const started = Date.now();
  const traceId = randomUUID();
  res.on("finish", () => {
    void logRow({
      timestamp: new Date().toISOString(),
      service: `proxy->${target}`,
      endpoint: req.originalUrl,
      status_code: res.statusCode,
      latency_ms: Date.now() - started,
      error_message: res.statusCode >= 500 ? `proxy saw ${res.statusCode}` : null,
      trace_id: traceId,
    });
  });
  next();
});

app.use(
  "/",
  createProxyMiddleware({
    router: () => targets[target],
    changeOrigin: true,
    logger: console,
  })
);

app.listen(PORT, () => console.log(`proxy on :${PORT} -> ${target}`));
