-- Migration 0002: enforce service field conventions on the logs table
-- Ensures all writers use the canonical ServiceName values defined in
-- packages/contracts/src/index.ts and workers/shared/log_row.py

alter table logs
  add constraint logs_service_check
  check (
    service in ('stable', 'canary', 'proxy')
    or service like 'proxy->%'
  );
