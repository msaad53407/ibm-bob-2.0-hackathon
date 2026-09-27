-- Migration 0008: the request method on probe rows.
--
-- A case label is not unique across operations ('happy-path' exists for every
-- endpoint), and a path is not unique across methods (GET and DELETE both hit
-- /todos). The Decision's stable/canary pairing needs all three — method, path,
-- label — so the method is recorded on the row rather than inferred.

alter table logs add column if not exists case_method text;

comment on column logs.case_method is
  'HTTP method the case was fired with. Together with case_label and the path
   this is the key the Decision pairs stable/canary responses on.';
