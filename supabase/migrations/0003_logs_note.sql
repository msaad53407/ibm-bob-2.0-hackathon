-- Migration 0003: typed flip-event notes on the logs table
--
-- Traffic flip rows are admin actions, not errors. They carry their message
-- in note instead of smuggling it through error_message (which stays NULL
-- for non-error rows per the LogRow convention in packages/contracts).

alter table logs
  add column if not exists note text;
