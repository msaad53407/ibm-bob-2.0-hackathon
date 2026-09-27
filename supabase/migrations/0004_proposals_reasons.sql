-- Migration 0004: store Decision reasons alongside proposals
-- The reasons list (e.g. ["canary 5xx on critical /checkout: 2 vs stable 0"])
-- was previously only returned in the API response and never persisted.
-- This column makes the Proposals history page fully self-contained.

alter table proposals
  add column if not exists reasons jsonb not null default '[]'::jsonb;
