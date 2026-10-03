#!/usr/bin/env python3
"""Explicit reviewed acquisition; no connection without a current hash-bound request.

The transport abort is sampled, NEVER a hard provider-accounting ceiling. This
tool acquires recovery inputs, not a production recovery certificate. No app
imports, TLS proxy, service bootstrap, seed, or environment-file loading.
"""
from __future__ import annotations

import argparse
import configparser
import contextlib
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import tempfile
import time
import uuid

spec = importlib.util.spec_from_file_location('bounded_pg_backup', Path(__file__).with_name('bounded_pg_backup.py'))
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)
Refusal = backup.Refusal
PREFIX = 'round19_s1_'
PROJECT = 'xznjxwrkbkahwtnbstbj'
SERVICE = 'round19_recovery'
ACK = 'sampled_namespace_abort_is_not_a_hard_provider_ceiling'
ENV = backup.ENV


def provenance():
    return {**backup.provenance(), 'generated_by': str(Path(__file__).resolve()),
            'generator_sha256': backup.sha256(__file__),
            'inventory_generator_sha256': backup.sha256(backup.__file__)}


def owned(name):
    if not isinstance(name, str) or not re.fullmatch(r'round19_s1_[a-z0-9_]+', name):
        raise Refusal('unowned_resource')
    return name


def remove(name):
    owned(name)
    if backup.run(['docker', 'ps', '-aq', '--filter', 'name=^/' + name + '$']).strip():
        backup.run(['docker', 'rm', '-fv', name])


def digest(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise Refusal('digest_required')
    return value


def validate_identity(identity):
    if not isinstance(identity, dict) or set(identity) != {'database_name_sha256','server_address_sha256','role','server_port','version'}:
        raise Refusal('identity_shape')
    digest(identity['database_name_sha256']); digest(identity['server_address_sha256'])
    if (type(identity['server_port']) is not int or not 0 < identity['server_port'] <= 65535
            or not all(isinstance(identity[k], str) and identity[k] for k in ('role','version'))):
        raise Refusal('identity_shape')


def read_request(path, approved_sha256, *, now=None):
    """The explicit hash is an operator checkpoint, not a signature or authority proof."""
    path = backup.private_file(path)
    if backup.sha256(path) != digest(approved_sha256):
        raise Refusal('request_digest_mismatch')
    request = json.loads(path.read_text())
    keys = {'version', 'project', 'expires_at', 'generator_sha256', 'inventory_generator_sha256',
            'service_sha256', 'pgpass_sha256', 'ca_sha256', 'identity', 'wall_seconds',
            'transport_abort_bytes', 'transport_acknowledgement', 'writer_freeze_receipt_sha256'}
    if not isinstance(request, dict) or set(request) != keys or type(request['version']) is not int or request['version'] != 1:
        raise Refusal('request_shape')
    if request['project'] != PROJECT or request['transport_acknowledgement'] != ACK:
        raise Refusal('target_or_transport_choice_not_reviewed')
    for k in ('generator_sha256', 'inventory_generator_sha256', 'service_sha256', 'pgpass_sha256',
              'ca_sha256', 'writer_freeze_receipt_sha256'):
        digest(request[k])
    if request['generator_sha256'] != backup.sha256(__file__) or request['inventory_generator_sha256'] != backup.sha256(backup.__file__):
        raise Refusal('reviewed_code_changed')
    backup.bounds(request['wall_seconds'], request['transport_abort_bytes'])
    try:
        expires = dt.datetime.fromisoformat(request['expires_at'])
        current = now or dt.datetime.now(dt.timezone.utc)
        if expires.utcoffset() != dt.timedelta(0) or not 0 < (expires - current).total_seconds() <= 900:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise Refusal('request_expired_or_invalid') from None
    identity = request['identity']
    validate_identity(identity)
    if identity['role'] != 'postgres' or type(identity['server_port']) is not int or not 0 < identity['server_port'] <= 65535 or identity['version'] != '17.6':
        raise Refusal('identity_shape')
    return request


def stage_credentials(directory, service_file, pgpass_file, ca_file, request):
    """Only direct or SESSION pooler endpoints; verify-full keeps the actual hostname."""
    inputs = [('service_sha256', service_file), ('pgpass_sha256', pgpass_file), ('ca_sha256', ca_file)]
    for key, value in inputs:
        path = backup.private_file(value)
        if backup.sha256(path) != request[key]:
            raise Refusal('credential_input_changed')
    config = configparser.ConfigParser(interpolation=None, strict=True)
    config.read_string(Path(service_file).read_text())
    keys = {'host', 'port', 'user', 'dbname', 'connect_timeout', 'sslmode', 'sslrootcert', 'passfile', 'gssencmode'}
    if config.defaults() or config.sections() != [SERVICE] or set(config[SERVICE]) != keys:
        raise Refusal('service_allowlist')
    s = config[SERVICE]
    direct = s['host'] == f'db.{PROJECT}.supabase.co' and s['user'] == 'postgres'
    session = re.fullmatch(r'aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com', s['host']) and s['user'] == 'postgres.' + PROJECT
    if not (direct or session) or s['port'] != '5432' or s['dbname'] != 'postgres' or s['connect_timeout'] != '8':
        raise Refusal('wrong_endpoint_or_transaction_pooler')
    if s['sslmode'] != 'verify-full' or s['sslrootcert'] != '/backup/root.crt' or s['passfile'] != '/backup/pgpass' or s['gssencmode'] != 'disable':
        raise Refusal('tls_required')
    # Preserve exact reviewed bytes, rehash staged inputs before any connection.
    for source, target, key in [(service_file, 'pg_service.conf', 'service_sha256'),
                                (pgpass_file, 'pgpass', 'pgpass_sha256'), (ca_file, 'root.crt', 'ca_sha256')]:
        p = directory / target
        with p.open('xb') as out:
            out.write(Path(source).read_bytes())
        p.chmod(0o600)
        if backup.sha256(p) != request[key]:
            raise Refusal('staged_credential_changed')


# PID1 supervises ALL acquisition connections. Unlike a dump-only watchdog, it
# also closes the exporter, inventory and role connections on a breach. Taking
# eth0 down needs NET_ADMIN in this exclusively owned namespace; no host change.
# Counters include DNS/TLS/retransmission visible here. Sampling can overshoot.
SUPERVISOR = r'''
set -eu
umask 077
rx=/sys/class/net/eth0/statistics/rx_bytes
tx=/sys/class/net/eth0/statistics/tx_bytes
[ -r "$rx" ] && [ -r "$tx" ] || exit 24
start=$(date +%s)
while [ ! -f /backup/stop ]; do
  total=$(( $(cat "$rx") + $(cat "$tx") ))
  printf '%s\n' "$total" > /backup/counter
  if [ "$total" -gt "$1" ]; then
    printf 'transport_exceeded\n' > /backup/abort
    ip link set eth0 down || exit 24
    exit 23
  fi
  if [ "$(( $(date +%s) - start ))" -ge "$2" ]; then
    printf 'wall_expired\n' > /backup/abort
    ip link set eth0 down || exit 24
    exit 25
  fi
  sleep 0.02
done
'''

IDENTITY_SQL = """SELECT json_build_object(
 'database_name_sha256',encode(sha256(convert_to(current_database(),'UTF8')),'hex'),
 'server_address_sha256',encode(sha256(convert_to(host(inet_server_addr()),'UTF8')),'hex'),
 'role',current_user,'server_port',inet_server_port(),'version',current_setting('server_version'),
 'readonly',current_setting('transaction_read_only'),'isolation',current_setting('transaction_isolation'),
 'snapshot',pg_export_snapshot());
"""


RECOVERY_PREREQUISITES_SQL = r'''
-- Read-only supplement for the existing acquisition inventory transaction.
-- Append BEFORE its ROLLBACK and write the extra object separately from the
-- strict existing inventory array. Integration changes helper bytes and thus
-- must occur before root hashes/reviews the operation request.
-- This file alone opens no connection and performs no production writes.
SELECT json_build_object(
 'kind','recovery_prerequisites',
 'readonly',current_setting('transaction_read_only'),
 'isolation',current_setting('transaction_isolation'),
 'activity_counts',(
   SELECT json_build_object(
     'clients',count(*) FILTER (WHERE backend_type='client backend'),
     'active_clients',count(*) FILTER (WHERE backend_type='client backend' AND state='active'),
     'client_transactions',count(*) FILTER (WHERE backend_type='client backend' AND xact_start IS NOT NULL),
     'assigned_client_xids',count(*) FILTER (WHERE backend_type='client backend' AND backend_xid IS NOT NULL),
     'background_workers',count(*) FILTER (WHERE backend_type<>'client backend'),
     'assigned_background_xids',count(*) FILTER (WHERE backend_type<>'client backend' AND backend_xid IS NOT NULL))
   FROM pg_stat_activity WHERE pid<>pg_backend_pid()),
 'database_properties',(
   SELECT json_build_object('name',d.datname,'owner',pg_get_userbyid(d.datdba),
     'encoding',pg_encoding_to_char(d.encoding),'locale_provider',d.datlocprovider,
     'collate',d.datcollate,'ctype',d.datctype,'locale',d.datlocale,
     'icu_rules',d.daticurules,'collation_version',d.datcollversion,
     'connection_limit',d.datconnlimit,'allow_connections',d.datallowconn,
     'tablespace',t.spcname,'acl',d.datacl)
   FROM pg_database d JOIN pg_tablespace t ON t.oid=d.dattablespace
   WHERE d.datname=current_database()),
 'database_role_settings',(
   SELECT json_agg(json_build_array(d.datname,CASE WHEN s.setrole=0 THEN NULL ELSE pg_get_userbyid(s.setrole) END,s.setconfig)
     ORDER BY d.datname,CASE WHEN s.setrole=0 THEN NULL ELSE pg_get_userbyid(s.setrole) END)
   FROM pg_db_role_setting s LEFT JOIN pg_database d ON d.oid=s.setdatabase),
 'system_schema_acls',(
   SELECT json_agg(json_build_array(nspname,pg_get_userbyid(nspowner),nspacl) ORDER BY nspname)
   FROM pg_namespace WHERE nspname IN ('pg_catalog','information_schema')),
 'system_relation_acls',(
   SELECT json_agg(json_build_array(n.nspname,c.relname,c.relkind,pg_get_userbyid(c.relowner),c.relacl)
     ORDER BY n.nspname,c.relname)
   FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname IN ('pg_catalog','information_schema') AND c.relacl IS NOT NULL),
 'system_column_acls',(
   SELECT json_agg(json_build_array(n.nspname,c.relname,a.attname,a.attacl)
     ORDER BY n.nspname,c.relname,a.attnum)
   FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname IN ('pg_catalog','information_schema') AND a.attacl IS NOT NULL AND NOT a.attisdropped),
 'system_routine_acls',(
   SELECT json_agg(json_build_array(n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),pg_get_userbyid(p.proowner),p.proacl)
     ORDER BY n.nspname,p.proname,pg_get_function_identity_arguments(p.oid))
   FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
   WHERE n.nspname IN ('pg_catalog','information_schema') AND p.proacl IS NOT NULL),
 'parameter_acls',(
   SELECT json_agg(json_build_array(parname,paracl) ORDER BY parname) FROM pg_parameter_acl));
'''

def validate_recovery_prerequisites(value):
    """Typed source configuration supplement; never certify an absent capture."""
    keys = {'kind', 'readonly', 'isolation', 'activity_counts', 'database_properties',
            'database_role_settings', 'system_schema_acls', 'system_relation_acls',
            'system_column_acls', 'system_routine_acls', 'parameter_acls'}
    if not isinstance(value, dict) or set(value) != keys:
        raise Refusal('recovery_prerequisites_shape')
    if value['kind'] != 'recovery_prerequisites' or value['readonly'] != 'on' or value['isolation'] != 'repeatable read':
        raise Refusal('recovery_prerequisites_transaction')
    try:
        if len(json.dumps(value, allow_nan=False).encode()) > 2 * 1024 * 1024:
            raise Refusal('recovery_prerequisites_oversized')
    except (ValueError, TypeError):
        raise Refusal('recovery_prerequisites_invalid_json') from None
    counts = value['activity_counts']
    if (not isinstance(counts, dict) or set(counts) != {'clients', 'active_clients', 'client_transactions',
            'assigned_client_xids', 'background_workers', 'assigned_background_xids'}
            or any(type(x) is not int or x < 0 for x in counts.values())
            or any(counts[k] > counts['clients'] for k in ('active_clients', 'client_transactions', 'assigned_client_xids'))
            or counts['assigned_background_xids'] > counts['background_workers']):
        raise Refusal('recovery_activity_counts_shape')
    def string(x): return isinstance(x, str) and bool(x) and '\x00' not in x
    def acl(x): return x is None or isinstance(x, list) and all(string(a) for a in x)
    d = value['database_properties']
    database_keys = {'name', 'owner', 'encoding', 'locale_provider', 'collate', 'ctype', 'locale', 'icu_rules',
                     'collation_version', 'connection_limit', 'allow_connections', 'tablespace', 'acl'}
    if (not isinstance(d, dict) or set(d) != database_keys
            or any(not string(d[k]) for k in ('name', 'owner', 'encoding', 'collate', 'ctype', 'tablespace'))
            or d['locale_provider'] not in ('b', 'c', 'i')
            or any(d[k] is not None and (not isinstance(d[k], str) or '\x00' in d[k]) for k in ('locale', 'icu_rules', 'collation_version'))
            or d['locale_provider'] in ('b', 'i') and not string(d['locale'])
            or type(d['connection_limit']) is not int or d['connection_limit'] < -1
            or type(d['allow_connections']) is not bool or not acl(d['acl'])):
        raise Refusal('recovery_database_properties_shape')
    lengths = {'database_role_settings': 3, 'system_schema_acls': 3, 'system_relation_acls': 5,
               'system_column_acls': 4, 'system_routine_acls': 5, 'parameter_acls': 2}
    for key, length in lengths.items():
        rows = value[key]
        if rows is None and key != 'system_schema_acls':
            continue  # SQL json_agg null means no matching optional configuration objects.
        if not isinstance(rows, list) or len(rows) > 5000:
            raise Refusal('recovery_configuration_rows_shape')
        identities = set()
        for row in rows:
            if not isinstance(row, list) or len(row) != length:
                raise Refusal('recovery_configuration_row_shape')
            if key == 'database_role_settings':
                valid = (all(x is None or string(x) for x in row[:2]) and any(x is not None for x in row[:2])
                         and isinstance(row[2], list) and bool(row[2])
                         and all(string(x) and '=' in x and string(x.split('=', 1)[0]) for x in row[2])
                         and len({x.split('=', 1)[0] for x in row[2]}) == len(row[2]))
                identity = tuple(row[:2])
            else:
                valid = acl(row[-1]) and all(string(x) for x in row[:-1])
                if key in ('system_relation_acls', 'system_column_acls', 'system_routine_acls'):
                    valid = valid and row[-1] is not None
                if key != 'parameter_acls': valid = valid and row[0] in ('pg_catalog', 'information_schema')
                if key == 'system_relation_acls': valid = valid and row[2] in ('r', 'p', 'v', 'm', 'S', 'f')
                if key == 'system_routine_acls':
                    valid = (row[-1] is not None and acl(row[-1]) and string(row[0]) and string(row[1]) and isinstance(row[2], str)
                             and '\x00' not in row[2] and string(row[3]) and row[0] in ('pg_catalog', 'information_schema'))
                identity = tuple(row[:1] if key in ('system_schema_acls', 'parameter_acls') else row[:3] if key in ('system_column_acls', 'system_routine_acls') else row[:2])
            if not valid or identity in identities:
                raise Refusal('recovery_configuration_invalid_or_duplicate')
            identities.add(identity)
    if {row[0] for row in value['system_schema_acls']} != {'pg_catalog', 'information_schema'}:
        raise Refusal('recovery_system_schemas_missing')


def compare_recovery_prerequisites(before, after):
    """Compare durable configuration separately from point-in-time activity."""
    validate_recovery_prerequisites(before); validate_recovery_prerequisites(after)
    def normalized(value):
        result = {k: v for k, v in value.items() if k not in ('kind', 'readonly', 'isolation', 'activity_counts')}
        result = json.loads(json.dumps(result))
        if result['database_properties']['acl'] is not None:
            result['database_properties']['acl'].sort()
        for key in ('database_role_settings', 'system_schema_acls', 'system_relation_acls',
                    'system_column_acls', 'system_routine_acls', 'parameter_acls'):
            if result[key] is not None:
                for row in result[key]:
                    if row[-1] is not None: row[-1].sort()
                result[key].sort(key=lambda row: json.dumps(row, sort_keys=True))
        return result
    if normalized(before) != normalized(after):
        raise Refusal('recovery_configuration_restore_mismatch')


def psql(client):
    return ['docker', 'exec', '-i', client, 'psql', '-XqAt', '-v', 'ON_ERROR_STOP=1', '--dbname=service=' + SERVICE]


def bounded_line(stream, deadline):
    """Pipe readiness means bytes, not a whole line; never call blocking readline."""
    data = bytearray()
    with selectors.DefaultSelector() as selector:
        selector.register(stream, selectors.EVENT_READ)
        while b'\n' not in data:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise Refusal('snapshot_exporter_timeout')
            chunk = os.read(stream.fileno(), 4096)
            if not chunk or len(data) + len(chunk) > 16384:
                raise Refusal('snapshot_exporter_empty_or_oversized')
            data.extend(chunk)
    return bytes(data).split(b'\n', 1)[0]


@contextlib.contextmanager
def exporter(client, directory, deadline):
    """Verify actual transaction settings before publishing snapshot; rollback last."""
    with (directory / 'exporter.stderr').open('wb') as error:
        proc = subprocess.Popen(psql(client), env=ENV, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=error)
        try:
            proc.stdin.write(('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n' + IDENTITY_SQL).encode())
            proc.stdin.flush()
            identity = json.loads(bounded_line(proc.stdout, deadline))
            if not isinstance(identity, dict) or set(identity) != {'database_name_sha256','server_address_sha256','role','server_port','version','readonly','isolation','snapshot'}:
                raise Refusal('snapshot_identity_shape')
            validate_identity({k: identity[k] for k in ('database_name_sha256','server_address_sha256','role','server_port','version')})
            if identity['readonly'] != 'on' or identity['isolation'] != 'repeatable read' or not isinstance(identity['snapshot'], str) or not re.fullmatch(r'[0-9A-Fa-f]+-[0-9A-Fa-f]+-[0-9]+', identity['snapshot']):
                raise Refusal('snapshot_transaction_unverified')
            yield identity
            proc.stdin.write(b'ROLLBACK;\n'); proc.stdin.close()
            proc.wait(timeout=max(0.1, deadline - time.monotonic()))
            if proc.returncode or (directory / 'exporter.stderr').stat().st_size:
                raise Refusal('exporter_rollback_or_warning')
        finally:
            if proc.poll() is None:
                proc.kill(); proc.wait(timeout=5)
            proc.stdout.close()
            if not proc.stdin.closed:
                proc.stdin.close()


def capture(client, directory, expected_identity, wall_seconds, transport_bytes):
    """Common engine, also exercised against an exclusively internal TLS fixture."""
    backup.bounds(wall_seconds, transport_bytes)
    owned(client)
    validate_identity(expected_identity)
    deadline = time.monotonic() + wall_seconds
    with exporter(client, directory, deadline) as identity:
        actual = {k: identity[k] for k in expected_identity}
        if actual != expected_identity:
            raise Refusal('connected_identity_mismatch')
        snapshot = identity['snapshot']
        sql = 'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n' + "SET TRANSACTION SNAPSHOT '" + snapshot + "';\n"
        sql += "SET LOCAL timezone='UTC'; SET LOCAL datestyle='ISO, YMD'; SET LOCAL extra_float_digits=3;\n"
        sql += backup.INVENTORY_SQL + '\n' + RECOVERY_PREREQUISITES_SQL + '\nROLLBACK;\n'
        raw = backup.run(psql(client), input=sql.encode(), timeout=max(.1, deadline - time.monotonic()))
        records = [json.loads(line) for line in raw.decode().splitlines()]
        if not records:
            raise Refusal('recovery_prerequisites_missing')
        prerequisites = records.pop()
        validate_recovery_prerequisites(prerequisites)
        backup.write_new(directory / 'recovery_prerequisites.json', prerequisites)
        backup.validate_inventory(records)
        backup.write_new(directory / 'inventory.json', records)
        # Globals are not MVCC: the separately reviewed writer freeze is necessary.
        roles = backup.run(['docker', 'exec', client, 'pg_dumpall', '--dbname=service=' + SERVICE,
                            '--roles-only', '--no-role-passwords'], timeout=max(.1, deadline - time.monotonic()))
        if not roles.strip():
            raise Refusal('roles_dump_empty')
        (directory / 'roles.sql').write_bytes(roles); (directory / 'roles.sql').chmod(0o600)
        dump = backup.run(['docker', 'exec', client, 'pg_dump', '--dbname=service=' + SERVICE,
                           '--format=custom', '--snapshot=' + snapshot, '--lock-wait-timeout=5s',
                           '--file=/backup/database.dump'], timeout=max(.1, deadline - time.monotonic()))
        if dump:
            raise Refusal('unexpected_dump_stdout')
    if time.monotonic() >= deadline or (directory / 'abort').exists():
        raise Refusal('acquisition_budget_aborted')
    counters = backup.run(['docker', 'exec', client, 'sh', '-c',
        'cat /sys/class/net/eth0/statistics/rx_bytes /sys/class/net/eth0/statistics/tx_bytes']).decode().split()
    if len(counters) != 2 or not all(v.isdigit() for v in counters):
        raise Refusal('transport_counter_unreadable')
    total = sum(map(int, counters))
    if total > transport_bytes or (directory / 'abort').exists() or time.monotonic() >= deadline:
        raise Refusal('transport_exceeded')
    return {'identity': actual, 'transport_bytes': total, 'snapshot_shared': True,
            'scope': 'custom_dump_roles_without_passwords_inventory_and_recovery_prerequisites',
            'recovery_prerequisites_sha256': backup.sha256(directory / 'recovery_prerequisites.json'),
            'backup_verified': False, 'hard_provider_ceiling': False,
            'inventory_limitations': ['table aggregation requires reviewed server memory budget',
                'custom base-type I/O functions, security labels and foreign servers/subscriptions require separate disposition',
                'nondefault system ACLs/database properties/role settings captured separately; provider credentials, Vault root key and storage object bytes are separate inputs'],
            'elapsed_seconds': round(wall_seconds - (deadline - time.monotonic()), 6)}


def acquire_reviewed(request_file, approved_sha256, service_file, pgpass_file, ca_file, output):
    request = read_request(request_file, approved_sha256)
    output = Path(output).absolute()
    if output.exists() or output.is_symlink() or not output.parent.is_dir() or output.parent.stat().st_mode & 0o077:
        raise Refusal('new_private_output_directory_required')
    client = PREFIX + 'acquire_' + uuid.uuid4().hex[:12]
    result = {**provenance(), 'status': 'failed', 'production': True, 'backup_verified': False,
              'hard_provider_ceiling': False, 'request_sha256': approved_sha256,
              'transport_abort_bytes': request['transport_abort_bytes'], 'wall_seconds': request['wall_seconds']}
    with tempfile.TemporaryDirectory(prefix=PREFIX, dir=output.parent) as temp:
        directory = Path(temp); directory.chmod(0o700)
        stage_credentials(directory, service_file, pgpass_file, ca_file, request)
        began = time.monotonic()
        try:
            # Fresh namespace; no published ports, host mounts, inherited secrets,
            # provider entrypoint or app. Only its own eth0 can be shut down.
            backup.run(['docker', 'run', '--pull', 'never', '-d', '--name', client,
                '--cap-drop=ALL', '--cap-add=NET_ADMIN', '--cap-add=DAC_OVERRIDE', '--security-opt=no-new-privileges',
                '--mount', f'type=bind,src={directory},dst=/backup',
                '-e', 'PGSERVICEFILE=/backup/pg_service.conf', '-e', 'PGPASSFILE=/backup/pgpass',
                '-e', 'PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=300000',
                '--entrypoint', 'sh', backup.SUPABASE_IMAGE, '-c', SUPERVISOR, 'supervisor',
                str(request['transport_abort_bytes']), str(math_ceil(request['wall_seconds']))])
            result.update(capture(client, directory, request['identity'], request['wall_seconds'], request['transport_abort_bytes']))
        except (Refusal, OSError, ValueError, TypeError, subprocess.TimeoutExpired):
            result['reason'] = 'acquisition_refused_private_diagnostics_required'
        finally:
            # Failure of daemon removal is an error, never an acquired receipt.
            remove(client)
        if (directory / 'abort').exists() or time.monotonic() - began >= request['wall_seconds']:
            result.pop('snapshot_shared', None)
            result['reason'] = 'acquisition_budget_aborted'
        # Only after all connections ended and removal succeeded. No credential
        # files/stderr/exporter snapshot are moved into the recovery bundle.
        if 'snapshot_shared' in result:
            with tempfile.TemporaryDirectory(prefix=PREFIX + 'publish_', dir=output.parent) as staged:
                staged = Path(staged); staged.chmod(0o700)
                for n in ['database.dump', 'inventory.json', 'roles.sql', 'recovery_prerequisites.json']:
                    p = directory / n; backup.private_file(p)
                    shutil.copyfile(p, staged / n); (staged / n).chmod(0o600)
                backup.inspect_archive(staged / 'database.dump')
                result['artifacts'] = {n: {'sha256': backup.sha256(staged / n), 'bytes': (staged / n).stat().st_size}
                                       for n in ['database.dump', 'inventory.json', 'roles.sql', 'recovery_prerequisites.json']}
                result['status'] = 'acquired_inputs_restore_and_completeness_pending'
                backup.write_new(staged / 'receipt.json', result)
                readback = json.loads((staged / 'receipt.json').read_text())
                if readback['generator_sha256'] != backup.sha256(__file__):
                    raise Refusal('receipt_provenance_readback')
                # mkdir is exclusive; contents published only after successful
                # capture/removal/inspection. A failed copy cleans only ours.
                output.mkdir(mode=0o700)
                try:
                    for p in staged.iterdir():
                        os.link(p, output / p.name)
                except OSError:
                    shutil.rmtree(output)
                    raise
    return result


def math_ceil(number):
    import math
    return math.ceil(number)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--execute-reviewed-request-sha256', required=True)
    parser.add_argument('--service-file', type=Path, required=True)
    parser.add_argument('--pgpass-file', type=Path, required=True)
    parser.add_argument('--ca-file', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = acquire_reviewed(args.request, args.execute_reviewed_request_sha256,
                                  args.service_file, args.pgpass_file, args.ca_file, args.output)
        print(json.dumps(result, allow_nan=False))
        return 1 if result['status'] == 'failed' else 0
    except (Refusal, OSError, ValueError, TypeError, configparser.Error):
        print(json.dumps({'status': 'refused', 'backup_verified': False, 'hard_provider_ceiling': False}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
