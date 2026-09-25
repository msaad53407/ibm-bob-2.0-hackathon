create table if not exists logs (
  id bigint generated always as identity primary key,
  timestamp timestamptz not null default now(),
  service text not null,
  endpoint text not null,
  status_code int not null,
  latency_ms int not null,
  error_message text,
  trace_id uuid not null
);

create table if not exists proposals (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  verdict text not null,
  proposals jsonb not null
);

-- append-only audit: no update/delete grants for anon/authenticated
create table if not exists audit (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  approver text not null,
  action text not null,
  outcome text not null,
  proposal jsonb
);
alter table logs enable row level security;
alter table proposals enable row level security;
alter table audit enable row level security;
create policy "read all" on logs for select using (true);
create policy "insert all" on logs for insert with check (true);
create policy "read all" on proposals for select using (true);
create policy "insert all" on proposals for insert with check (true);
create policy "read all" on audit for select using (true);
create policy "insert all" on audit for insert with check (true);
