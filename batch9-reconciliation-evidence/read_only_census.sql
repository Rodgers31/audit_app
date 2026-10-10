-- Diagnostic input for an independently authorized operator. No release.
-- Startup connection options are not proof: explicitly enter/verify READ ONLY.
BEGIN READ ONLY;
SHOW transaction_read_only;
SELECT clock_timestamp() AS observed_at, current_database() AS database,
       current_user AS actor, version() AS server,
       current_setting('idle_in_transaction_session_timeout') AS idle_transaction_cutoff,
       current_setting('idle_session_timeout') AS idle_session_cutoff;
SELECT oid, datname, datallowconn FROM pg_database WHERE datname=current_database();
SELECT domain, count(*) AS running_count FROM public.ingestion_jobs
 WHERE status='RUNNING' GROUP BY domain ORDER BY domain;
SELECT id, domain, dry_run, started_at,
       jsonb_typeof(metadata) AS metadata_shape,
       metadata->>'seeding_claim_id' AS claim_tag,
       metadata->>'dispatch_command_id' AS command_tag,
       metadata->>'dispatch_claim_token' AS token_tag
 FROM public.ingestion_jobs WHERE status='RUNNING' ORDER BY domain,id;
-- No query text, credentials, provider URLs or application payloads exported.
SELECT pid, backend_start, backend_type, state, xact_start, application_name
 FROM pg_stat_activity WHERE datname=current_database() ORDER BY pid;
SELECT gid, prepared, owner, database FROM pg_prepared_xacts
 WHERE database=current_database();
SELECT to_regclass('public.seeding_domain_claims') AS claim_table,
       to_regclass('public.etl_dispatch_commands') AS dispatch_table;
ROLLBACK;
