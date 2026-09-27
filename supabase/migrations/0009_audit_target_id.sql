-- Migration 0009: audit.target_id — the Execution's originating target pair.
--
-- record_audit() has always inserted target_id (POST /execute passes it
-- through), but 0006 only added the column to logs and proposals. PostgREST
-- rejects an insert carrying a key that is not a column, so on a project
-- built from exactly these migrations POST /execute failed with a PGRST204
-- -class error *after* the proxy had already been flipped. Unlike the other
-- history writes, record_audit has no try/except (a failed audit record is
-- worth surfacing), so it surfaced as a 500: traffic flipped, no audit row.
--
-- Demo Executions keep it NULL, matching logs and proposals. Note the
-- column is advisory only: external pairs are structurally unapprovable
-- (approve_execution rejects a set with no execute field), so a non-NULL
-- target_id here records where an Execution came from, never that it was
-- allowed to act on third-party traffic.

alter table audit add column if not exists target_id uuid references target_pairs(id) on delete set null;

comment on column audit.target_id is
  'target pair this Execution belongs to (NULL for demo traffic)';
