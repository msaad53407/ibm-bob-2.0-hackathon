import { ServiceName, isError, makeLogRow } from "@guardrail/contracts";

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
