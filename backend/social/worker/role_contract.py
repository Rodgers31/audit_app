"""Explicit least-privilege SQL contract for a separately created worker login.

No role, password, engine, policy or grant is created at import. Installation is
an operator action; verification describes current SQL access, not deployment,
key custody, provider permissions or publishing authorization.
"""
from dataclasses import dataclass
from collections.abc import Mapping
import hashlib
import re
from types import MappingProxyType

from sqlalchemy import text
from sqlalchemy.engine import Engine


READ_TABLES = frozenset({
    'social_controls', 'social_accounts', 'social_publications',
    'social_post_targets', 'social_post_revisions', 'social_publish_attempts',
    'social_credentials', 'social_media_assets', 'social_worker_heartbeats',
    'social_worker_runtime_ownership', 'social_worker_runtime_history',
    'social_posts', 'social_source_events', 'social_source_cursors',
    'social_automation_rule_versions', 'social_policy_operating_evidence',
    'social_authorized_policy_snapshots', 'social_policy_selection', 'social_policy_decisions',
})
REPORT_VIEW_SHA256 = {
    'social_report_source_authority': 'f140c09463d68b7878d4f7b199d04f15ef3b95e109cfbb5820572c9d5e0a84f0',
    'social_report_source_authority_snapshot': '60d9f03c6a0586c236e51f25fba05bc3659c72101bc3021fb0f7b887152f78ed',
}
# The same reviewed 708 DDL on the documented prebaseline production schema
# expands the locked cohort's SELECT c.* in its historical physical order,
# including validation_warnings and the preexisting confidence_score. Actual
# PostgreSQL replay reproduces this exact body; joins, predicates and locks are
# unchanged. Keep this one locked-view variant explicit, never normalize SQL.
REPORT_LOCKED_VIEW_HISTORICAL_SHA256 = 'a10869d91f9d43eb6713a33089592336a204650b25752c8c26065ec610c18de0'
NATIVE_VIEW_SHA256 = {'social_native_source_authority': '95c130e2106639dcaa3519951bfa9baa49b52c7fdd677b0dbfe1f0e744b3975a', 'social_native_source_authority_snapshot': '7549c1de87fb44bf1f00b1a9b0ca39b2859d8b1e9a3d898f9203ab4a496faf1e'}
READ_VIEWS = frozenset({'social_report_source_authority'})
OPTIONAL_READ_VIEWS = frozenset({'social_native_source_authority'})
LOCK_TABLES = frozenset({'social_controls', 'social_publications', 'social_credentials', 'social_worker_runtime_ownership'})
UPDATES = {
    'social_accounts': frozenset('hold_reason publish_lease_target_id publish_lease_token publish_lease_expires_at updated_at'.split()),
    'social_post_targets': frozenset('state next_action next_action_at lease_owner lease_token lease_epoch lease_expires_at submit_count checkpoint primary_remote_id remote_refs remote_url visibility_state confirmation_kind error_code safe_error_message published_at updated_at'.split()),
    'social_publish_attempts': frozenset('completed_at outcome receipt duration_ms provider_request_id http_status provider_code'.split()),
    'social_worker_heartbeats': frozenset('heartbeat_at last_scan_at last_success_at active_claims state last_error_code'.split()),
    **{table: frozenset({'id'}) for table in LOCK_TABLES},
}
INSERTS = {
    'social_worker_runtime_ownership': frozenset('id owner_id generation deployment_version'.split()),
    'social_worker_runtime_history': frozenset('generation event owner_id deployment_version proof'.split()),
    'social_publish_attempts': frozenset('id target_id sequence operation_id operation request_fingerprint lease_epoch dispatch_started_at outcome receipt estimated_cost_microusd cost_reservation_state created_at'.split()),
    'social_worker_heartbeats': frozenset('worker_id deployment_version started_at heartbeat_at last_scan_at last_success_at active_claims state last_error_code'.split()),
    'social_audit_events': frozenset('id post_id target_id account_id actor_kind action previous_state new_state details request_id created_at'.split()),
}
TABLES = READ_TABLES | INSERTS.keys()
PLATFORM_READ_TABLES = frozenset({'social_platform_credentials', 'social_platform_budgets', 'social_platform_event_inbox'})
PLATFORM_LOCK_TABLES = frozenset({'social_platform_credentials'})
PLATFORM_UPDATES = {
    'social_platform_credentials': frozenset({'id'}),
    'social_platform_budgets': frozenset({'reserved_microusd', 'version'}),
    'social_platform_event_inbox': frozenset({'processing_state', 'processed_at'}),
}


@dataclass(frozen=True)
class RoleContract:
    read_tables: frozenset[str]
    lock_tables: frozenset[str]
    updates: Mapping[str, frozenset[str]]
    inserts: Mapping[str, frozenset[str]]

    @property
    def read_relations(self):
        return self.read_tables | READ_VIEWS

    @property
    def tables(self):
        return self.read_tables | self.inserts.keys()


def selected_contract(*, platforms=False):
    """Platform authority is an explicit boolean opt-in, never inferred from SQL."""
    _require(type(platforms) is bool)
    return RoleContract(READ_TABLES | PLATFORM_READ_TABLES if platforms else READ_TABLES,
        LOCK_TABLES | PLATFORM_LOCK_TABLES if platforms else LOCK_TABLES,
        MappingProxyType(UPDATES | PLATFORM_UPDATES if platforms else dict(UPDATES)),
        MappingProxyType(dict(INSERTS)))


IDENTIFIER = re.compile(r'[a-z][a-z0-9_]{0,62}\Z')
# Temporary schemas hold only the inspecting session's own objects. Every other
# schema, including pg_catalog and information_schema, is inventoried.
INVENTORIED = "n.nspname !~ '^pg_(toast_)?temp_'"
TEMPORARY = "n.nspname ~ '^pg_(toast_)?temp_'"
# Catalog access every fresh login already has: initdb's PUBLIC grants recorded
# in pg_init_privs, and information_schema's public views. Its _pg_* helpers
# expose raw foreign-server/user-mapping options and are never baseline.
BASELINE = """CASE WHEN n.nspname='information_schema' THEN p.privilege='SELECT' AND c.relname !~ '^_pg_'
     WHEN n.nspname ~ '^pg_' THEN EXISTS(SELECT 1 FROM pg_init_privs i CROSS JOIN LATERAL aclexplode(i.initprivs) e
       WHERE i.classoid='pg_class'::regclass AND i.objoid=c.oid AND i.objsubid IN (0,{column})
         AND i.privtype='i' AND e.grantee=0 AND e.privilege_type=p.privilege)
     ELSE false END"""
# PostgreSQL 17 MAINTAIN permits VACUUM/ANALYZE/REINDEX and LOCK TABLE in any mode.
TABLE_PRIVILEGES = """unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER']
     || CASE WHEN current_setting('server_version_num')::int>=170000 THEN ARRAY['MAINTAIN'] ELSE ARRAY[]::text[] END)"""
# Authority that is not a relation grant. Each check is effective for this
# NOINHERIT, membership-free login: its own entries plus PUBLIC.
OUTSIDE_AUTHORITY = """
SELECT NOT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
         WHERE p.prosecdef AND """ + INVENTORIED + """ AND has_function_privilege(:oid,p.oid,'EXECUTE'))
  -- Non-table delegation is authority too, including otherwise ordinary
  -- invoker routines, type usage and trusted-language usage.
  AND NOT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
         WHERE """ + INVENTORIED + """ AND has_function_privilege(:oid,p.oid,'EXECUTE WITH GRANT OPTION'))
  AND NOT EXISTS(SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
         WHERE """ + INVENTORIED + """ AND has_type_privilege(:oid,t.oid,'USAGE WITH GRANT OPTION'))
  AND NOT EXISTS(SELECT 1 FROM pg_language l WHERE has_language_privilege(:oid,l.oid,'USAGE WITH GRANT OPTION'))
  -- An owner may ALTER or DROP its object (a guard function, a type, ...) in any
  -- database. pg_shdepend records ownership of every object class; only the
  -- login's own temporary relations, row types and functions are exempt.
  AND NOT EXISTS(SELECT 1 FROM pg_shdepend d
         WHERE d.refclassid='pg_authid'::regclass AND d.refobjid=:oid AND d.deptype='o'
           AND NOT (d.dbid=(SELECT oid FROM pg_database WHERE datname=current_database()) AND (
             (d.classid='pg_class'::regclass AND EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE c.oid=d.objid AND """ + TEMPORARY + """))
             OR (d.classid='pg_type'::regclass AND EXISTS(SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
                WHERE t.oid=d.objid AND """ + TEMPORARY + """))
             OR (d.classid='pg_proc'::regclass AND EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE p.oid=d.objid AND """ + TEMPORARY + """)))))
  -- Catalog routines initdb withholds from PUBLIC: server files, logs, WAL, signals.
  AND NOT EXISTS(SELECT 1 FROM pg_init_privs i
         WHERE i.classoid='pg_proc'::regclass AND i.objsubid=0 AND i.privtype='i'
           AND NOT EXISTS(SELECT 1 FROM aclexplode(i.initprivs) e WHERE e.grantee=0 AND e.privilege_type='EXECUTE')
           AND EXISTS(SELECT 1 FROM pg_proc p WHERE p.oid=i.objoid AND has_function_privilege(:oid,p.oid,'EXECUTE')))
  -- pg_settings hides superuser-only parameters from this login; ACL rows do not.
  -- A parameter without a row has the default ACL, which grants a non-superuser nothing.
  AND NOT EXISTS(SELECT 1 FROM pg_parameter_acl a
         WHERE has_parameter_privilege(:oid,a.parname,'SET') OR has_parameter_privilege(:oid,a.parname,'ALTER SYSTEM'))
  AND current_setting('lo_compat_privileges')='off'
  AND NOT EXISTS(SELECT 1 FROM pg_largeobject_metadata m
         WHERE EXISTS(SELECT 1 FROM aclexplode(m.lomacl) e WHERE e.grantee IN (0,:oid)))
  AND NOT EXISTS(SELECT 1 FROM pg_foreign_data_wrapper w WHERE has_foreign_data_wrapper_privilege(:oid,w.oid,'USAGE'))
  AND NOT EXISTS(SELECT 1 FROM pg_foreign_server s WHERE has_server_privilege(:oid,s.oid,'USAGE'))
  AND NOT EXISTS(SELECT 1 FROM pg_user_mappings u WHERE u.umuser=:oid)
  -- Login defaults apply at connection, never to the installer's SET LOCAL ROLE.
  -- The dedicated login carries none. A database-wide default may set a built-in
  -- user-context parameter, or a custom placeholder outside every installed
  -- extension's prefix: whether an extension's library is loaded varies by
  -- session, so its parameters are refused rather than judged by visibility.
  AND NOT EXISTS(SELECT 1 FROM pg_db_role_setting d
         CROSS JOIN LATERAL unnest(d.setconfig) c(setting)
         CROSS JOIN LATERAL (SELECT lower(split_part(c.setting,'=',1)) AS name) g
         WHERE d.setdatabase IN (0,(SELECT oid FROM pg_database WHERE datname=current_database()))
           AND (d.setrole=:oid OR (d.setrole=0 AND NOT CASE WHEN g.name LIKE '%.%' THEN
               split_part(g.name,'.',1) NOT IN (SELECT lower(extname) FROM pg_extension)
               AND NOT EXISTS(SELECT 1 FROM pg_settings s WHERE lower(s.name)=g.name AND s.context<>'user')
             ELSE EXISTS(SELECT 1 FROM pg_settings s WHERE lower(s.name)=g.name AND s.context='user') END)))
"""


class WorkerRoleError(RuntimeError):
    """Fixed diagnostic; no connection string, SQL, rows or driver exception."""


def _require(value):
    if value is not True:
        raise WorkerRoleError('WORKER_ROLE_UNAVAILABLE')


def _scope(role, schema):
    _require(type(role) is str and IDENTIFIER.fullmatch(role) is not None
             and not role.startswith('pg_') and role not in {'postgres', 'anon', 'authenticated', 'service_role', 'public'})
    _require(type(schema) is str and IDENTIFIER.fullmatch(schema) is not None
             and not schema.startswith('pg_') and schema != 'information_schema')


def _quoted(conn, name):
    return conn.dialect.identifier_preparer.quote_identifier(name)


def _limits(conn):
    conn.execute(text("SET LOCAL statement_timeout='5s'"))
    conn.execute(text("SET LOCAL lock_timeout='2s'"))
    # Catalog checks resolve every function and relation in pg_catalog first, so
    # an object in a user schema cannot stand in for a builtin; worker
    # relations are named with their schema.
    conn.execute(text("SET LOCAL search_path=pg_catalog,pg_temp"))


def _identity(conn, role, schema, *, current):
    row = conn.execute(text('SELECT oid,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb,rolreplication,rolinherit,rolcanlogin,rolconnlimit FROM pg_roles WHERE rolname=:role'), {'role': role}).mappings().one()
    _require(not any(row[key] for key in ('rolsuper', 'rolbypassrls', 'rolcreaterole', 'rolcreatedb', 'rolreplication', 'rolinherit')))
    _require(row['rolcanlogin'] is True and row['rolconnlimit'] == 2)
    oid = row['oid']
    _require(conn.execute(text("SELECT NOT EXISTS(SELECT 1 FROM pg_roles WHERE oid<>:oid AND pg_has_role(:oid,oid,'MEMBER'))"), {'oid': oid}).scalar())
    _require(conn.execute(text('SELECT NOT EXISTS(SELECT 1 FROM pg_database WHERE datdba=:oid)'), {'oid': oid}).scalar())
    _require(conn.execute(text("SELECT NOT EXISTS(SELECT 1 FROM pg_namespace WHERE nspowner=:oid AND nspname NOT LIKE 'pg_temp_%' AND nspname NOT LIKE 'pg_toast_temp_%')"), {'oid': oid}).scalar())
    _require(conn.execute(text("SELECT NOT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relowner=:oid AND " + INVENTORIED + ")"), {'oid': oid}).scalar())
    _require(conn.execute(text("SELECT NOT EXISTS(SELECT 1 FROM pg_namespace n WHERE " + INVENTORIED + " AND (has_schema_privilege(:oid,n.oid,'CREATE') OR has_schema_privilege(:oid,n.oid,'USAGE WITH GRANT OPTION')))"), {'oid': oid}).scalar())
    _require(conn.execute(text("SELECT NOT EXISTS(SELECT 1 FROM pg_database WHERE has_database_privilege(:oid,oid,'CREATE') OR has_database_privilege(:oid,oid,'CONNECT WITH GRANT OPTION,TEMP WITH GRANT OPTION,CREATE WITH GRANT OPTION'))"), {'oid': oid}).scalar())
    _require(conn.execute(text(OUTSIDE_AUTHORITY), {'oid': oid}).scalar())
    _require(conn.execute(text("SHOW session_replication_role")).scalar() == 'origin')
    # Explicit default ACLs of any object class must not widen future access.
    # This includes function EXECUTE and schema/type delegation, not only rows.
    _require(conn.execute(text("SELECT NOT EXISTS(SELECT 1 FROM pg_default_acl d CROSS JOIN LATERAL aclexplode(d.defaclacl) a WHERE a.grantee IN (0,:oid))"), {'oid': oid}).scalar())
    _require(conn.execute(text('SELECT to_regnamespace(:schema) IS NOT NULL'), {'schema': schema}).scalar())
    if current:
        identity = conn.execute(text('SELECT current_user,session_user')).one()
        _require(tuple(identity) == (role, role))
    return oid


def _grants(conn, role, schema, *, complete, platforms=False):
    contract = selected_contract(platforms=platforms)
    # Three catalog queries regardless of relation/column count. Checking every
    # privilege with a separate round trip makes startup prohibitively slow on
    # a hosted database shared with the application's other tables.
    objects = list(conn.execute(text("""
        SELECT c.oid,n.nspname,c.relname,c.relkind,c.relrowsecurity,
               CASE WHEN c.relkind='S' THEN
                 has_sequence_privilege(:role,c.oid,'USAGE,SELECT,UPDATE')
               ELSE false END AS sequence_access,
               CASE WHEN n.nspname=:schema AND c.relname='social_native_source_authority' AND c.relkind='v'
                 THEN has_table_privilege(:role,c.oid,'SELECT') ELSE false END AS native_effective_read,
               CASE WHEN n.nspname=:schema AND c.relname='social_native_source_authority' AND c.relkind='v'
                 THEN EXISTS(SELECT 1 FROM aclexplode(c.relacl) a
                   WHERE a.grantee=(SELECT oid FROM pg_roles WHERE rolname=:role)
                     AND a.privilege_type='SELECT' AND NOT a.is_grantable)
                 ELSE false END AS native_direct_read,
               CASE WHEN n.nspname=:schema AND c.relname='social_native_source_authority' AND c.relkind='v'
                 THEN NOT EXISTS(SELECT 1 FROM aclexplode(c.relacl) a
                   WHERE a.grantee<>c.relowner AND
                     (a.grantee<>(SELECT oid FROM pg_roles WHERE rolname=:role)
                      OR a.privilege_type<>'SELECT' OR a.is_grantable))
                 ELSE true END AS native_scoped_acl
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE """ + INVENTORIED + """ AND c.relkind IN ('r','p','v','m','f','S')
    """), {'role': role, 'schema': schema}).mappings())
    found = set()
    optional_reads = set()
    for obj in objects:
        table = obj['relname'] if obj['nspname'] == schema else None
        if table in READ_VIEWS | OPTIONAL_READ_VIEWS:
            _require(obj['relkind'] == 'v' and obj['relrowsecurity'] is False)
        if table in OPTIONAL_READ_VIEWS:
            # A prior explicit, complete grant is tolerated by the runtime/base
            # installer. Effective PUBLIC/role/column access cannot stand in
            # for that direct table grant; the base installer never creates it.
            _require(obj['native_scoped_acl'] is True
                     and type(obj['native_effective_read']) is bool
                     and obj['native_effective_read'] is obj['native_direct_read'])
            if obj['native_direct_read'] is True:
                optional_reads.add(table)
        if table in contract.tables:
            found.add(table)
            _require(obj['relkind'] == 'r' and obj['relrowsecurity'] is True)
        _require(obj['sequence_access'] is False)
    _require(found == contract.tables)
    read_relations = contract.read_relations | optional_reads
    tables = conn.execute(text("""
        SELECT n.nspname,c.relname,p.privilege,
               has_table_privilege(:role,c.oid,p.privilege) AS present,
               has_table_privilege(:role,c.oid,p.privilege||' WITH GRANT OPTION') AS grantable,
               """ + BASELINE.format(column='0') + """ AS baseline
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        CROSS JOIN """ + TABLE_PRIVILEGES + """ p(privilege)
        WHERE """ + INVENTORIED + """ AND c.relkind IN ('r','p','v','m','f')
    """), {'role': role})
    # Baseline catalog access is tolerated, never required: revoking it only narrows.
    for namespace, table, privilege, present, grantable, baseline in tables:
        required = namespace == schema and table in read_relations and privilege == 'SELECT'
        _require(not grantable and (not present or required or baseline)
                 and (not complete or not required or present))
    columns = conn.execute(text("""
        SELECT n.nspname,c.relname,a.attname,p.privilege,
               has_column_privilege(:role,c.oid,a.attnum,p.privilege) AS present,
               has_column_privilege(:role,c.oid,a.attnum,p.privilege||' WITH GRANT OPTION') AS grantable,
               """ + BASELINE.format(column='a.attnum') + """ AS baseline
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
        CROSS JOIN (VALUES ('SELECT'),('INSERT'),('UPDATE'),('REFERENCES')) p(privilege)
        WHERE """ + INVENTORIED + """ AND c.relkind IN ('r','p','v','m','f')
    """), {'role': role})
    for namespace, table, column, privilege, present, grantable, baseline in columns:
        required = namespace == schema and (
            table in read_relations if privilege == 'SELECT' else
            column in (contract.inserts if privilege == 'INSERT' else
                       contract.updates if privilege == 'UPDATE' else {}).get(table, ()))
        _require(not grantable and (not present or required or baseline)
                 and (not complete or not required or present))


@dataclass(frozen=True)
class Policy:
    table: str
    name: str
    command: str
    permissive: bool
    using: str | None
    check: str | None


def _policies(*, platforms=False):
    contract = selected_contract(platforms=platforms)
    result = [Policy(table, 'scw_read', 'r', True, 'true', None) for table in sorted(contract.read_tables)]
    for table in sorted(contract.updates):
        using, check = ('true', 'false') if table in contract.lock_tables else ('(completed_at IS NULL)', '(completed_at IS NOT NULL)') if table == 'social_publish_attempts' else ('true', 'true')
        result.extend(Policy(table, name, 'w', permissive, using, check) for name, permissive in [('scw_update', True), ('scw_update_fence', False)])
    for table in sorted(contract.inserts):
        check = ("(actor_kind = 'worker'::text)" if table == 'social_audit_events' else
                 "(event = 'acquired'::text)" if table == 'social_worker_runtime_history' else 'true')
        result.extend(Policy(table, name, 'a', permissive, None, check) for name, permissive in [('scw_insert', True), ('scw_insert_fence', False)])
    return result


def _policy_rows(conn, oid, schema, *, platforms=False):
    # A policy does not grant table access. Unrelated PUBLIC policies cannot
    # affect the worker while _grants denies all out-of-contract privileges.
    # Still inventory every explicit worker policy and reserved policy name.
    return list(conn.execute(text('''
        SELECT c.relname AS "table",p.polname AS name,p.polcmd AS command,
               p.polpermissive AS permissive,p.polroles AS roles,
               pg_get_expr(p.polqual,p.polrelid) AS "using",
               pg_get_expr(p.polwithcheck,p.polrelid) AS "check"
        FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=:schema AND (
            p.polroles @> ARRAY[CAST(:oid AS oid)] OR p.polname LIKE 'scw_%'
            OR (c.relname=ANY(:tables) AND p.polroles @> ARRAY[CAST(0 AS oid)]))
    '''), {'oid': oid, 'schema': schema, 'tables': sorted(selected_contract(platforms=platforms).tables)}).mappings())


def _policy_matches(row, policy, oid):
    return (row['table'] == policy.table and row['name'] == policy.name
            and row['command'] == policy.command and row['permissive'] is policy.permissive
            and list(row['roles']) == [oid] and row['using'] == policy.using and row['check'] == policy.check)


def _check_policies(conn, oid, schema, *, complete, platforms=False):
    expected = {(p.table, p.name): p for p in _policies(platforms=platforms)}
    rows = _policy_rows(conn, oid, schema, platforms=platforms)
    seen = set()
    for row in rows:
        key = row['table'], row['name']
        _require(key in expected and _policy_matches(row, expected[key], oid))
        seen.add(key)
    _require(not complete or seen == expected.keys())
    return seen


# Bodies from f38c61a9d203, including its reviewed trigger wiring. These hashes
# are schema-independent (pg_proc.prosrc); a future guard migration must update
# this contract deliberately. No function is installed/repaired by this check.
GUARD_SOURCES = {
    'social_guard_policy_decision': 'd7cd5ec9550449b8834346d12f7faed8cab5ad6442d518a335b63f9b66946f18',
    'social_deny_history_mutation': '0d32cba5e232bfff95b7e2d23ad1fe311b40da64258e6ef6c0e945fd811d957a',
    'social_guard_target_payload': '866879740f52eb3f17888c801729695c56e9fd5f1f4213804da1887f12e9618c',
    'social_guard_authorization': '2a825e76bd7af78352e7b59d019bf88e07fd19432b38a5e4e28294c97a344ec9',
    'social_guard_ready_asset': '9ce9b11cc7a1a664287e627a93456e8bb988438d25a29f6ea4d77bb74159e970',
    'social_worker_owner_guard': 'c34abb544af92aa0338ebfd8a236ef2f2e21376208f29ff0018c8052413d23b7',
    'social_worker_owner_acquired': '5537aa74d7d97f5d9d2bb8dc17b84f3401725653f73cb87f8ef879521675597e',
    'social_worker_history_guard': '6fab44b2ffff522a542da51786a36b592afb96cb84e172b60068d17f330c5fbe',
}
TRIGGERS = {
    ('social_publications', 'social_publication_policy_immutable'): ('social_guard_policy_decision', 19),
    ('social_source_events', 'social_source_events_immutable'): ('social_deny_history_mutation', 27),
    ('social_automation_rule_versions', 'social_automation_rule_versions_immutable'): ('social_deny_history_mutation', 27),
    ('social_policy_operating_evidence', 'social_policy_operating_evidence_immutable'): ('social_deny_history_mutation', 27),
    ('social_authorized_policy_snapshots', 'social_authorized_policy_snapshots_immutable'): ('social_deny_history_mutation', 27),
    ('social_policy_decisions', 'social_policy_decisions_immutable'): ('social_deny_history_mutation', 27),

    ('social_post_revisions', 'social_revision_immutable'): ('social_deny_history_mutation', 27),
    ('social_audit_events', 'social_audit_immutable'): ('social_deny_history_mutation', 27),
    ('social_post_targets', 'social_target_payload_immutable'): ('social_guard_target_payload', 19),
    ('social_publications', 'social_publication_authorization_immutable'): ('social_guard_authorization', 19),
    ('social_media_assets', 'social_ready_asset_immutable'): ('social_guard_ready_asset', 19),
    ('social_worker_runtime_ownership', 'social_worker_owner_guard'): ('social_worker_owner_guard', 31),
    ('social_worker_runtime_ownership', 'social_worker_owner_acquired'): ('social_worker_owner_acquired', 5),
    ('social_worker_runtime_history', 'social_worker_history_guard'): ('social_worker_history_guard', 31),
}


def _triggers(conn, schema, *, platforms=False):
    contract = selected_contract(platforms=platforms)
    rows = conn.execute(text("""
        SELECT c.relname,t.tgname,t.tgtype,t.tgenabled,t.tgqual IS NULL AS unqualified,
               cardinality(t.tgattr::int2[])=0 AS all_columns,
               t.tgnargs,t.tgconstraint,p.proname,p.prosrc,p.prosecdef,
               p.proconfig,pn.nspname AS function_schema,l.lanname
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_proc p ON p.oid=t.tgfoid JOIN pg_namespace pn ON pn.oid=p.pronamespace
        JOIN pg_language l ON l.oid=p.prolang
        WHERE n.nspname=:schema AND c.relname=ANY(:tables) AND NOT t.tgisinternal
    """), {'schema': schema, 'tables': sorted(contract.tables)}).mappings()
    seen = set()
    for row in rows:
        key = row['relname'], row['tgname']
        _require(key in TRIGGERS)
        function, kind = TRIGGERS[key]
        _require(row['proname'] == function and row['function_schema'] == schema
                 and row['tgtype'] == kind and row['tgenabled'] in ('O', 'A')
                 and row['unqualified'] is True and row['all_columns'] is True and row['tgnargs'] == 0
                 and row['tgconstraint'] == 0 and row['prosecdef'] is False
                 and (row['proconfig'] is None if not function.startswith('social_worker_') else
                      row['proconfig'] is not None and len(row['proconfig']) == 1
                      and row['proconfig'][0].replace(' ', '').replace('"', '') == 'search_path=pg_catalog,' + schema + ',pg_temp')
                 and row['lanname'] == 'plpgsql'
                 and hashlib.sha256(row['prosrc'].encode()).hexdigest() == GUARD_SOURCES[function])
        seen.add(key)
    _require(seen == TRIGGERS.keys())
    # Rule actions are permission-checked as the table owner, like a definer.
    _require(conn.execute(text("""
        SELECT NOT EXISTS(SELECT 1 FROM pg_rewrite r JOIN pg_class c ON c.oid=r.ev_class
          JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:schema AND c.relname=ANY(:tables))
    """), {'schema': schema, 'tables': sorted(contract.tables)}).scalar())


def _views(conn, schema):
    rows = list(conn.execute(text("""SELECT c.relname,c.reloptions,pg_get_viewdef(c.oid,true) AS definition,
        c.relowner=(SELECT relowner FROM pg_class WHERE oid=to_regclass(quote_ident(:schema)||'.social_source_events')) AS source_owner,
        c.relowner=(SELECT relowner FROM pg_class WHERE oid=to_regclass(quote_ident(:schema)||'.budget_lines')) AS application_owner,
        ARRAY(SELECT a.atttypid::regtype::text FROM pg_attribute a WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum) AS types,
        (SELECT count(*)=1 AND bool_and(r.rulename='_RETURN' AND r.ev_type='1' AND r.is_instead AND r.ev_enabled='O') FROM pg_rewrite r WHERE r.ev_class=c.oid) AS exact_return_rule,
        ARRAY(SELECT a.attname::text FROM pg_attribute a WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum) AS columns
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=:schema AND c.relname=ANY(:views) AND c.relkind='v'"""),
        {'schema': schema, 'views': sorted(REPORT_VIEW_SHA256)}).mappings())
    # Historical pre-708 schemas have no report authority. A 708 schema must
    # contain the exact view even when no report has been generated yet.
    report_schema = conn.execute(text('''SELECT EXISTS(SELECT 1 FROM pg_attribute
        WHERE attrelid=to_regclass(quote_ident(:schema)||'.social_source_cursors')
          AND attname='report_state' AND NOT attisdropped)'''), {'schema': schema}).scalar()
    if not rows:
        _require(report_schema is False)
    else:
        _require(len(rows) == len(REPORT_VIEW_SHA256) and report_schema is True)
        for row in rows:
            _require(row['relname'] in REPORT_VIEW_SHA256
                     and row['source_owner'] is True and row['application_owner'] is True
                     and row['exact_return_rule'] is True
                 and list(row['types']) == ['integer', 'integer', 'text']
                 and list(row['reloptions'] or []) == ['security_barrier=true']
                 and list(row['columns']) == ['record_id', 'ingestion_id', 'authority_fingerprint'])
            definition = row['definition']
            for clause in ('FROM ', 'JOIN '):
                definition = definition.replace(clause+_quoted(conn, schema)+'.', clause).replace(clause+schema+'.', clause)
            accepted = {REPORT_VIEW_SHA256[row['relname']]}
            if row['relname'] == 'social_report_source_authority':
                accepted.add(REPORT_LOCKED_VIEW_HISTORICAL_SHA256)
            _require(hashlib.sha256(definition.encode()).hexdigest() in accepted)

    native = list(conn.execute(text('''SELECT c.relname,c.reloptions,pg_get_viewdef(c.oid,true) AS definition,
        c.relowner=(SELECT relowner FROM pg_class WHERE oid=to_regclass(quote_ident(:schema)||'.social_source_events')) AS source_owner,
        c.relowner=(SELECT relowner FROM pg_class WHERE oid=to_regclass(quote_ident(:schema)||'.budget_lines')) AS application_owner,
        ARRAY(SELECT a.attname::text FROM pg_attribute a WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum) AS columns,
        ARRAY(SELECT a.atttypid::regtype::text FROM pg_attribute a WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum) AS types,
        (SELECT count(*)=1 AND bool_and(r.rulename='_RETURN' AND r.ev_type='1' AND r.is_instead AND r.ev_enabled='O') FROM pg_rewrite r WHERE r.ev_class=c.oid) AS exact_return_rule,
        NOT EXISTS(SELECT 1 FROM aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) a
          WHERE a.grantee=0 OR (a.grantee<>c.relowner AND
            (c.relname='social_native_source_authority_snapshot' OR a.privilege_type<>'SELECT' OR a.is_grantable)))
        AND NOT EXISTS(SELECT 1 FROM pg_attribute a CROSS JOIN LATERAL aclexplode(a.attacl) e
          WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped AND e.grantee<>c.relowner) AS private_acl
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:schema
          AND c.relname IN ('social_native_source_authority','social_native_source_authority_snapshot') AND c.relkind='v'
    '''),{'schema':schema}).mappings())
    if native:
        _require(len(native)==2 and len(NATIVE_VIEW_SHA256)==2)
        for row in native:
            _require(row['source_owner'] is True and row['application_owner'] is True and row['exact_return_rule'] is True
                and row['private_acl'] is True
                and list(row['columns'])==['source_kind','native_domain','record_id','ingestion_id','authority_fingerprint']
                and list(row['types'])==['text','text','integer','integer','text']
                and list(row['reloptions'] or [])==['security_barrier=true'])
            definition=row['definition']
            for clause in ('FROM ','JOIN '):
                definition=definition.replace(clause+_quoted(conn,schema)+'.',clause).replace(clause+schema+'.',clause)
            _require(hashlib.sha256(definition.encode()).hexdigest()==NATIVE_VIEW_SHA256.get(row['relname']))


def _verify(conn, role, schema, *, current, platforms=False):
    oid = _identity(conn, role, schema, current=current)
    _triggers(conn, schema, platforms=platforms)
    _views(conn, schema)
    _grants(conn, role, schema, complete=True, platforms=platforms)
    _check_policies(conn, oid, schema, complete=True, platforms=platforms)
    # This proves the lock-only policy sees the actual singleton; an UPDATE
    # policy with only WITH CHECK false can otherwise silently hide the row.
    _require(list(conn.execute(text('SELECT id FROM ' + _quoted(conn, schema) + '.social_controls WHERE id=1 FOR UPDATE')).scalars()) == [1])


def verify_worker_role(engine, role, schema='public', *, platforms=False):
    failed = False
    try:
        _scope(role, schema)
        selected_contract(platforms=platforms)
        _require(isinstance(engine, Engine))
        with engine.begin() as conn:
            _limits(conn)
            _verify(conn, role, schema, current=True, platforms=platforms)
    except Exception:
        failed = True
    if failed:
        raise WorkerRoleError('WORKER_ROLE_UNAVAILABLE')


def install_worker_role(engine, role, schema='public', *, platforms=False):
    """Grant only this contract to an existing role, atomically or not at all.

    Never create/alter a login, password, database or default/PUBLIC privilege.
    Unexpected prior authority refuses installation rather than being hidden by
    a best-effort revoke. The caller separately approves this operator action.
    """
    failed = False
    try:
        _scope(role, schema)
        contract = selected_contract(platforms=platforms)
        _require(isinstance(engine, Engine))
        with engine.begin() as conn:
            _limits(conn)
            oid = _identity(conn, role, schema, current=False)
            _triggers(conn, schema, platforms=platforms)
            _views(conn, schema)
            _grants(conn, role, schema, complete=False, platforms=platforms)
            existing = _check_policies(conn, oid, schema, complete=False, platforms=platforms)
            quoted_role, quoted_schema = _quoted(conn, role), _quoted(conn, schema)
            conn.execute(text('GRANT USAGE ON SCHEMA ' + quoted_schema + ' TO ' + quoted_role))
            for table in sorted(contract.read_relations):
                if table in READ_VIEWS and conn.execute(text('SELECT to_regclass(quote_ident(:schema)||\'.\'||quote_ident(:table)) IS NULL'), {'schema': schema, 'table': table}).scalar():
                    continue
                conn.execute(text('GRANT SELECT ON ' + quoted_schema + '.' + _quoted(conn, table) + ' TO ' + quoted_role))
            for command, matrix in [('INSERT', contract.inserts), ('UPDATE', contract.updates)]:
                for table, columns in sorted(matrix.items()):
                    fields = ','.join(_quoted(conn, column) for column in sorted(columns))
                    conn.execute(text('GRANT ' + command + '(' + fields + ') ON ' + quoted_schema + '.' + _quoted(conn, table) + ' TO ' + quoted_role))
            for policy in _policies(platforms=platforms):
                if (policy.table, policy.name) in existing:
                    continue
                command = {'r': 'SELECT', 'w': 'UPDATE', 'a': 'INSERT'}[policy.command]
                sql = ('CREATE POLICY ' + _quoted(conn, policy.name) + ' ON ' + quoted_schema + '.' + _quoted(conn, policy.table)
                       + ' AS ' + ('PERMISSIVE' if policy.permissive else 'RESTRICTIVE') + ' FOR ' + command + ' TO ' + quoted_role)
                if policy.using is not None:
                    sql += ' USING (' + policy.using + ')'
                if policy.check is not None:
                    sql += ' WITH CHECK (' + policy.check + ')'
                conn.execute(text(sql))
            _verify(conn, role, schema, current=False, platforms=platforms)
            # SET LOCAL never persists a changed identity in the operator pool.
            conn.execute(text('SET LOCAL ROLE ' + quoted_role))
            _verify(conn, role, schema, current=False, platforms=platforms)
    except Exception:
        failed = True
    if failed:
        raise WorkerRoleError('WORKER_ROLE_UNAVAILABLE')
