import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { createLogger, makeFlipRow, parseEnv, EnvSchema } from "./lib.js";
import { createAdminAuth, isAuthorized } from "./auth.js";

const TEST_ENV = {
  SUPABASE_URL: "https://example.supabase.co",
  SUPABASE_SERVICE_KEY: "key",
  ADMIN_TOKEN: "test-admin-token-1234",
};

describe("parseEnv", () => {
  it("applies defaults", () => {
    const env = parseEnv({ ...TEST_ENV });
    assert.equal(env.PORT, 8080);
    assert.equal(env.STABLE_URL, "http://stable:8000");
  });

  it("requires ADMIN_TOKEN", () => {
    // NOTE: parseEnv() calls process.exit(1) on failure, so the negative
    // case asserts on the schema directly instead of calling parseEnv.
    const { ADMIN_TOKEN: _drop, ...without } = TEST_ENV;
    assert.equal(EnvSchema.safeParse(without).success, false);
  });
});

describe("makeFlipRow", () => {
  it("records flips in note, never in error_message", () => {
    const row = makeFlipRow("canary");
    assert.equal(row.service, "proxy");
    assert.equal(row.endpoint, "/admin/route");
    assert.equal(row.status_code, 200);
    assert.equal(row.error_message, null);
    assert.equal(row.note, "traffic flip to canary");
    assert.match(row.trace_id, /^[0-9a-f-]{36}$/);
  });
});

describe("admin auth", () => {
  const TOKEN = "test-admin-token-1234";

  it("accepts the correct Bearer token", () => {
    assert.equal(isAuthorized(`Bearer ${TOKEN}`, TOKEN), true);
  });

  it("rejects missing / wrong / malformed headers", () => {
    assert.equal(isAuthorized(undefined, TOKEN), false);
    assert.equal(isAuthorized("Bearer wrong", TOKEN), false);
    assert.equal(isAuthorized(TOKEN, TOKEN), false);
    assert.equal(isAuthorized(`Bearer ${TOKEN}`, ""), false);
  });

  it("middleware 401s without a token and passes with one", () => {
    const requireAdmin = createAdminAuth(TOKEN);
    let status = 0;
    const body = {};
    const res = {
      status: (s) => { status = s; return { json: (b) => Object.assign(body, b) }; },
    };
    let next = false;
    requireAdmin({ headers: {} }, res, () => { next = true; });
    assert.equal(status, 401);
    assert.equal(next, false);
    requireAdmin({ headers: { authorization: `Bearer ${TOKEN}` } }, res, () => { next = true; });
    assert.equal(next, true);
  });
});

describe("createLogger", () => {
  it("resolves without a client", async () => {
    const logger = createLogger(null);
    await logger.logFlip("stable");
    await logger.logRow({ service: "stable" });
  });

  it("swallows insert failures", async () => {
    const failing = { from: () => ({ insert: async () => { throw new Error("down"); } }) };
    const logger = createLogger(failing);
    await logger.logFlip("stable");
  });

  it("writes flip rows through the client", async () => {
    const written = [];
    const client = { from: (t) => ({ insert: async (row) => { written.push([t, row]); } }) };
    await createLogger(client).logFlip("stable");
    assert.equal(written.length, 1);
    assert.equal(written[0][0], "logs");
    assert.equal(written[0][1].note, "traffic flip to stable");
    assert.equal(written[0][1].error_message, null);
  });
});
