import { timingSafeEqual } from "node:crypto";

// ── Admin auth ──────────────────────────────────────────────────────────────
// Shared-secret Bearer gate for the Proxy admin surface (Slice A).
// The secret itself lives in server-only env (ADMIN_TOKEN) and is compared
// with timingSafeEqual so a wrong guess leaks nothing via timing.

export function isAuthorized(header, expectedToken) {
  if (typeof header !== "string" || !expectedToken) return false;
  const expected = `Bearer ${expectedToken}`;
  const a = Buffer.from(header);
  const b = Buffer.from(expected);
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}

export function createAdminAuth(expectedToken) {
  return function requireAdmin(req, res, next) {
    if (!isAuthorized(req.headers?.authorization, expectedToken)) {
      return res.status(401).json({ error: "unauthorized" });
    }
    next();
  };
}
