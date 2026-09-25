import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { createLogger, makeFlipRow, parseEnv } from "./lib.js";

describe("parseEnv", () => {
  it("applies defaults", () => {
    const env = parseEnv({
      SUPABASE_URL: "https://example.supabase.co",
      SUPABASE_SERVICE_KEY: "key",
    });
    assert.equal(env.PORT, 8080);
    assert.equal(env.STABLE_URL, "http://stable:8000");
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
