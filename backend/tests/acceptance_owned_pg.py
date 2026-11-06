"""One fail-closed owned-loopback contract for nightly acceptance fixtures.

The provisioner must mark its dedicated database before tests start. Each context
owns a fresh schema. No caller-supplied libpq option or ambient PG variable is
forwarded, and cleanup rechecks ownership before dropping that exact schema.
"""
from contextlib import contextmanager
import os
import re
import uuid


URL = 'postgresql+psycopg2://postgres@127.0.0.1:55432/auditgava_refresh_fixture'
PREFIX = 'nightly-acceptance-owned-v1:'
CLOSED_SCHEMAS = []


def validate_target(url, owned, token, environment=None):
    environment = os.environ if environment is None else environment
    if (type(url) is not str or url != URL or owned != 'true' or type(token) is not str
            or re.fullmatch('[0-9a-f]{32}', token) is None
            or any(key.upper().startswith('PG') for key in environment)):
        raise RuntimeError('Owned PostgreSQL fixture target/credential/environment override refused')
    return {'host': '127.0.0.1', 'hostaddr': '127.0.0.1', 'port': 55432,
            'dbname': 'auditgava_refresh_fixture', 'user': 'postgres', 'password': '',
            'passfile': '/nonexistent-nightly-acceptance-passfile', 'connect_timeout': 3,
            'application_name': 'nightly-acceptance-' + token[:12],
            'options': '-c statement_timeout=5000 -c lock_timeout=2000 -c idle_in_transaction_session_timeout=10000'}


def target_from_environment():
    url = os.environ.get('REFRESH_FIXTURE_PG_URL')
    args = validate_target(url, os.environ.get('REFRESH_FIXTURE_OWNED'),
                           os.environ.get('REFRESH_FIXTURE_TOKEN'))
    return url, os.environ['REFRESH_FIXTURE_TOKEN'], args


def _database(connection, token, database='auditgava_refresh_fixture'):
    from sqlalchemy import text
    if database not in ('auditgava_refresh_fixture', 'fiscal_fixture'):
        raise RuntimeError('Unknown dedicated PostgreSQL fixture database')
    row = connection.execute(text("""SELECT current_database(),current_user,session_user,
        host(inet_server_addr()),inet_server_port(),pg_get_userbyid(datdba),
        shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()""")).one()
    if tuple(row) != (database, 'postgres', 'postgres', '127.0.0.1',
                      55432, 'postgres', PREFIX + token):
        raise RuntimeError('Actual owned PostgreSQL database/server/role identity refused before DDL')
    return tuple(row[:6])


@contextmanager
def owned_reader(schema, *, token):
    """Inspect an existing fixture schema without creating, repairing or dropping it."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import NullPool
    args = validate_target(URL, 'true', token)
    if (type(schema) is not str
            or re.fullmatch('acceptance_' + token[:16] + '_[0-9a-f]{12}', schema) is None):
        raise RuntimeError('Owned PostgreSQL reader schema refused')
    args['options'] += (' -c search_path=' + schema + ',pg_catalog'
                        ' -c default_transaction_read_only=on -c row_security=off')
    engine = create_engine(URL, connect_args=args, poolclass=NullPool, isolation_level='REPEATABLE READ')
    try:
        with Session(engine) as session:
            _database(session, token)
            owner = session.execute(text("""SELECT pg_get_userbyid(nspowner),obj_description(oid,'pg_namespace')
                FROM pg_namespace WHERE nspname=:schema"""), {'schema': schema}).one_or_none()
            if tuple(owner or ()) != ('postgres', PREFIX + token):
                raise RuntimeError('Existing owned PostgreSQL reader schema ownership differs')
            yield session
    finally:
        engine.dispose()


@contextmanager
def owned_schema():
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.pool import NullPool
    url, token, args = target_from_environment()  # No engine or connection before validation.
    schema = 'acceptance_' + token[:16] + '_' + uuid.uuid4().hex[:12]
    admin = create_engine(url, connect_args=args, poolclass=NullPool)
    engine, created = None, False
    try:
        with admin.begin() as connection:
            observed = _database(connection, token)
            connection.execute(text('CREATE SCHEMA ' + schema + ' AUTHORIZATION postgres'))
            connection.execute(text("COMMENT ON SCHEMA " + schema + " IS '" + PREFIX + token + "'"))
        created = True
        options = args['options'] + ' -c search_path=' + schema + ',pg_catalog'
        engine = create_engine(url, connect_args=dict(args, options=options), poolclass=NullPool)
        # This internally constructed URL is only for the real workflow subprocess;
        # the public fixture entry still accepts the single query-free URL above.
        child_url = make_url(url).set(query={'hostaddr': '127.0.0.1', 'connect_timeout': '3',
                                          'passfile': args['passfile'], 'options': options})
        engine.info_acceptance = {'schema': schema, 'identity': list(observed), 'token': token}
        yield engine, child_url.render_as_string(hide_password=False)
    finally:
        if engine is not None: engine.dispose()
        try:
            if created:
                with admin.begin() as connection:
                    _database(connection, token)
                    owner = connection.execute(text("""SELECT pg_get_userbyid(nspowner),
                        obj_description(oid,'pg_namespace') FROM pg_namespace WHERE nspname=:schema"""),
                        {'schema': schema}).one_or_none()
                    if tuple(owner or ()) != ('postgres', PREFIX + token):
                        raise RuntimeError('Owned PostgreSQL schema ownership changed; cleanup refused')
                    connection.execute(text('DROP SCHEMA ' + schema + ' CASCADE'))
                with admin.connect() as connection:
                    _database(connection, token)
                    if connection.scalar(text('SELECT count(*) FROM pg_namespace WHERE nspname=:schema'),
                                         {'schema': schema}) != 0:
                        raise RuntimeError('Owned PostgreSQL schema remains after cleanup')
                CLOSED_SCHEMAS.append({'schema': schema, 'database': observed[0], 'schema_absent': True})
        finally:
            admin.dispose()
