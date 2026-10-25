"""Bounded catalog-only qualification of the existing GitHub writer secrets.

No app imports, migrations, business rows, grants or credentials in output.
This certifies the observed target, not authority to run a seed or migration.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import parse_qsl, unquote, urlsplit

PROJECT = 'xznjxwrkbkahwtnbstbj'
CLUSTER = '7626352619084395911'
REVISION = 'a756b20a0001'
CA_HASH = '700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7'
CA = Path(__file__).with_name('supabase-project-ca.crt')
_spec = importlib.util.spec_from_file_location('github_database_tls_policy',
    Path(__file__).resolve().parents[2]/'backend/github_database_tls.py')
tls = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tls)
SECRETS = ('DATABASE_URL', 'DATABASE_POOLER_URL')
IDENTITY = """SELECT current_database(),current_user,session_user,d.oid::bigint,
 current_setting('server_version_num')::integer,
 current_setting('transaction_read_only'),current_setting('transaction_isolation'),
 pg_catalog.pg_is_in_recovery()
 FROM pg_catalog.pg_database d WHERE datname=current_database() LIMIT 2"""
READS = (IDENTITY,
         'SELECT system_identifier::text FROM pg_catalog.pg_control_system()',
         'SELECT version_num FROM public.alembic_version LIMIT 2',
         'SELECT pg_catalog.pg_database_size(current_database())')
SETTINGS = ('SET LOCAL statement_timeout=3000', 'SET LOCAL lock_timeout=1000',
            'SET LOCAL idle_in_transaction_session_timeout=5000',
            'SET LOCAL search_path=pg_catalog', 'SET LOCAL row_security=on',
            'SET LOCAL max_parallel_workers_per_gather=0', 'SET LOCAL work_mem=\'1MB\'')


class Refused(Exception):
    """Fixed diagnostic only: never retain driver/URL error messages."""


def connection_options(value):
    if (type(value) is not str or not 1 <= len(value) <= 8192
            or re.search(r'%(?![0-9a-fA-F]{2})', value)
            or any(ord(c) < 32 for c in value)):
        raise Refused('URL_REFUSED')
    try:
        url = urlsplit(value)
        user, password = unquote(url.username or ''), unquote(url.password or '')
        queries = parse_qsl(url.query, keep_blank_values=True, strict_parsing=True) if url.query else []
        direct = (url.hostname, url.port, user) == ('db.'+PROJECT+'.supabase.co', 5432, 'postgres')
        pooled = ((url.hostname, url.port, user) in
                  {('aws-1-eu-central-1.pooler.supabase.com', port, 'postgres.'+PROJECT)
                   for port in (5432, 6543)})
        valid = (url.scheme in ('postgres', 'postgresql', 'postgresql+psycopg2')
                 and url.path == '/postgres' and url.netloc.count('@') == 1 and not url.fragment
                 and password and '\x00' not in password and (direct or pooled)
                 and (not queries or queries == [('sslmode', 'require')]
                      or queries == [('sslmode', 'verify-full')]))
    except (ValueError, UnicodeError):
        raise Refused('URL_REFUSED') from None
    if not valid:
        raise Refused('URL_TARGET_OR_OPTIONS_REFUSED')
    return dict(host=url.hostname, port=url.port, dbname='postgres', user=user,
                password=password, sslmode='verify-full', connect_timeout=5,
                application_name='audit-github-target-qualification',
                options='-c default_transaction_read_only=on -c statement_timeout=3000',
                hostaddr='', gssencmode='disable')


def collect(connection):
    """Read four fixed, bounded catalog results and roll back before success."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
            for sql in SETTINGS:
                cursor.execute(sql)
            results = []
            for sql in READS:
                cursor.execute(sql)
                results.append(cursor.fetchmany(2))
        identity, cluster, revision, size = results
        if (type(identity) is not list or len(identity) != 1 or len(identity[0]) != 8
                or identity[0][:4] != ('postgres', 'postgres', 'postgres', 5)
                or type(identity[0][3]) is not int or type(identity[0][4]) is not int
                or not 170000 <= identity[0][4] < 180000
                or identity[0][5:] != ('on', 'repeatable read', False)
                or type(identity[0][7]) is not bool
                or cluster != [(CLUSTER,)] or revision != [(REVISION,)]
                or len(size) != 1 or len(size[0]) != 1
                or type(size[0][0]) is not int or not 0 < size[0][0] < 2**63):
            raise Refused('CATALOG_IDENTITY_REFUSED')
        if (connection.info.dsn_parameters.get('sslmode') != 'verify-full'
                or not connection.info.dsn_parameters.get('sslrootcert')
                or connection.info.ssl_in_use is not True
                or connection.info.ssl_attribute('protocol') not in ('TLSv1.2', 'TLSv1.3')):
            raise Refused('TLS_REFUSED')
        result = {'revision': REVISION, 'database_bytes': size[0][0],
                  'catalog_reads': len(READS), 'read_only': True, 'tls_verified': True}
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()
    return result


def qualify(value):
    options = connection_options(value)  # Refuse unrelated targets before credentials leave.
    ca = CA.read_bytes()
    if len(ca) != 1367 or hashlib.sha256(ca).hexdigest() != CA_HASH:
        raise Refused('CA_IDENTITY_REFUSED')
    # Retain the platform's normal public CA roots for the shared pooler,
    # plus the already accepted project-linked CA for its direct endpoint.
    system_ca = Path('/etc/ssl/certs/ca-certificates.crt').read_bytes()
    if not 1 <= len(system_ca) <= 1024*1024:
        raise Refused('SYSTEM_CA_REFUSED')
    import psycopg2
    with tempfile.NamedTemporaryFile() as roots:
        roots.write(system_ca + b'\n' + ca)
        roots.flush()
        connection = psycopg2.connect(**options, sslrootcert=roots.name)
        return collect(connection)


def main(args):
    if args == ['--prepare-writer-tls']:
        try:
            tls.prepare()
            return 0
        except Exception:
            print('WRITER_TLS_PREPARATION_REFUSED')
            return 2
    if len(args) == 2 and args[0] == '--child' and args[1] in SECRETS:
        try:
            for key in tuple(os.environ):
                if key.startswith('PG'):
                    del os.environ[key]
            result = qualify(os.environ[args[1]])
            print(json.dumps(result, sort_keys=True))
            return 0
        except Exception:
            print('DATABASE_QUALIFICATION_REFUSED')
            return 2
    if args not in (['--seed'], ['--all']):
        print('QUALIFICATION_ARGUMENTS_REFUSED')
        return 2
    if args == ['--seed']:
        try:
            if tls.connection_args().get('sslmode') != 'verify-full':
                raise Refused('WRITER_TLS_REFUSED')
        except Exception:
            print('WRITER_TLS_PREPARATION_REFUSED')
            return 2
    labels = SECRETS if args == ['--all'] else SECRETS[:1]
    reports = {}
    for label in labels:
        env = {k: v for k, v in os.environ.items()
               if k not in SECRETS and not k.startswith('PG')}
        env[label] = os.environ.get(label, '')
        try:
            child = subprocess.run([sys.executable, '-I', str(Path(__file__).resolve()),
                                    '--child', label], env=env, capture_output=True,
                                   text=True, timeout=20, check=False)
            if child.returncode != 0 or len(child.stdout) > 4096:
                raise Refused('CHILD_REFUSED')
            report = json.loads(child.stdout)
            if (type(report) is not dict or set(report) !=
                    {'revision','database_bytes','catalog_reads','read_only','tls_verified'}
                    or report['read_only'] is not True or report['tls_verified'] is not True
                    or report['revision'] != REVISION or type(report['catalog_reads']) is not int
                    or report['catalog_reads'] != 4 or type(report['database_bytes']) is not int
                    or not 0 < report['database_bytes'] < 2**63):
                raise Refused('REPORT_REFUSED')
            reports[label] = report
        except (OSError, ValueError, Refused, subprocess.TimeoutExpired):
            print(json.dumps({'qualification':'refused', 'connection':label}))
            return 2
    print(json.dumps({'qualification':'target_verified_read_only', 'connections':reports}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
