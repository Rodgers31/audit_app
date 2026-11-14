"""Read-only PostgreSQL and current-run semantic observations, never a connection URL."""
from common import canonical, digest, integer, loads, require, string
from acceptance_plans import plan_from_original


def readonly(session):
    from sqlalchemy import text
    require(session is not None and session.get_bind().dialect.name == 'postgresql',
            'actual PostgreSQL reader required')
    require(not session.new and not session.dirty and not session.deleted, 'clean committed reader required')
    require(session.scalar(text('SHOW transaction_read_only')) == 'on', 'read-only transaction required')
    require(session.scalar(text('SHOW row_security')) == 'off',
            'RLS must refuse invisible storage rather than certify an empty census')


def observe_catalog(session, tables, *, expected_revision, expected_role):
    """Observe resolved relations and ACL/RLS/role on the same read-only connection.

    This reports actual catalog facts. A revision string alone does not certify
    that a migration or a production role policy was applied.
    """
    from sqlalchemy import text
    readonly(session)
    require(type(tables) is list and bool(tables) and len(tables) <= 64
            and all(type(t) is str and t.isidentifier() for t in tables)
            and len(set(tables)) == len(tables), 'explicit unique relation inventory required')
    string(expected_revision); string(expected_role)
    identity = session.execute(text("""SELECT current_database(),current_schema(),current_user,
        session_user,host(inet_server_addr()),inet_server_port(),current_setting('search_path')""")).one()
    require(identity[2] == expected_role and identity[3] == expected_role, 'actual reader role differs')
    role = session.execute(text("""SELECT rolsuper,rolinherit,rolcreaterole,rolcreatedb,
        rolcanlogin,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user""")).one()
    revision_table = session.execute(text("""SELECT c.oid,n.nspname,c.relname,c.relkind
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE c.oid=to_regclass('alembic_version')""")).one_or_none()
    require(revision_table is not None and revision_table[1] == identity[1]
            and revision_table[2] == 'alembic_version' and revision_table[3] == 'r',
            'actual schema revision unavailable or shadowed')
    revisions = list(session.scalars(text('SELECT version_num FROM alembic_version')))
    require(revisions == [expected_revision], 'actual schema revision differs')
    rows = []
    for name in tables:
        row = session.execute(text("""SELECT n.nspname,c.relname,pg_get_userbyid(c.relowner),
            c.relrowsecurity,c.relforcerowsecurity,coalesce(c.relacl::text,''),c.relkind,
            pg_table_is_visible(c.oid) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE c.oid=to_regclass(:name)"""), {'name': name}).one_or_none()
        require(row is not None and row[0] == identity[1] and row[1] == name
                and row[6] in ('r', 'p') and row[7] is True, 'resolved relation missing/shadowed')
        columns = session.execute(text("""SELECT a.attname,format_type(a.atttypid,a.atttypmod),
            a.attnotnull,pg_get_expr(d.adbin,d.adrelid) FROM pg_attribute a
            LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
            WHERE a.attrelid=to_regclass(:name) AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum"""),
            {'name': name}).all()
        policies = session.execute(text("""SELECT policyname,permissive,roles::text,cmd,qual,with_check
            FROM pg_policies WHERE schemaname=:schema AND tablename=:name ORDER BY policyname"""),
            {'schema': row[0], 'name': name}).all()
        constraints = session.execute(text("""SELECT contype,convalidated,pg_get_constraintdef(oid)
            FROM pg_constraint WHERE conrelid=to_regclass(:name) ORDER BY contype,conname"""), {'name': name}).all()
        rows.append({'name': name, 'schema': row[0], 'owner': row[2], 'rls': row[3],
                     'force_rls': row[4], 'acl': row[5], 'columns': [list(c) for c in columns],
                     'policies': [list(p) for p in policies], 'constraints': [list(c) for c in constraints]})
    return {'schema': 'nightly-pg-catalog-observation-v1', 'identity': list(identity),
            'role_flags': list(role), 'revision': revisions[0], 'tables': rows,
            'policy_accepted': False}


def observe_current_run(session, plan_original, context, report_raw, *, kind='full15'):
    """Recompute the actual product classifier against actual unfiltered stored jobs."""
    from seeding.current_run import classify, load_current_jobs
    readonly(session)
    plan = plan_from_original(plan_original, kind)
    require(type(context) is dict, 'exact current-run context required')
    floor = integer(context.get('floor'))
    require(type(report_raw) is bytes and 0 < len(report_raw) <= 65536, 'bounded original CLI report bytes required')
    original = loads(report_raw)
    require(type(original) is dict, 'original current-run report object required')
    with session.no_autoflush:
        jobs, job_times = load_current_jobs(session, floor)
        recomputed = classify(jobs, plan, context, job_times=job_times)
    require(canonical(recomputed) == canonical(original), 'CLI/current-run report differs from actual PostgreSQL')
    require(original['classification'] != 'unsafe' and original['cache_eligible'] is True,
            'unsafe/unknown current-run cannot authorize refresh')
    # A recognized required-source hold can be refresh-eligible while source
    # completion remains red. Keep that distinction in the returned facts.
    return {'schema': 'nightly-current-run-observation-v1', 'report': recomputed,
            'source_complete': original['classification'] == 'complete',
            'cli_execution_proven': False, 'production_accepted': False}
