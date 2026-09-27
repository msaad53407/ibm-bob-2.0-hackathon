-- Migration 0007: per-case attribution on probe rows.
--
-- The runner fires the SAME (method, path, body) at stable and canary, so the
-- pair is the strongest signal available — but only if each row remembers
-- which generated case produced it. Without attribution the agent could only
-- report endpoint-level aggregates, and an unrelated shared failure could
-- mask a canary-only one (see Decision's method-scoped pairing).
--
-- case_tier/source/label are NULL for demo traffic (the canonical CASES carry
-- no per-case metadata) and set for registered external targets.

alter table logs add column if not exists case_tier text;
alter table logs add column if not exists case_source text;
alter table logs add column if not exists case_label text;

-- Findings are always scoped by case provenance: partial index keeps the
-- agent's target-scoped fetch off a sequential scan of the whole table.
create index if not exists logs_case_idx on logs(target_id, case_tier)
  where target_id is not null;

alter table probe_cases add column if not exists label text;

comment on column logs.case_tier is
  'critical|high — tier of the probe case that produced this row (NULL for demo traffic)';
comment on column logs.case_source is
  'synth|llm|demo — how the probe case was generated (NULL for demo traffic)';
comment on column logs.case_label is
  'short case identity, e.g. drop-required:title, wrong-type:due_in_days, enum:priority';
comment on column probe_cases.label is
  'short case identity used for log-row attribution and proposal evidence';
