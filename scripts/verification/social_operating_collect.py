#!/usr/bin/env python3
"""Explicit opt-in, bounded PostgreSQL statistics collection; never billing acceptance."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

if __package__:
    from . import evaluate_social_operating_budget as budget
else:
    import evaluate_social_operating_budget as budget

MAX_OUTPUT = 65_536
MAX_QUERIES = 50
BEGIN = 'BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'
IDENTITY_SQL = """
SELECT clock_timestamp(), current_database(), d.oid, current_user, session_user,
       current_setting('transaction_read_only'),
       current_setting('statement_timeout'), current_setting('lock_timeout'),
       current_setting('server_version_num')::integer,
       EXISTS (SELECT 1 FROM pg_catalog.pg_roles r
         WHERE pg_has_role(current_user, r.oid, 'MEMBER')
         AND (r.rolsuper OR r.rolbypassrls OR r.rolcreaterole OR r.rolcreatedb OR r.rolreplication)),
       EXISTS (SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
         WHERE left(n.nspname,3) <> 'pg_' AND n.nspname <> 'information_schema'
         AND c.relkind IN ('r','p','v','m','f')
         AND (has_table_privilege(current_user,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER')
              OR has_any_column_privilege(current_user,c.oid,'INSERT,UPDATE')
              OR pg_has_role(current_user,c.relowner,'MEMBER'))),
       EXISTS (SELECT 1 FROM pg_catalog.pg_namespace n
         WHERE left(n.nspname,3) <> 'pg_' AND n.nspname <> 'information_schema'
         AND has_schema_privilege(current_user,n.oid,'CREATE')),
       has_database_privilege(current_user,d.oid,'CREATE,TEMP')
FROM pg_catalog.pg_database d WHERE d.datname=current_database() LIMIT 2
"""
EXTENSION_SQL = """
SELECT n.nspname, e.extversion,
 EXISTS (SELECT 1 FROM pg_catalog.pg_attribute a
  WHERE a.attrelid=to_regclass(n.nspname || '.pg_stat_statements')
  AND a.attname='stats_since' AND NOT a.attisdropped),
 EXISTS (SELECT 1 FROM pg_catalog.pg_attribute a
  WHERE a.attrelid=to_regclass(n.nspname || '.pg_stat_statements_info')
  AND a.attname='dealloc' AND NOT a.attisdropped)
FROM pg_catalog.pg_extension e JOIN pg_catalog.pg_namespace n ON n.oid=e.extnamespace
WHERE e.extname='pg_stat_statements' LIMIT 2
"""
CLOCK_SQL = 'SELECT clock_timestamp()'
# No query text, parameters, application rows, global ordering or query discovery.
STATS_SQL = {
    schema: "SELECT clock_timestamp(), calls, rows, {history} FROM " + schema +
    ".pg_stat_statements WHERE dbid=%s AND userid=%s AND queryid=%s AND toplevel=%s LIMIT 2"
    for schema in ('extensions', 'public')
}
INFO_SQL = {schema: 'SELECT clock_timestamp(), stats_reset, dealloc FROM ' + schema +
            '.pg_stat_statements_info LIMIT 2' for schema in ('extensions', 'public')}


def check_config(value):
    budget.shape(value, {'schema_version', 'project_id', 'database_name',
                         'expected_database_oid', 'stats_schema', 'queries'})
    budget.require(type(value['schema_version']) is int and value['schema_version'] == 1, 'INVALID_VERSION')
    budget.require(type(value['project_id']) is str and
                   re.fullmatch('[a-z]{20}', value['project_id']), 'INVALID_PROJECT')
    budget.label(value['database_name'])
    budget.require(0 < budget.integer(value['expected_database_oid'], 2**32-1), 'INVALID_DATABASE_OID')
    budget.require(type(value['stats_schema']) is str and value['stats_schema'] in STATS_SQL, 'INVALID_STATS_SCHEMA')
    entries = value['queries']
    budget.require(type(entries) is list and 1 <= len(entries) <= MAX_QUERIES, 'QUERY_ALLOWLIST_REQUIRED')
    seen = set()
    for entry in entries:
        budget.shape(entry, {'userid', 'queryid', 'toplevel'})
        budget.require(0 < budget.integer(entry['userid'], 2**32-1), 'INVALID_USER_OID')
        budget.require(type(entry['queryid']) is int and -2**63 <= entry['queryid'] < 2**63,
                       'INVALID_QUERY_ID')
        budget.require(type(entry['toplevel']) is bool, 'INVALID_TOPLEVEL')
        key = (entry['userid'], entry['queryid'], entry['toplevel'])
        budget.require(key not in seen, 'DUPLICATE_QUERY_ID')
        seen.add(key)
    budget.require(len(budget.canonical(value)) <= MAX_OUTPUT, 'INPUT_TOO_LARGE')
    return value


def _read_private(path):
    failure = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'rb') as stream:
            meta = os.fstat(stream.fileno())
            budget.require(stat.S_ISREG(meta.st_mode) and meta.st_uid == os.getuid()
                           and meta.st_mode & 0o077 == 0, 'PRIVATE_FILE_REQUIRED')
            budget.require(0 < meta.st_size <= 8192, 'CREDENTIAL_SIZE_INVALID')
            raw = stream.read(8193)
        budget.require(0 < len(raw) <= 8192, 'CREDENTIAL_SIZE_INVALID')
        value = json.loads(raw, object_pairs_hook=budget._pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(budget.EvidenceError('NONFINITE_JSON')))
        budget.shape(value, {'user', 'password', 'sslrootcert'})
        budget.require(type(value['user']) is str and re.fullmatch('[a-z_][a-z0-9_]{0,62}', value['user']), 'INVALID_READER_ROLE')
        budget.require(value['user'] not in ('postgres', 'service_role', 'supabase_admin'), 'PRIVILEGED_READER_REFUSED')
        budget.require(type(value['password']) is str and 1 <= len(value['password']) <= 1024
                       and '\x00' not in value['password'], 'INVALID_CREDENTIAL')
        budget.require(type(value['sslrootcert']) is str and len(value['sslrootcert']) <= 1024, 'INVALID_CERTIFICATE')
        cert = Path(value['sslrootcert'])
        budget.require(cert.is_absolute() and not cert.is_symlink() and cert.is_file()
                       and 0 < cert.stat().st_size <= 131_072, 'INVALID_CERTIFICATE')
        return value
    except budget.EvidenceError as error:
        failure = str(error)
    except (OSError, ValueError, TypeError, RecursionError):
        failure = 'CREDENTIAL_READ_FAILED'
    # No retained decoder context, filename, password, DSN or driver exception.
    raise budget.EvidenceError(failure)


def _timestamp(value):
    budget.require(type(value) is datetime and value.utcoffset() is not None, 'INVALID_SOURCE_TIME')
    return value.astimezone(timezone.utc).isoformat()


def _rows(cursor, sql, params=None):
    cursor.execute(sql, params)
    result = cursor.fetchmany(3)
    budget.require(type(result) is list and len(result) <= 2, 'SOURCE_ROW_CAP_EXCEEDED')
    return result


def _one(cursor, sql, params=None):
    result = _rows(cursor, sql, params)
    budget.require(len(result) == 1, 'SOURCE_ROW_MISSING_OR_DUPLICATED')
    return result[0]


def _snapshot(connection, config, reader_user):
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute(BEGIN)
        row = _one(cursor, IDENTITY_SQL)
        budget.require(len(row) == 13, 'INVALID_IDENTITY_ROW')
        start, database, oid, user, session, readonly, statement, lock, version, *privileges = row
        budget.require(database == config['database_name'] and type(oid) is int
                       and oid == config['expected_database_oid'], 'DATABASE_IDENTITY_MISMATCH')
        budget.require(user == session == reader_user, 'READER_IDENTITY_MISMATCH')
        budget.require(readonly == 'on' and statement == '5s' and lock == '1s', 'SESSION_GUARDS_MISMATCH')
        budget.require(all(type(p) is bool and not p for p in privileges), 'PRIVILEGED_READER_REFUSED')
        budget.integer(version, 1_000_000)
        extension = _one(cursor, EXTENSION_SQL)
        budget.require(len(extension) == 4 and extension[0] == config['stats_schema'], 'EXTENSION_SCOPE_MISMATCH')
        schema, extension_version, history, dealloc_supported = extension
        budget.require(type(extension_version) is str and re.fullmatch(r'\d{1,2}\.\d{1,2}', extension_version), 'INVALID_EXTENSION_VERSION')
        budget.require(type(history) is bool and type(dealloc_supported) is bool, 'INVALID_HISTORY_SUPPORT')
        source = {'project_endpoint': 'db.' + config['project_id'] + '.supabase.co',
                  'database_name_sha256': budget.content_hash(database), 'database_oid': oid,
                  'reader_sha256': budget.content_hash(user), 'server_version_num': version,
                  'stats_schema': schema, 'extension_version': extension_version,
                  'tls_verification': 'verify-full'}
        fingerprint = budget.content_hash(source)
        unknowns = []
        if not history: unknowns.append('STATS_SINCE_UNAVAILABLE')
        if not dealloc_supported: unknowns.append('RESET_AND_DEALLOCATION_UNAVAILABLE')
        info_before = _one(cursor, INFO_SQL[schema]) if dealloc_supported else None
        entries = []
        for selected in config['queries']:
            key = budget.content_hash({'database_sha256': fingerprint, **selected})
            params = (oid, selected['userid'], selected['queryid'], selected['toplevel'])
            rows = _rows(cursor, STATS_SQL[schema].format(history='stats_since' if history else 'NULL::timestamptz'), params)
            budget.require(len(rows) <= 1, 'DUPLICATE_SOURCE_QUERY')
            if not rows:
                unknowns.append('ALLOWLISTED_QUERY_MISSING')
                entries.append({'query_sha256': key, 'observed_at': None, 'calls': None,
                                'rows': None, 'stats_since': None})
                continue
            budget.require(len(rows[0]) == 4, 'INVALID_QUERY_ROW')
            observed, calls, count, since = rows[0]
            entries.append({'query_sha256': key, 'observed_at': _timestamp(observed),
                            'calls': budget.integer(calls), 'rows': budget.integer(count),
                            'stats_since': _timestamp(since) if since is not None else None})
            if since is None: unknowns.append('STATS_SINCE_UNAVAILABLE')
        info_after = _one(cursor, INFO_SQL[schema]) if dealloc_supported else None
        end = _timestamp(_one(cursor, CLOCK_SQL)[0])
        info = []
        for observed_info in (info_before, info_after):
            if observed_info is None:
                info.append(None)
            else:
                budget.require(len(observed_info) == 3, 'INVALID_INFO_ROW')
                observed, reset, dealloc = observed_info
                info.append({'observed_at': _timestamp(observed), 'stats_reset': _timestamp(reset),
                             'dealloc': budget.integer(dealloc)})
        if info[0] is not None and (info[0]['stats_reset'], info[0]['dealloc']) != (info[1]['stats_reset'], info[1]['dealloc']):
            unknowns.append('HISTORY_CHANGED_DURING_CAPTURE')
        return {'source_identity': source, 'database_sha256': fingerprint,
                'snapshot_start': _timestamp(start), 'snapshot_end': end,
                'info_before': info[0], 'info_after': info[1], 'entries': entries,
                'unknowns': sorted(set(unknowns))}


def _report():
    return {'schema_version': 1, 'status': 'BLOCKED', 'production_authorized': False,
            'provider_meter_authenticated': False, 'caller_attribution_verified': False,
            'artifact_authentication': 'UNVERIFIED_WHEN_IMPORTED',
            'generated_by': 'scripts/verification/social_operating_collect.py',
            'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'captured_at': datetime.now(timezone.utc).isoformat(), 'snapshot': None,
            'payload_sha256': None, 'unknowns': []}


def collect(config, *, credential_file, execute=False, connect=None):
    """No connection or credential read without execute=True, also on direct calls.

    Injected drivers are test-only and are visibly distinguished from TLS readback.
    Artifacts carry content binding, not a reusable authentication/signature claim.
    """
    report = _report()
    connection = None
    failure = None
    try:
        check_config(config)
        budget.require(type(execute) is bool, 'INVALID_EXECUTE_FLAG')
        if not execute:
            report['status'] = 'PLAN_ONLY'
            report['unknowns'] = ['COLLECTION_NOT_EXECUTED']
            return report
        budget.require(not any(k.startswith('PG') for k in os.environ), 'LIBPQ_ENVIRONMENT_REFUSED')
        credentials = _read_private(credential_file)
        injected = connect is not None
        if connect is None:
            import psycopg2
            connect = psycopg2.connect
        connection = connect(host='db.' + config['project_id'] + '.supabase.co', port=5432,
            dbname=config['database_name'], user=credentials['user'], password=credentials['password'],
            sslmode='verify-full', sslrootcert=credentials['sslrootcert'], connect_timeout=5,
            application_name='auditgava-egress-readonly',
            options='-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000 -c idle_in_transaction_session_timeout=5000 -c search_path=pg_catalog')
        report['snapshot'] = _snapshot(connection, config, credentials['user'])
        validate_snapshot(report['snapshot'])
        report['captured_at'] = datetime.now(timezone.utc).isoformat()
        budget.require(budget.instant(report['captured_at']) >= budget.instant(report['snapshot']['snapshot_end']), 'SOURCE_CLOCK_AHEAD')
        report['session_observation'] = 'INJECTED_TEST_DRIVER' if injected else 'TLS_DATABASE_SESSION_READBACK'
        report['payload_sha256'] = budget.content_hash(report['snapshot'])
        report['unknowns'] = report['snapshot']['unknowns']
        report['status'] = 'PARTIAL_OBSERVATION' if report['unknowns'] else 'OBSERVED_COUNTERS_ONLY'
        budget.require(len(budget.canonical(report)) <= MAX_OUTPUT, 'OUTPUT_TOO_LARGE')
    except budget.EvidenceError as error:
        failure = str(error)
    except Exception:
        failure = 'COLLECTION_FAILED'
    finally:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                failure = 'CLEANUP_FAILED'
            try:
                connection.close()
            except Exception:
                failure = 'CLEANUP_FAILED'
    if failure:
        report = _report()
        report['unknowns'] = [failure]
    return report


def validate_snapshot(value):
    budget.shape(value, {'source_identity', 'database_sha256', 'snapshot_start', 'snapshot_end',
                         'info_before', 'info_after', 'entries', 'unknowns'})
    source = budget.shape(value['source_identity'], {'project_endpoint', 'database_name_sha256',
        'database_oid', 'reader_sha256', 'server_version_num', 'stats_schema', 'extension_version', 'tls_verification'})
    budget.require(type(source['project_endpoint']) is str and re.fullmatch(r'db\.[a-z]{20}\.supabase\.co', source['project_endpoint']), 'INVALID_PROJECT')
    budget.digest(source['database_name_sha256']); budget.digest(source['reader_sha256'])
    budget.require(0 < budget.integer(source['database_oid'], 2**32-1), 'INVALID_DATABASE_OID')
    budget.integer(source['server_version_num'], 1_000_000)
    budget.require(source['stats_schema'] in ('extensions', 'public') and source['tls_verification'] == 'verify-full', 'INVALID_SOURCE_SCOPE')
    budget.require(type(source['extension_version']) is str and re.fullmatch(r'\d{1,2}\.\d{1,2}', source['extension_version']), 'INVALID_EXTENSION_VERSION')
    budget.require(budget.digest(value['database_sha256']) == budget.content_hash(source), 'SOURCE_IDENTITY_BINDING_MISMATCH')
    start, end = budget.instant(value['snapshot_start']), budget.instant(value['snapshot_end'])
    budget.require(start <= end and (end-start).total_seconds() <= 300, 'INVALID_CAPTURE_WINDOW')
    budget.require(type(value['unknowns']) is list and len(value['unknowns']) <= 10
                   and all(type(x) is str and x in {'STATS_SINCE_UNAVAILABLE', 'RESET_AND_DEALLOCATION_UNAVAILABLE',
                       'ALLOWLISTED_QUERY_MISSING', 'HISTORY_CHANGED_DURING_CAPTURE'} for x in value['unknowns']), 'INVALID_UNKNOWNS')
    required_unknowns = set()
    if value['info_before'] is None or value['info_after'] is None:
        budget.require(value['info_before'] is None and value['info_after'] is None, 'PARTIAL_HISTORY_METADATA')
        required_unknowns.add('RESET_AND_DEALLOCATION_UNAVAILABLE')
    for key in ('info_before', 'info_after'):
        info = value[key]
        if info is not None:
            budget.shape(info, {'observed_at', 'stats_reset', 'dealloc'})
            budget.require(start <= budget.instant(info['observed_at']) <= end and
                           budget.instant(info['stats_reset']) <= start, 'INVALID_HISTORY_TIME')
            budget.integer(info['dealloc'])
    if value['info_before'] is not None:
        first, last = value['info_before'], value['info_after']
        budget.require(budget.instant(first['observed_at']) <= budget.instant(last['observed_at']), 'HISTORY_TIME_REVERSED')
        if (budget.instant(first['stats_reset']), first['dealloc']) != (budget.instant(last['stats_reset']), last['dealloc']):
            required_unknowns.add('HISTORY_CHANGED_DURING_CAPTURE')
    entries = value['entries']
    budget.require(type(entries) is list and 1 <= len(entries) <= MAX_QUERIES, 'INVALID_COUNTER_COUNT')
    seen = set()
    for entry in entries:
        budget.shape(entry, {'query_sha256', 'observed_at', 'calls', 'rows', 'stats_since'})
        key = budget.digest(entry['query_sha256'])
        budget.require(key not in seen, 'DUPLICATE_QUERY_SHAPE'); seen.add(key)
        if entry['observed_at'] is None:
            budget.require(all(entry[k] is None for k in ('calls', 'rows', 'stats_since')), 'PARTIAL_QUERY_ROW')
            required_unknowns.add('ALLOWLISTED_QUERY_MISSING')
        else:
            budget.require(start <= budget.instant(entry['observed_at']) <= end, 'QUERY_TIME_OUTSIDE_CAPTURE')
            budget.integer(entry['calls']); budget.integer(entry['rows'])
            if entry['stats_since'] is not None:
                budget.require(budget.instant(entry['stats_since']) <= start, 'INVALID_HISTORY_TIME')
            else:
                required_unknowns.add('STATS_SINCE_UNAVAILABLE')
    budget.require(required_unknowns <= set(value['unknowns']), 'MISSING_HISTORY_DISCLOSURE')
    return value


def main(argv=None):
    try:
        parser = budget.SafeParser(description=__doc__)
        parser.add_argument('--config', required=True, help='Nonsecret exact database/query allowlist JSON')
        parser.add_argument('--credential-file', help='Explicit private 0600 JSON; never read in plan mode')
        parser.add_argument('--execute-read-only', action='store_true')
        parser.add_argument('--out', help='Exclusive new JSON report')
        args = parser.parse_args(argv)
        report = collect(budget.load_json(args.config), credential_file=args.credential_file,
                         execute=args.execute_read_only)
        if args.out:
            budget.require(Path(args.out).suffix == '.json', 'JSON_FILE_REQUIRED')
            descriptor = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(budget.canonical(report) + b'\n')
            budget.require(budget.load_json(args.out) == report, 'OUTPUT_READBACK_FAILED')
        print(json.dumps(report, sort_keys=True))
        return 0 if report['status'] != 'BLOCKED' else 1
    except (budget.EvidenceError, OSError, ValueError, TypeError):
        error = sys.exc_info()[1]
        report = _report()
        report['unknowns'] = [str(error) if isinstance(error, budget.EvidenceError) else 'CLI_FAILED']
        print(json.dumps(report, sort_keys=True))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
