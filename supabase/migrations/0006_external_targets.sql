-- Migration 0006: external target pairs + generated probe cases (BYO-API).
--
-- Demo traffic keeps target_id NULL (current behavior). External runs tag
-- rows so analysis can scope per target. Writes are service_role-only
-- (runner registers + runs server-side and bypasses RLS); owners can read
-- their own targets/cases with their JWT. can_flip stays false for external
-- pairs: the agent advises, it never actuates third-party traffic.

create table if not exists target_pairs (
  id uuid primary key default gen_random_uuid(),
  owner_email text not null,
  stable_url text not null,
  canary_url text not null,
  spec_text text not null,
  inventory jsonb not null default '[]'::jsonb,
  can_flip boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists probe_cases (
  id bigint generated always as identity primary key,
  target_id uuid not null references target_pairs(id) on delete cascade,
  method text not null,
  path text not null,
  body jsonb,
  tier text not null default 'high',
  source text not null default 'synth',
  created_at timestamptz not null default now()
);
create index if not exists probe_cases_target_id_idx on probe_cases(target_id);

alter table logs add column if not exists target_id uuid references target_pairs(id) on delete set null;
alter table proposals add column if not exists target_id uuid references target_pairs(id) on delete set null;

alter table target_pairs enable row level security;
alter table probe_cases enable row level security;

drop policy if exists "own targets" on target_pairs;
create policy "own targets" on target_pairs
  for select using (owner_email = (auth.jwt() ->> 'email'));

drop policy if exists "own cases" on probe_cases;
create policy "own cases" on probe_cases
  for select using (
    exists (select 1 from public.target_pairs t
            where t.id = probe_cases.target_id
            and t.owner_email = (auth.jwt() ->> 'email'))
  );

grant select on target_pairs to authenticated;
grant select on probe_cases to authenticated;
