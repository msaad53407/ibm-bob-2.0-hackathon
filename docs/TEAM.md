# GuardRail — Team Split (source of truth)

Team GuardRail, IBM Bob 2.0 Hackathon (Sep 25-27 2026). Vertical slices, contract-first.
Decisions: `docs/adr/0001-compose-over-vercel.md`, `0002-traffic-flip-is-rollback.md`,
`0003-hybrid-backend.md`, `0004-pnpm-turbo-compose.md`. Glossary: `CONTEXT.md`.

## Architecture

stable + canary (one FastAPI image, `BUG_PROFILE`) → proxy (Node, live routing + logging)
→ traffic-runner (Python, direct side-by-side hits) → Supabase (`logs`) → agent
(Python, decide/propose/execute) → proxy flip → audit. Dashboard (Next.js) gates
execution and shows live state. Two planted canary bugs: 500 on `POST /checkout`
edge case, +800ms on `GET /search`.

## Track A — Detect (Saad)

Owns: `services/proxy/`, `services/api-demo/`, `workers/traffic-runner/`,
`supabase/migrations/0001_init.sql` (logs table), doc-ingest `bob-shell` wrapper
in `workers/agent/domain/criticality.py:bob_criticality` (static spec map so demo never blocks).

Done when: `docker compose up` serves stable/canary side by side, proxy defaults
to stable and `POST /admin/route {target}` flips live traffic, runner writes
`{timestamp, service, endpoint, status_code, latency_ms, error_message, trace_id}`
for all 4 cases x 2 services, both bugs reproduce deterministically.

## Track B — Decide + Show (teammate)

Owns: `workers/agent/api/app.py` (`/decide` pairs the same probe on both sides
and escalates on any Canary-only 5xx or latency regression, `/propose` ranked
per-finding proposals with derived severity/blast-radius/reversibility,
`/execute` real flip call + audit insert), `apps/web/` (live metrics via Realtime,
proposal cards, approve, audit viewer, MTTD/MTTR timers on the Overview page),
`supabase` proposals/audit tables, demo script + video + submission.

Not yet built from this list: **deny** — there is no reject path, so a Proposal
set an operator does not want can only be ignored, never declined on the record.

Done when: escalate triggers on the 2 planted bugs, dashboard shows ranked
proposals, human click executes a real flip, audit row is append-only, timers run.

## Shared contracts (do not change unilaterally)

- Log schema: `packages/contracts/src/index.ts:LogRow` — including the
  `case_method` / `case_tier` / `case_source` / `case_label` attribution
  columns. Those four are the join key `domain/compare.py` pairs Stable and
  Canary responses on; a row written without them cannot be analysed.
- Flip API: `GET/POST /admin/route {target: stable|canary}` on proxy `:8080`.
- Criticality map: `{critical: ["/checkout"], high: ["/search"], source}`, and
  `tier_for_method()` — the single definition of which methods are critical.
- Agent API: `:8003/decide`, `/propose`, `/execute {target, approver}`.
- Lean MVP + Realtime: no Sentry adapter, single model, polling replaced by
  Supabase Realtime, only flip executes (flag-off/shift-down displayed).

## Integration

- Hr 0-3 (joint): lock contracts above, run migration, `docker compose up --build`.
- Hr 30: runner → agent → dashboard → flip end-to-end against real bugs.
- Hr 44: full dry-run (deploy bug, traffic, propose, approve live, show audit).

## Run

1. `cp .env.example .env`, fill `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY`.
2. Generate the service-to-service secret: `openssl rand -hex 32` → `ADMIN_TOKEN` in `.env` (server-only, never `NEXT_PUBLIC_`).
3. Apply migrations: `supabase db push` (or paste `supabase/migrations/` into the SQL editor).
4. Seed your admin: `insert into admins (email) values ('you@example.com');`
5. `docker compose up --build`. Only web `:3000` is public; proxy/agent are internal-only.
6. Open `:3000` → `/login` (password, sign-up, or magic link) → dashboard. `/execute` records your email as approver.

Auth notes: Supabase Auth → admin allowlist (`admins` table, migration `0005`).
Service writes use the service key (bypass RLS); anon reads/writes are denied.
For demo smoothness, disable "Confirm email" in Supabase Auth settings or create users under Auth → Users.

## Troubleshooting

**A dashboard page returns 500 and a service is missing from `docker compose ps`.**
Plain `docker compose ps` hides *exited* containers, so a service that died on
boot looks absent rather than broken. Use `docker compose ps -a`, then
`docker compose logs <service>`. The usual cause is an import error in a
Python worker — the image copies whole package directories, so a new module
picked up in one rebuild but not the other is the thing to check. The web
forwarders return `503 {"error": "agent unreachable" | "traffic-runner
unreachable"}` with the same hint, so a 503 names the service; a 500 means the
upstream answered and actually failed.

**`/decide` says "no canary-only difference across 0 paired probes".** The
analysis only looks at the last hour (`RECENT_WINDOW_SECONDS`). Fire a fresh
batch from `/verification` → *Run traffic* (or `/targets` for an external pair)
first. External targets also need live URLs — an ngrok tunnel from yesterday is
dead, and those probes will read as transport errors.
