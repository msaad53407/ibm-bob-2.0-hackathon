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
in `workers/agent/graph.py:bob_criticality` (fallback criticality map so demo never blocks).

Done when: `docker compose up` serves stable/canary side by side, proxy defaults
to stable and `POST /admin/route {target}` flips live traffic, runner writes
`{timestamp, service, endpoint, status_code, latency_ms, error_message, trace_id}`
for all 4 cases x 2 services, both bugs reproduce deterministically.

## Track B — Decide + Show (teammate)

Owns: `workers/agent/graph.py` (`/decide` rule `error_diff>5% OR p95 split on
critical → escalate`, `/propose` 3 ranked with risk/blast-radius/reversibility,
`/execute` real flip call + audit insert), `apps/web/` (live metrics via Realtime,
proposal cards, approve/deny, audit viewer, MTTD/MTTR timers), `supabase`
proposals/audit tables, demo script + video + submission.

Done when: escalate triggers on the 2 planted bugs, dashboard shows ranked
proposals, human click executes a real flip, audit row is append-only, timers run.

## Shared contracts (do not change unilaterally)

- Log schema: `packages/contracts/src/index.ts:LogRow`.
- Flip API: `GET/POST /admin/route {target: stable|canary}` on proxy `:8080`.
- Criticality map: `{critical: ["/checkout"], high: ["/search"], source}`.
- Agent API: `:8003/decide`, `/propose`, `/execute {target, approver}`.
- Lean MVP + Realtime: no Sentry adapter, single model, polling replaced by
  Supabase Realtime, only flip executes (flag-off/shift-down displayed).

## Integration

- Hr 0-3 (joint): lock contracts above, run migration, `docker compose up --build`.
- Hr 30: runner → agent → dashboard → flip end-to-end against real bugs.
- Hr 44: full dry-run (deploy bug, traffic, propose, approve live, show audit).

## Run

1. `cp .env.example .env`, fill `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY`.
2. Apply `supabase/migrations/0001_init.sql` to the cloud project.
3. `docker compose up --build`. Web `:3000`, proxy `:8080`, agent `:8003`.
