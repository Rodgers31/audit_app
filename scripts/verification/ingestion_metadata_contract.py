"""Fixed, owner-mediated metadata projection for preflight protocol 2.

The observer gets EXECUTE, never application SELECT or statistics membership.
Installation is an explicit operator action, not an application migration.
"""
from __future__ import annotations

import hashlib

SCHEMA = "audit_preflight_v2"
FUNCTION = "observe"
READERS = ("audit_app_audit_reader", "b71_preflight_reader")
CHECK_NAMES = (
    "retained_claim",
    "retained_dispatch",
    "worker_ready",
    "nonterminal_or_unknown_command",
    "nonterminal_or_unknown_job",
    "other_active_session",
    "prepared_transaction",
)
OUTPUT_NAMES = ("protocol", "revision", *CHECK_NAMES, "complete_activity")
# Default admission remains an empty reader graph. The explicit existing-audit
# profile pins the two owner-only administration edges and one read-group edge.
ROLE_GRAPH_SQL = """(EXISTS(SELECT 1 FROM pg_catalog.pg_roles
 WHERE oid={owner} AND rolname='postgres') AND (CASE
 WHEN {audit_log} IS NULL AND {grantor} IS NULL THEN
  NOT EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members
    WHERE roleid={reader} OR member={reader})
 WHEN {audit_log} IS NOT NULL AND {grantor} IS NOT NULL THEN
  {reader}<>{owner} AND {audit_log} NOT IN({reader},{owner})
  AND {grantor} NOT IN({reader},{owner},{audit_log})
  AND EXISTS(SELECT 1 FROM pg_catalog.pg_roles r
    WHERE r.oid={audit_log} AND r.rolname='audit_log_reader'
      AND NOT r.rolcanlogin AND NOT r.rolsuper AND NOT r.rolbypassrls
      AND NOT r.rolcreatedb AND NOT r.rolcreaterole AND NOT r.rolreplication
      AND r.rolinherit)
  AND EXISTS(SELECT 1 FROM pg_catalog.pg_roles r
    WHERE r.oid={grantor} AND r.rolname='supabase_admin' AND r.rolsuper)
  AND (SELECT count(*) FROM pg_catalog.pg_auth_members
    WHERE roleid IN({reader},{audit_log}) OR member IN({reader},{audit_log}))=3
  AND (SELECT count(*) FROM pg_catalog.pg_auth_members
    WHERE roleid IN({reader},{audit_log}) AND member={owner}
      AND grantor={grantor} AND admin_option
      AND NOT inherit_option AND NOT set_option)=2
  AND EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members
    WHERE roleid={audit_log} AND member={reader} AND grantor={owner}
      AND NOT admin_option AND inherit_option AND set_option)
 ELSE false END))"""


def profile_oids(profile):
    """No implicit profile selection, coercion or caller-selected role names."""
    if profile is None:
        return None, None
    if type(profile) is not dict or set(profile) != {
        "audit_log_role_oid",
        "admin_grantor_oid",
    }:
        raise ValueError("ROLE_PROFILE_REFUSED")
    values = tuple(profile[k] for k in ("audit_log_role_oid", "admin_grantor_oid"))
    if (
        any(type(x) is not int or not 0 < x <= 2**32 - 1 for x in values)
        or values[0] == values[1]
    ):
        raise ValueError("ROLE_PROFILE_REFUSED")
    return values


def interface_parameters(reader_oid, profile):
    if type(reader_oid) is not int or not 0 < reader_oid <= 2**32 - 1:
        raise ValueError("READER_REFUSED")
    return reader_oid, *profile_oids(profile)


BODY = """SELECT 2::integer,
 (SELECT CASE WHEN count(*)=1 THEN min(v.revision) ELSE NULL END
  FROM (SELECT pg_catalog.left(version_num::text,33) AS revision
        FROM public.alembic_version LIMIT 2) v),
 EXISTS(SELECT 1 FROM public.seeding_domain_claims WHERE released_at IS NULL LIMIT 1),
 EXISTS(SELECT 1 FROM public.etl_dispatch_domains
        WHERE command_id IS NOT NULL OR claim_token IS NOT NULL
           OR ready IS DISTINCT FROM FALSE LIMIT 1),
 EXISTS(SELECT 1 FROM public.etl_dispatch_worker WHERE ready IS DISTINCT FROM FALSE LIMIT 1),
 EXISTS(SELECT 1 FROM public.etl_dispatch_commands
        WHERE status IS NULL OR status NOT IN ('completed','failed') LIMIT 1),
 EXISTS(SELECT 1 FROM public.ingestion_jobs
        WHERE status IS NULL OR status::text NOT IN
              ('COMPLETED','COMPLETED_WITH_ERRORS','FAILED') LIMIT 1),
 EXISTS(SELECT 1 FROM pg_catalog.pg_stat_activity
        WHERE datid=(SELECT oid FROM pg_catalog.pg_database
                     WHERE datname=pg_catalog.current_database())
          AND pid<>pg_catalog.pg_backend_pid() AND backend_type='client backend'
          AND state IS DISTINCT FROM 'idle' LIMIT 1),
 EXISTS(SELECT 1 FROM pg_catalog.pg_prepared_xacts
        WHERE database=pg_catalog.current_database() LIMIT 1),
 pg_catalog.pg_has_role(current_user,'pg_read_all_stats','USAGE')
 AND NOT EXISTS(SELECT 1 FROM pg_catalog.pg_stat_activity
        WHERE datid=(SELECT oid FROM pg_catalog.pg_database
                     WHERE datname=pg_catalog.current_database())
          AND backend_type='client backend' AND state IS NULL LIMIT 1)
"""
BODY_SHA256 = hashlib.sha256(BODY.encode()).hexdigest()
OBSERVE_SQL = "SELECT * FROM audit_preflight_v2.observe()"


def installation_sql(reader: str, *, reader_oid, owner_oid, role_profile=None) -> str:
    """Only the existing production login or an explicit owned-test login."""
    if type(reader) is not str or reader not in READERS:
        raise ValueError("READER_REFUSED")
    if (
        any(
            type(x) is not int or not 0 < x <= 2**32 - 1
            for x in (reader_oid, owner_oid)
        )
        or reader_oid == owner_oid
    ):
        raise ValueError("ROLE_IDENTITY_REFUSED")
    log_oid, grantor_oid = profile_oids(role_profile)
    if log_oid is not None and len({reader_oid, owner_oid, log_oid, grantor_oid}) != 4:
        raise ValueError("ROLE_PROFILE_REFUSED")
    graph = ROLE_GRAPH_SQL.format(
        reader=f"{reader_oid}::oid",
        owner=f"{owner_oid}::oid",
        audit_log="NULL::oid" if log_oid is None else f"{log_oid}::oid",
        grantor="NULL::oid" if grantor_oid is None else f"{grantor_oid}::oid",
    )
    return f"""BEGIN;
SET LOCAL statement_timeout='2s';
SET LOCAL lock_timeout='500ms';
DO $guard$
BEGIN
 IF current_user <> 'postgres' OR session_user <> 'postgres'
    OR NOT pg_catalog.pg_has_role(current_user,'pg_read_all_stats','USAGE')
    OR current_setting('server_version_num')::integer NOT BETWEEN 170000 AND 179999
 THEN RAISE EXCEPTION 'PREFLIGHT_OWNER_REFUSED'; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_roles
      WHERE oid={reader_oid}::oid AND rolname='{reader}')
 OR NOT EXISTS(SELECT 1 FROM pg_catalog.pg_roles
      WHERE oid={owner_oid}::oid AND rolname='postgres')
 THEN RAISE EXCEPTION 'PREFLIGHT_ROLE_IDENTITY_REFUSED'; END IF;
 IF pg_catalog.to_regnamespace('{SCHEMA}') IS NOT NULL
 THEN RAISE EXCEPTION 'PREFLIGHT_NAMESPACE_EXISTS'; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='{reader}'
     AND rolcanlogin AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreatedb
     AND NOT rolcreaterole AND NOT rolreplication)
 THEN RAISE EXCEPTION 'PREFLIGHT_READER_REFUSED'; END IF;
 IF NOT {graph}
 THEN RAISE EXCEPTION 'PREFLIGHT_ROLE_GRAPH_REFUSED'; END IF;
 IF pg_catalog.pg_has_role('{reader}','pg_read_all_stats','MEMBER')
 OR pg_catalog.has_database_privilege('{reader}',current_database(),'CREATE')
 OR EXISTS(SELECT 1 FROM pg_catalog.pg_namespace n
     WHERE pg_catalog.left(n.nspname,3)<>'pg_' AND n.nspname<>'information_schema'
       AND pg_catalog.has_schema_privilege('{reader}',n.oid,'CREATE'))
 OR EXISTS(SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
     WHERE pg_catalog.left(n.nspname,3)<>'pg_' AND n.nspname<>'information_schema'
       AND (pg_catalog.pg_has_role('{reader}',c.relowner,'MEMBER')
         OR CASE WHEN c.relkind IN ('r','p','v','m','f') THEN
              pg_catalog.has_table_privilege('{reader}',c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER')
              OR pg_catalog.has_any_column_privilege('{reader}',c.oid,'INSERT,UPDATE')
            WHEN c.relkind='S' THEN pg_catalog.has_sequence_privilege('{reader}',c.oid,'USAGE,UPDATE')
            ELSE false END))
 THEN RAISE EXCEPTION 'PREFLIGHT_READER_ACCESS_REFUSED'; END IF;
END
$guard$;
CREATE SCHEMA {SCHEMA} AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA {SCHEMA} FROM PUBLIC;
CREATE FUNCTION {SCHEMA}.{FUNCTION}()
RETURNS TABLE(protocol integer, revision text,
 retained_claim boolean, retained_dispatch boolean, worker_ready boolean,
 nonterminal_or_unknown_command boolean, nonterminal_or_unknown_job boolean,
 other_active_session boolean, prepared_transaction boolean, complete_activity boolean)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog SET row_security=off
AS $projection${BODY}$projection$;
REVOKE ALL ON FUNCTION {SCHEMA}.{FUNCTION}() FROM PUBLIC;
GRANT USAGE ON SCHEMA {SCHEMA} TO {reader};
GRANT EXECUTE ON FUNCTION {SCHEMA}.{FUNCTION}() TO {reader};
DO $acl_guard$
DECLARE reader_oid oid := (SELECT oid FROM pg_catalog.pg_roles WHERE rolname='{reader}');
BEGIN
 IF EXISTS(SELECT 1 FROM pg_catalog.pg_proc p
     CROSS JOIN LATERAL pg_catalog.aclexplode(p.proacl) a
     WHERE p.oid='{SCHEMA}.{FUNCTION}()'::regprocedure
       AND (a.grantee NOT IN(p.proowner,reader_oid) OR a.grantee=0
         OR a.grantor<>p.proowner OR a.privilege_type<>'EXECUTE'
         OR (a.grantee<>p.proowner AND a.is_grantable)))
 OR EXISTS(SELECT 1 FROM pg_catalog.pg_namespace n
     CROSS JOIN LATERAL pg_catalog.aclexplode(n.nspacl) a
     WHERE n.nspname='{SCHEMA}'
       AND (a.grantee NOT IN(n.nspowner,reader_oid) OR a.grantee=0
         OR a.grantor<>n.nspowner
         OR (a.grantee<>n.nspowner AND (a.privilege_type<>'USAGE' OR a.is_grantable))))
 THEN RAISE EXCEPTION 'PREFLIGHT_DEFAULT_ACCESS_REFUSED'; END IF;
END
$acl_guard$;
COMMIT;
"""


# Only this bounded definition text is read. It is a reviewed routine body, not
# application query text. Unknown overloads/default PUBLIC EXECUTE refuse.
INTERFACE_SQL = """WITH admitted AS (
 SELECT %s::oid AS reader_oid,%s::oid AS audit_log_oid,%s::oid AS admin_grantor_oid
)
SELECT n.oid::bigint,p.oid::bigint,p.proowner::bigint,
 l.lanname,p.prosecdef,p.provolatile,p.prokind,p.pronargs,p.proretset,
 (p.prorettype=2249 AND p.pronargdefaults=0 AND p.prosupport=0 AND p.provariadic=0
  AND p.proallargtypes=ARRAY[23,25,16,16,16,16,16,16,16,16]::oid[]
  AND p.proargmodes=ARRAY['t','t','t','t','t','t','t','t','t','t']::"char"[]
  AND p.proargnames=ARRAY['protocol','revision','retained_claim','retained_dispatch',
      'worker_ready','nonterminal_or_unknown_command','nonterminal_or_unknown_job',
      'other_active_session','prepared_transaction','complete_activity']::text[]),
 (p.proconfig=ARRAY['search_path=pg_catalog','row_security=off']::text[]),
 p.proparallel,p.proleakproof,p.proisstrict,n.nspowner::bigint,
 (NOT EXISTS(SELECT 1 FROM pg_catalog.aclexplode(
       COALESCE(p.proacl,pg_catalog.acldefault('f',p.proowner))) a
    WHERE a.grantee NOT IN(p.proowner,admitted.reader_oid) OR a.grantee=0
       OR a.grantor<>p.proowner OR a.privilege_type<>'EXECUTE'
       OR (a.grantee<>p.proowner AND a.is_grantable))
  AND EXISTS(SELECT 1 FROM pg_catalog.aclexplode(p.proacl) a
       WHERE a.grantee=admitted.reader_oid AND a.privilege_type='EXECUTE' AND NOT a.is_grantable)),
 (NOT EXISTS(SELECT 1 FROM pg_catalog.aclexplode(
       COALESCE(n.nspacl,pg_catalog.acldefault('n',n.nspowner))) a
    WHERE a.grantee NOT IN(n.nspowner,admitted.reader_oid) OR a.grantee=0 OR a.grantor<>n.nspowner
       OR (a.grantee<>n.nspowner AND (a.privilege_type<>'USAGE' OR a.is_grantable)))
  AND EXISTS(SELECT 1 FROM pg_catalog.aclexplode(n.nspacl) a
       WHERE a.grantee=admitted.reader_oid AND a.privilege_type='USAGE' AND NOT a.is_grantable)),
 pg_catalog.pg_has_role(p.proowner,'pg_read_all_stats','USAGE'),
 CASE WHEN pg_catalog.octet_length(p.prosrc)<=16384 THEN p.prosrc ELSE NULL END,
 {role_graph}
FROM pg_catalog.pg_proc p
JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
JOIN pg_catalog.pg_language l ON l.oid=p.prolang
CROSS JOIN admitted
WHERE n.nspname='audit_preflight_v2' AND p.proname='observe'
ORDER BY p.oid LIMIT 2
""".format(
    role_graph=ROLE_GRAPH_SQL.format(
        reader="admitted.reader_oid",
        owner="p.proowner",
        audit_log="admitted.audit_log_oid",
        grantor="admitted.admin_grantor_oid",
    )
)
