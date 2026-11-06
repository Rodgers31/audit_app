-- PREPARED, NOT EXECUTED. Existing approved TLS/role observer only.
-- psql service must already pin endpoint/role/database + verify-full existing CA.
-- One invocation, connect_timeout=3, outer deadline <=35s; never print DSNs.
\set ON_ERROR_STOP on
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '3s';
SET LOCAL lock_timeout = '1s';
SET LOCAL idle_in_transaction_session_timeout = '10s';
SET LOCAL row_security = off;
SELECT current_setting('transaction_read_only') AS read_only,
       md5(current_database()) AS database_ref, md5(current_user) AS role_ref,
       current_setting('server_version') AS server_version,
       current_setting('max_connections') AS physical_pg_limit,
       current_setting('superuser_reserved_connections') AS superuser_reserve;
SELECT ssl, version, cipher, bits FROM pg_stat_ssl WHERE pid = pg_backend_pid();
SELECT version_num AS schema_revision FROM public.alembic_version;
SELECT md5(rolname) AS role_ref, rolsuper, rolcreaterole, rolcreatedb,
       rolreplication, rolbypassrls, rolcanlogin, rolconnlimit
  FROM pg_roles WHERE rolname IN (current_user, session_user);
WITH RECURSIVE memberships(oid) AS (
  SELECT oid FROM pg_roles WHERE rolname=current_user
  UNION
  SELECT m.roleid FROM pg_auth_members m JOIN memberships p ON p.oid=m.member
)
SELECT md5(r.rolname) AS member_role_ref, r.rolsuper,r.rolbypassrls,
       r.rolcreaterole,r.rolcreatedb,r.rolreplication
  FROM memberships m JOIN pg_roles r ON r.oid=m.oid;
SELECT c.relname,c.relkind,md5(pg_get_userbyid(c.relowner)) AS owner_ref,
       c.relrowsecurity,c.relforcerowsecurity,c.reloptions,
       has_table_privilege(current_user,c.oid,'SELECT') AS effective_select,
       has_table_privilege(current_user,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE') AS any_write,
       CASE WHEN c.relkind='v' THEN md5(pg_get_viewdef(c.oid,true)) END AS raw_view_md5
  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relname IN
 ('social_source_events','social_source_cursors','social_controls','social_accounts',
  'social_native_source_authority','social_native_source_authority_snapshot',
  'social_report_source_authority','social_report_source_authority_snapshot',
  'social_media_assets','social_media_uploads','budget_lines','audits',
  'fiscal_summaries','debt_timeline','ingestion_jobs')
 ORDER BY c.relname;
SELECT c.relname, a.attnum,a.attname,format_type(a.atttypid,a.atttypmod) AS type,
       a.attnotnull
  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  JOIN pg_attribute a ON a.attrelid=c.oid
 WHERE n.nspname='public' AND c.relname IN
 ('social_native_source_authority','social_native_source_authority_snapshot',
  'social_report_source_authority','social_report_source_authority_snapshot')
 AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum;
SELECT c.relname, md5(pg_get_userbyid(e.grantor)) AS grantor_ref,
       CASE WHEN e.grantee=0 THEN 'PUBLIC' ELSE md5(pg_get_userbyid(e.grantee)) END AS grantee_ref,
       e.privilege_type,e.is_grantable
  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) e
 WHERE n.nspname='public' AND c.relname LIKE 'social_%' ORDER BY c.relname,grantee_ref,e.privilege_type;
SELECT c.relname,a.attname,
       CASE WHEN e.grantee=0 THEN 'PUBLIC' ELSE md5(pg_get_userbyid(e.grantee)) END AS grantee_ref,
       e.privilege_type,e.is_grantable
  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  JOIN pg_attribute a ON a.attrelid=c.oid
  CROSS JOIN LATERAL aclexplode(a.attacl) e
 WHERE n.nspname='public' AND c.relname LIKE 'social_%'
 AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attname,grantee_ref;
SELECT c.relname,p.polname,p.polcmd,p.polpermissive,
       ARRAY(SELECT CASE WHEN x=0 THEN 'PUBLIC' ELSE md5(pg_get_userbyid(x)) END
             FROM unnest(p.polroles) x ORDER BY x) AS policy_role_refs,
       md5(COALESCE(pg_get_expr(p.polqual,p.polrelid),'')) AS using_ref,
       md5(COALESCE(pg_get_expr(p.polwithcheck,p.polrelid),'')) AS check_ref
  FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid
  JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relname LIKE 'social_%' ORDER BY c.relname,p.polname;
SELECT backend_type,md5(COALESCE(usename,'')) AS role_ref,
       datname=current_database() AS same_database,count(*) AS processes,
       count(*) FILTER (WHERE state='active') AS active,
       count(*) FILTER (WHERE state='idle in transaction') AS idle_in_transaction,
       count(*) FILTER (WHERE wait_event_type='Lock') AS waiting_lock,
       count(*) FILTER (WHERE state IS NULL) AS masked_or_background_state
  FROM pg_stat_activity GROUP BY backend_type,role_ref,same_database
 ORDER BY backend_type,role_ref,same_database;
ROLLBACK;
-- Raw view MD5 is a change indicator, never equivalent to role_contract.py's
-- normalized SHA256, exact owner/ACL/barrier/columns/rules/trigger/RLS contract.
-- That verifier includes SELECT FOR UPDATE and is NOT a read-only observer.
