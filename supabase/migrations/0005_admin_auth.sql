-- Migration 0005: admin allowlist + locked-down RLS (Slice B).
--
-- Dashboard login is Supabase Auth (email/password or magic link). Reads on
-- logs/proposals/audit are admin-only; writes stay service_role-only
-- (runner/proxy/agent use the service key, which bypasses RLS), so there are
-- intentionally NO insert/update/delete policies for anon/authenticated.
--
-- After applying, seed your first admin (replace the email):
--   insert into admins (email) values ('you@example.com');

create table if not exists admins (
  email text primary key,
  created_at timestamptz not null default now()
);

alter table admins enable row level security;

-- An authenticated user may read exactly their own allowlist row.
-- The dashboard layout uses this to decide admin vs access-denied.
drop policy if exists "own admin row" on admins;
create policy "own admin row" on admins
  for select using (email = (auth.jwt() ->> 'email'));

grant select on admins to authenticated;

-- Drop the open demo policies from 0001_init.sql.
drop policy if exists "read all" on logs;
drop policy if exists "insert all" on logs;
drop policy if exists "read all" on proposals;
drop policy if exists "insert all" on proposals;
drop policy if exists "read all" on audit;
drop policy if exists "insert all" on audit;

-- Admin-only reads (anon gets nothing now — the dashboard requires login).
drop policy if exists "admin read" on logs;
create policy "admin read" on logs
  for select using (
    exists (select 1 from public.admins a where a.email = (auth.jwt() ->> 'email'))
  );

drop policy if exists "admin read" on proposals;
create policy "admin read" on proposals
  for select using (
    exists (select 1 from public.admins a where a.email = (auth.jwt() ->> 'email'))
  );

drop policy if exists "admin read" on audit;
create policy "admin read" on audit
  for select using (
    exists (select 1 from public.admins a where a.email = (auth.jwt() ->> 'email'))
  );
