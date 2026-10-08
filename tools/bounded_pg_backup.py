#!/usr/bin/env python3
"""Local-only PostgreSQL acquisition/restore rehearsal. Never a production gate.

No application imports, inherited libpq environment or automatic remote connection.
Transport abort is sampled RX+TX, not a hard provider-egress ceiling.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import uuid

IMAGE = 'postgres@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675'
SUPABASE_IMAGE = 'public.ecr.aws/supabase/postgres@sha256:21ab971149317ea9cd12a8126fe4ebb34def08c8972956b0958cba0924409dab'
PREFIX = 'round19_s1_'
MAX_WALL = 300
MAX_BYTES = 256 * 1024 * 1024
ENV = {'PATH': '/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1'}


class Refusal(RuntimeError):
    """Public error codes contain no child stderr, credentials or private data."""


def bounds(wall_seconds, transport_bytes):
    if type(wall_seconds) not in (int, float) or not math.isfinite(wall_seconds) or not 0 < wall_seconds <= MAX_WALL:
        raise Refusal('invalid_wall_bound')
    if type(transport_bytes) is not int or not 0 < transport_bytes <= MAX_BYTES:
        raise Refusal('invalid_transport_bound')


def run(argv, *, timeout=10, input=None):
    try:
        result = subprocess.run(argv, env=ENV, input=input, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        raise Refusal('child_unavailable_or_timed_out') from None
    if result.returncode:
        raise Refusal('child_failed')
    # Warnings cannot be silently certified as successful acquisition/restore.
    if result.stderr:
        raise Refusal('child_stderr_requires_private_review')
    return result.stdout


def owned(name):
    if not isinstance(name, str) or not re.fullmatch(r'round(?:18|19)_s1_[a-z0-9_]+', name):
        raise Refusal('unowned_resource')
    return name


def remove_container(name):
    owned(name)
    existing = run(['docker', 'ps', '-aq', '--filter', 'name=^/' + name + '$']).strip()
    if existing:
        run(['docker', 'rm', '-fv', name])


def isolated_container(name):
    owned(name)
    settings = json.loads(run(['docker', 'inspect', name, '--format', '{{json .NetworkSettings.Networks}}']))
    if not isinstance(settings, dict) or not settings:
        raise Refusal('container_isolation_unverified')
    for network in settings:
        if network == 'none':
            continue
        owned(network)
        if json.loads(run(['docker', 'network', 'inspect', network, '--format', '{{json .Internal}}'])) is not True:
            raise Refusal('container_isolation_unverified')


def private_file(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise Refusal('private_regular_0600_file_required')
    return path.resolve()


def private_acquisition_file(path):
    """Require the child output to remain private and owned by this caller."""
    path = private_file(path)
    metadata, parent = path.stat(), path.parent.stat()
    if (metadata.st_uid != os.geteuid() or metadata.st_gid != os.getegid()
            or metadata.st_mode & 0o777 != 0o600
            or parent.st_uid != os.geteuid() or parent.st_mode & 0o777 != 0o700):
        raise Refusal('caller_owned_private_acquisition_required')
    return path


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_new(path, value):
    """Persist complete validated JSON first, then publish exclusively."""
    serialized = json.dumps(value, sort_keys=True, indent=2, allow_nan=False)
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix=PREFIX, dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf8') as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        if json.dumps(json.loads(Path(temporary).read_text()), sort_keys=True, indent=2, allow_nan=False) != serialized:
            raise Refusal('receipt_readback_failed')
        os.link(temporary, path)
    finally:
        Path(temporary).unlink()


def provenance():
    return {'generated_by': str(Path(__file__).resolve()), 'generator_sha256': sha256(__file__),
            'generated_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}


# Execute only in a fresh owned client namespace. Internal watchdog kills the
# entire dump group; the outer host watchdog removes the container on timeout.
# The kernel RX/TX counters include other namespace traffic (e.g. DNS), TLS and
# retransmissions visible at this interface. Samples are NOT a hard quota.
BOUNDED_SH = r'''
set -eu
umask 077
limit=$1
shift
rx=/sys/class/net/eth0/statistics/rx_bytes
tx=/sys/class/net/eth0/statistics/tx_bytes
[ -r "$rx" ] && [ -r "$tx" ] || exit 24
"$@" > /backup/acquisition.partial 2>/backup/child.stderr &
pid=$!
(
  while kill -0 "$pid" 2>/dev/null; do
    total=$(( $(cat "$rx") + $(cat "$tx") ))
    if [ "$total" -gt "$limit" ]; then
      : > /backup/budget_exceeded
      kill -KILL "$pid"
      exit 0
    fi
    sleep 0.02
  done
) &
monitor=$!
status=0
wait "$pid" || status=$?
wait "$monitor" || exit 24
[ ! -f /backup/budget_exceeded ] || exit 23
[ "$status" -eq 0 ] || exit 25
[ ! -s /backup/child.stderr ] || exit 26
'''


def network_bytes(container):
    raw = run(['docker', 'exec', owned(container), 'sh', '-c',
               'cat /sys/class/net/eth0/statistics/rx_bytes /sys/class/net/eth0/statistics/tx_bytes'])
    values = raw.decode('ascii').split()
    if len(values) != 2 or not all(v.isdigit() for v in values):
        raise Refusal('transport_counter_unreadable')
    return sum(map(int, values))


def acquire_local(source, network, snapshot, destination, *, wall_seconds=MAX_WALL,
                  transport_bytes=MAX_BYTES, command=None):
    """Rehearse on an owned internal Docker source only. No production mode.

    command is an explicit local test seam, executed inside the bounded container.
    It cannot target an external endpoint because the network must be internal.
    """
    bounds(wall_seconds, transport_bytes)
    owned(source)
    owned(network)
    if not isinstance(snapshot, str) or not re.fullmatch(r'[0-9A-Fa-f]+-[0-9A-Fa-f]+-[0-9]+', snapshot):
        raise Refusal('invalid_snapshot')
    net = json.loads(run(['docker', 'network', 'inspect', network, '--format', '{{json .Internal}}']))
    if net is not True:
        raise Refusal('source_network_not_internal')
    source_nets = json.loads(run(['docker', 'inspect', source, '--format', '{{json .NetworkSettings.Networks}}']))
    if set(source_nets) != {network}:
        raise Refusal('source_not_exclusively_on_owned_internal_network')
    destination = Path(destination).absolute()
    if destination.exists() or not destination.parent.is_dir():
        raise Refusal('new_destination_required')
    # Artifacts remain private. A failure never creates the requested archive.
    client = PREFIX + 'client_' + uuid.uuid4().hex[:12]
    result = {**provenance(), 'status': 'failed', 'backup_verified': False,
              'production': False, 'hard_transport_ceiling': False,
              'wall_seconds': wall_seconds, 'transport_abort_bytes': transport_bytes,
              'transport_counter_scope': 'fresh client namespace eth0 RX+TX',
              'transport_sample_seconds': 0.02}
    with tempfile.TemporaryDirectory(prefix=PREFIX, dir=destination.parent) as directory:
        private = Path(directory)
        os.chmod(private, 0o700)
        # Safe synthetic service only, inherited libpq configuration is discarded.
        service = private / 'pg_service.conf'
        service.write_text(f'[rehearsal]\nhost={source}\nport=5432\nuser=postgres\ndbname=postgres\nconnect_timeout=8\n')
        service.chmod(0o600)
        created = True
        began = time.monotonic()
        try:
            run(['docker', 'run', '-d', '--name', client, '--network', network,
                 '--user', f'{os.geteuid()}:{os.getegid()}',
                 '--mount', f'type=bind,src={private},dst=/backup',
                 '-e', 'PGSERVICEFILE=/backup/pg_service.conf',
                 '-e', 'PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=300000',
                 '--entrypoint', 'sleep', IMAGE, 'infinity'])
            created = True
            argv = command if command is not None else ['pg_dump', '--dbname=service=rehearsal',
                         '--format=custom', '--snapshot=' + snapshot, '--lock-wait-timeout=5s']
            try:
                child = subprocess.run(['docker', 'exec', client, 'timeout', '--signal=KILL',
                        str(wall_seconds), 'sh', '-c', BOUNDED_SH, 'bounded', str(transport_bytes), *argv],
                        env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        timeout=wall_seconds + 2)
                result['child_exit'] = child.returncode
                result['transport_bytes'] = network_bytes(client)
                if child.returncode or child.stderr or result['transport_bytes'] > transport_bytes:
                    result['reason'] = ('wall_expired' if child.returncode in (137, 124) else
                                        'transport_exceeded' if result['transport_bytes'] > transport_bytes else
                                        'child_failed_or_warning')
                else:
                    partial = private_acquisition_file(private / 'acquisition.partial')
                    inspect_archive(partial)
                    # Exclusive publication; never replace an existing backup path.
                    os.link(partial, destination)
                    destination.chmod(0o600)
                    result.update(status='acquired_unverified', archive_sha256=sha256(destination),
                                  archive_bytes=destination.stat().st_size)
            except subprocess.TimeoutExpired:
                result['reason'] = 'outer_wall_expired'
            except Refusal:
                result['reason'] = 'archive_or_counter_refused'
        finally:
            if created:
                # Removal kills all remaining local client processes, not just docker exec.
                remove_container(client)
            result['elapsed_seconds'] = round(time.monotonic() - began, 6)
    result['transport_overshoot_bytes'] = max(0, result.get('transport_bytes', 0) - transport_bytes)
    return result


def inspect_archive(archive, expected_sha256=None):
    archive = private_file(archive)
    if expected_sha256 is not None and sha256(archive) != expected_sha256:
        raise Refusal('archive_digest_mismatch')
    with archive.open('rb') as handle:
        magic = handle.read(5)
    if archive.stat().st_size < 5 or magic != b'PGDMP':
        raise Refusal('custom_archive_required')
    inspector = PREFIX + 'inspect_' + uuid.uuid4().hex[:12]
    try:
        output = run(['docker', 'run', '--rm', '--network', 'none', '--name', inspector,
                      '--mount', f'type=bind,src={archive},dst=/backup/archive,readonly',
                      IMAGE, 'pg_restore', '--list', '/backup/archive'], timeout=30)
    finally:
        # Killing the host docker client does not imply its daemon-owned child
        # stopped. Remove the named inspector even when run/list times out.
        remove_container(inspector)
    entries = [line for line in output.decode('utf8').splitlines() if line and not line.startswith(';')]
    if not entries:
        raise Refusal('empty_archive')
    return {**provenance(), 'status': 'archive_readable_not_recovery_proof',
            'backup_verified': False, 'archive_sha256': sha256(archive), 'toc_entries': len(entries)}


def restore_local(archive, expected_sha256, roles_file, roles_sha256):
    """Restore trusted reviewed bytes into a fresh network-none target, never an app.

    Caller must inspect the result's contents/inventory separately before claiming
    recovery. Roles SQL is trusted executable input, explicitly hash bound.
    """
    if not isinstance(expected_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', expected_sha256):
        raise Refusal('archive_digest_required')
    inspect_archive(archive, expected_sha256)
    roles = private_file(roles_file)
    if not isinstance(roles_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', roles_sha256) or sha256(roles) != roles_sha256:
        raise Refusal('roles_digest_mismatch')
    target = PREFIX + 'restore_' + uuid.uuid4().hex[:12]
    archive = Path(archive).resolve()
    created = True
    try:
        run(['docker', 'run', '-d', '--name', target, '--network', 'none',
             '--mount', f'type=bind,src={archive},dst=/backup/archive,readonly',
             '--mount', f'type=bind,src={roles},dst=/backup/roles.sql,readonly',
             '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', IMAGE])
        created = True
        deadline = time.monotonic() + 30
        while True:
            ready = subprocess.run(['docker', 'exec', target, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres'],
                                  env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
            if ready.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise Refusal('restore_target_not_ready')
            time.sleep(0.1)
        run(['docker', 'exec', target, 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres',
             '-d', 'postgres', '-f', '/backup/roles.sql'])
        began = time.monotonic()
        run(['docker', 'exec', target, 'pg_restore', '--exit-on-error', '--single-transaction',
             '-U', 'postgres', '-d', 'postgres', '/backup/archive'], timeout=600)
        resolved = run(['docker', 'exec', target, 'psql', '-XAt', '-U', 'postgres', '-d', 'postgres',
            '-c', "SELECT json_build_object('database',current_database(),'version',current_setting('server_version'),'address',inet_server_addr(),'port',inet_server_port())"])
        yield_result = {'target': target, 'status': 'restored_unverified', 'backup_verified': False,
                        'production': False, 'restore_seconds': round(time.monotonic() - began, 6),
                        'resolved': json.loads(resolved), 'network': 'none', 'archive_sha256': expected_sha256}
        # A context manager keeps the container only during explicit verification.
        yield yield_result
    finally:
        if created:
            remove_container(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    inspect = commands.add_parser('inspect')
    inspect.add_argument('--archive', type=Path, required=True)
    inspect.add_argument('--expected-sha256', required=True)
    acquire = commands.add_parser('acquire-local')
    for flag in ('source','network','snapshot'):
        acquire.add_argument('--'+flag, required=True)
    acquire.add_argument('--output', type=Path, required=True)
    acquire.add_argument('--wall-seconds', type=float, default=MAX_WALL)
    acquire.add_argument('--transport-bytes', type=int, default=MAX_BYTES)
    restore = commands.add_parser('restore-local')
    restore.add_argument('--archive', type=Path, required=True)
    restore.add_argument('--expected-sha256', required=True)
    restore.add_argument('--roles-file', type=Path, required=True)
    restore.add_argument('--roles-sha256', required=True)
    restore.add_argument('--inventory', type=Path, required=True)
    restore.add_argument('--inventory-sha256', required=True)
    args = parser.parse_args()
    try:
        if args.operation=='inspect':
            result=inspect_archive(args.archive,args.expected_sha256)
        elif args.operation=='acquire-local':
            result=acquire_local(args.source,args.network,args.snapshot,args.output,
                wall_seconds=args.wall_seconds,transport_bytes=args.transport_bytes)
        else:
            inventory_file=private_file(args.inventory)
            if sha256(inventory_file)!=args.inventory_sha256:
                raise Refusal('inventory_digest_mismatch')
            before=json.loads(inventory_file.read_text())
            validate_inventory(before)
            with contextlib.contextmanager(restore_local)(args.archive,args.expected_sha256,args.roles_file,args.roles_sha256) as result:
                compare_inventory(before,inventory_local(result['target']))
                result['inventory_equal']=True
                result['status']='local_inventory_equal_production_unverified'
        print(json.dumps(result,allow_nan=False))
        return 1 if result.get('status')=='failed' else 0
    except (Refusal,OSError,ValueError,TypeError):
        print(json.dumps({'status':'refused','backup_verified':False}))
        return 1


# Rehearsal inventory is one explicit read-only snapshot consumer. No schema
# filters omit auth/storage/extension-owned tables. Extension internals and
# managed role compatibility remain actual production inputs, not image claims.
INVENTORY_SQL = r'''
SELECT json_build_object('kind','catalog','schemas',
 (SELECT json_agg(json_build_array(nspname,pg_get_userbyid(nspowner),nspacl) ORDER BY nspname) FROM pg_namespace WHERE nspname !~ '^pg_' AND nspname <> 'information_schema'),
 'relations',(SELECT json_agg(json_build_array(n.nspname,c.relname,c.relkind,pg_get_userbyid(c.relowner),c.relacl,c.relrowsecurity,c.relforcerowsecurity,c.reloptions) ORDER BY n.nspname,c.relname) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'),
 'columns',(SELECT json_agg(json_build_array(n.nspname,c.relname,a.attname,a.attnum,format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,a.attgenerated,pg_get_expr(d.adbin,d.adrelid),a.attacl) ORDER BY n.nspname,c.relname,a.attnum) FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum WHERE a.attnum>0 AND NOT a.attisdropped AND n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'),
 'constraints',(SELECT json_agg(json_build_array(n.nspname,c.relname,k.conname,k.convalidated,pg_get_constraintdef(k.oid)) ORDER BY n.nspname,c.relname,k.conname) FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'),
 'indexes',(SELECT json_agg(json_build_array(schemaname,tablename,indexname,indexdef) ORDER BY schemaname,tablename,indexname) FROM pg_indexes WHERE schemaname !~ '^pg_' AND schemaname <> 'information_schema'),
 'policies',(SELECT json_agg(json_build_array(schemaname,tablename,policyname,permissive,roles,cmd,qual,with_check) ORDER BY schemaname,tablename,policyname) FROM pg_policies),
 'triggers',(SELECT json_agg(json_build_array(n.nspname,c.relname,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid)) ORDER BY n.nspname,c.relname,t.tgname) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE NOT t.tgisinternal AND n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'),
 'routines',(SELECT json_agg(json_build_array(n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),pg_get_userbyid(p.proowner),p.proacl,p.proconfig,pg_get_functiondef(p.oid)) ORDER BY n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE p.prokind IN ('f','p') AND n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'),
 'views',(SELECT json_agg(json_build_array(n.nspname,c.relname,pg_get_viewdef(c.oid)) ORDER BY n.nspname,c.relname) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind IN ('v','m') AND n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'),
 'extensions',(SELECT json_agg(json_build_array(e.extname,e.extversion,n.nspname,pg_get_userbyid(e.extowner),e.extrelocatable,
   (SELECT array_agg(format('%I.%I',cn.nspname,c.relname) ORDER BY config.ordinality) FROM unnest(e.extconfig) WITH ORDINALITY config(oid,ordinality) JOIN pg_class c ON c.oid=config.oid JOIN pg_namespace cn ON cn.oid=c.relnamespace),
   e.extcondition) ORDER BY e.extname) FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace),
 'roles',(SELECT json_agg(json_build_array(rolname,rolsuper,rolinherit,rolcreaterole,rolcreatedb,rolcanlogin,rolreplication,rolbypassrls,rolconnlimit,rolvaliduntil,rolconfig) ORDER BY rolname) FROM pg_roles),
 'memberships',(SELECT json_agg(json_build_array(pg_get_userbyid(roleid),pg_get_userbyid(member),pg_get_userbyid(grantor),admin_option,inherit_option,set_option) ORDER BY pg_get_userbyid(roleid),pg_get_userbyid(member)) FROM pg_auth_members),
 'large_object_metadata',(SELECT json_agg(json_build_array(oid,pg_get_userbyid(lomowner),lomacl) ORDER BY oid) FROM pg_largeobject_metadata),
 'large_objects',(SELECT json_agg(json_build_array(loid,pageno,encode(sha256(data),'hex'),octet_length(data)) ORDER BY loid,pageno) FROM pg_largeobject),
 'sequence_definitions',(SELECT json_agg(json_build_array(n.nspname,c.relname,format_type(s.seqtypid,NULL),s.seqstart,s.seqincrement,s.seqmax,s.seqmin,s.seqcache,s.seqcycle) ORDER BY n.nspname,c.relname) FROM pg_sequence s JOIN pg_class c ON c.oid=s.seqrelid JOIN pg_namespace n ON n.oid=c.relnamespace),
 'database_acl',(SELECT datacl FROM pg_database WHERE datname=current_database()),
 'tablespaces',(SELECT json_agg(json_build_array(spcname,pg_get_userbyid(spcowner),spcacl,spcoptions) ORDER BY spcname) FROM pg_tablespace),
 'types',(SELECT json_agg(json_build_array(n.nspname,t.typname,t.typtype,pg_get_userbyid(t.typowner),t.typacl,
   CASE WHEN t.typbasetype<>0 THEN format_type(t.typbasetype,t.typtypmod) END,t.typnotnull,t.typdefault,
   CASE WHEN t.typrelid<>0 THEN t.typrelid::regclass::text END,
   CASE WHEN t.typcollation<>0 THEN t.typcollation::regcollation::text END) ORDER BY n.nspname,t.typname)
   FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema'),
 'enum_labels',(SELECT json_agg(json_build_array(n.nspname,t.typname,e.enumsortorder,e.enumlabel) ORDER BY n.nspname,t.typname,e.enumsortorder)
   FROM pg_enum e JOIN pg_type t ON t.oid=e.enumtypid JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema'),
 'domain_constraints',(SELECT json_agg(json_build_array(n.nspname,t.typname,c.conname,c.convalidated,pg_get_constraintdef(c.oid)) ORDER BY n.nspname,t.typname,c.conname)
   FROM pg_constraint c JOIN pg_type t ON t.oid=c.contypid JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema'),
 'range_definitions',(SELECT json_agg(json_build_array(n.nspname,t.typname,format_type(r.rngsubtype,NULL),
   CASE WHEN r.rngcollation<>0 THEN r.rngcollation::regcollation::text END,
   format('%I.%I',opn.nspname,op.opcname),r.rngcanonical::regproc::text,r.rngsubdiff::regproc::text,format_type(r.rngmultitypid,NULL)) ORDER BY n.nspname,t.typname)
   FROM pg_range r JOIN pg_type t ON t.oid=r.rngtypid JOIN pg_namespace n ON n.oid=t.typnamespace JOIN pg_opclass op ON op.oid=r.rngsubopc JOIN pg_namespace opn ON opn.oid=op.opcnamespace
   WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema'),
 'collations',(SELECT json_agg(json_build_array(n.nspname,c.collname,pg_get_userbyid(c.collowner),to_jsonb(c)-'oid'-'collnamespace'-'collowner') ORDER BY n.nspname,c.collname)
   FROM pg_collation c JOIN pg_namespace n ON n.oid=c.collnamespace WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema'),
 'default_acls',(SELECT json_agg(json_build_array(pg_get_userbyid(d.defaclrole),n.nspname,d.defaclobjtype,d.defaclacl) ORDER BY pg_get_userbyid(d.defaclrole),n.nspname,d.defaclobjtype)
   FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace),
 'publications',(SELECT json_agg(json_build_array(p.pubname,pg_get_userbyid(p.pubowner),to_jsonb(p)-'oid'-'pubowner') ORDER BY p.pubname) FROM pg_publication p),
 'publication_relations',(SELECT json_agg(json_build_array(p.pubname,n.nspname,c.relname,
   (SELECT array_agg(a.attname ORDER BY a.attnum) FROM pg_attribute a WHERE a.attrelid=c.oid AND a.attnum=ANY(r.prattrs)),pg_get_expr(r.prqual,r.prrelid)) ORDER BY p.pubname,n.nspname,c.relname)
   FROM pg_publication_rel r JOIN pg_publication p ON p.oid=r.prpubid JOIN pg_class c ON c.oid=r.prrelid JOIN pg_namespace n ON n.oid=c.relnamespace),
 'publication_schemas',(SELECT json_agg(json_build_array(p.pubname,n.nspname) ORDER BY p.pubname,n.nspname) FROM pg_publication_namespace pn JOIN pg_publication p ON p.oid=pn.pnpubid JOIN pg_namespace n ON n.oid=pn.pnnspid));
SELECT format($q$SELECT json_build_object('kind','table','schema',%L,'name',%L,'count',count(*),'sha256',encode(sha256(convert_to(coalesce(string_agg(length(row_text)::text || ':' || row_text,'' ORDER BY row_text),''),'UTF8')),'hex')) FROM (SELECT to_jsonb(t)::text AS row_text FROM %I.%I t) rows;$q$,n.nspname,c.relname,n.nspname,c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE c.relkind IN ('r','m') AND n.nspname !~ '^pg_' AND n.nspname <> 'information_schema' ORDER BY n.nspname,c.relname
\gexec
SELECT format($q$SELECT json_build_object('kind','sequence','schema',%L,'name',%L,'last_value',last_value,'is_called',is_called) FROM %I.%I;$q$,n.nspname,c.relname,n.nspname,c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind='S' AND n.nspname !~ '^pg_' ORDER BY n.nspname,c.relname
\gexec
'''


def inventory_local(container, snapshot=None):
    isolated_container(container)
    if snapshot is not None and (not isinstance(snapshot, str) or not re.fullmatch(r'[0-9A-Fa-f]+-[0-9A-Fa-f]+-[0-9]+', snapshot)):
        raise Refusal('invalid_snapshot')
    start = 'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n'
    if snapshot is not None:
        start += "SET TRANSACTION SNAPSHOT '" + snapshot + "';\n"
    sql = start + "SET LOCAL timezone='UTC'; SET LOCAL datestyle='ISO, YMD'; SET LOCAL extra_float_digits=3;\n" + INVENTORY_SQL + '\nROLLBACK;\n'
    raw = run(['docker', 'exec', '-i', owned(container), 'psql', '-XqAt', '-v', 'ON_ERROR_STOP=1',
               '-U', 'postgres', '-d', 'postgres'], input=sql.encode(), timeout=300)
    records = [json.loads(line) for line in raw.decode().splitlines()]
    if not records or records[0].get('kind') != 'catalog' or not any(r.get('kind') == 'table' for r in records):
        raise Refusal('inventory_empty_or_malformed')
    return records


CATALOG_ARRAYS = {'schemas':3, 'relations':8, 'columns':10, 'constraints':5,
    'indexes':4, 'policies':8, 'triggers':5, 'routines':7, 'views':3,
    'extensions':7, 'roles':11, 'memberships':6, 'large_object_metadata':3,
    'large_objects':4, 'sequence_definitions':9, 'tablespaces':4,
    'types':10, 'enum_labels':4, 'domain_constraints':5, 'range_definitions':8,
    'collations':4, 'default_acls':4, 'publications':3, 'publication_relations':5,
    'publication_schemas':2}

# Catalog identities must be meaningful and unique even when both inputs have
# the same damage. Equality alone cannot turn malformed evidence into a pass.
CATALOG_IDENTITIES = {'schemas':1, 'relations':2, 'columns':3, 'constraints':3,
    'indexes':3, 'policies':3, 'triggers':3, 'routines':3, 'views':2,
    'extensions':1, 'roles':1, 'memberships':3, 'large_object_metadata':1,
    'large_objects':2, 'sequence_definitions':2, 'tablespaces':1,
    'types':2, 'enum_labels':2, 'domain_constraints':3, 'range_definitions':2,
    'collations':2, 'default_acls':3, 'publications':1, 'publication_relations':3,
    'publication_schemas':2}


def qualified_relation(value):
    """Decode the two identifiers emitted by PostgreSQL format('%I.%I')."""
    identifier = r'(?:"(?:[^"]|"")+"|[a-z_][a-z0-9_$]*)'
    match = re.fullmatch('(' + identifier + r')\.(' + identifier + ')', value)
    if match is None:
        raise Refusal('inventory_extension_config_malformed')
    return tuple(part[1:-1].replace('""', '"') if part.startswith('"') else part
                 for part in match.groups())


def inventoried_schema(name):
    # Match the SQL producer's namespace filter. System namespace objects are
    # outside its promised relation/column coverage, not necessarily absent.
    return not name.startswith('pg_') and name != 'information_schema'


def validate_inventory(records):
    if not isinstance(records, list) or not records or not isinstance(records[0], dict):
        raise Refusal('inventory_empty_or_malformed')
    catalog = records[0]
    if set(catalog) != {'kind','database_acl', *CATALOG_ARRAYS} or catalog['kind'] != 'catalog':
        raise Refusal('inventory_empty_or_malformed')
    for key, width in CATALOG_ARRAYS.items():
        rows = catalog[key]
        if rows is None and key not in {'schemas','relations','columns','roles','extensions','tablespaces','types'}:
            continue
        if not isinstance(rows, list) or not rows or any(not isinstance(row,list) or len(row)!=width for row in rows):
            raise Refusal('inventory_empty_or_malformed')
        identities = set()
        enum_orders = set()
        for row in rows:
            def string(value):
                return isinstance(value,str) and bool(value)
            def optional_string(value):
                return value is None or isinstance(value,str)
            def acl(value):
                return value is None or isinstance(value,list) and all(string(v) for v in value)
            valid_shape = True
            if key == 'types':
                valid_shape = (row[2] in ('b','c','d','e','m','p','r') and string(row[3]) and acl(row[4])
                    and optional_string(row[5]) and type(row[6]) is bool
                    and all(optional_string(v) for v in row[7:])
                    and (row[2]!='d' or string(row[5])))
            elif key == 'enum_labels':
                valid_shape = type(row[2]) in (int,float) and math.isfinite(row[2]) and isinstance(row[3],str)
                order = row[0],row[1],row[2]
                if not valid_shape or order in enum_orders:
                    raise Refusal('inventory_enum_order_malformed')
                enum_orders.add(order)
            elif key == 'domain_constraints':
                valid_shape = type(row[3]) is bool and string(row[4])
            elif key == 'range_definitions':
                valid_shape = string(row[2]) and optional_string(row[3]) and all(string(v) for v in row[4:])
            elif key == 'collations':
                d = row[3]
                valid_shape = (string(row[2]) and isinstance(d,dict) and d.get('collname')==row[1]
                    and d.get('collprovider') in ('d','c','i','b') and type(d.get('collisdeterministic')) is bool
                    and type(d.get('collencoding')) is int)
            elif key == 'default_acls':
                valid_shape = (row[2] in ('r','S','f','T','n') and isinstance(row[3],list)
                    and all(string(v) for v in row[3]))
            elif key == 'publications':
                d = row[2]
                valid_shape = (string(row[1]) and isinstance(d,dict) and d.get('pubname')==row[0]
                    and all(type(d.get(k)) is bool for k in ('puballtables','pubinsert','pubupdate','pubdelete','pubtruncate','pubviaroot')))
            elif key == 'publication_relations':
                valid_shape = ((row[3] is None or isinstance(row[3],list) and all(string(v) for v in row[3])
                    and len(row[3])==len(set(row[3]))) and optional_string(row[4]))
            if not valid_shape:
                raise Refusal('inventory_catalog_value_malformed')
            if key == 'extensions':
                if ((row[5] is None) != (row[6] is None)):
                    raise Refusal('inventory_extension_config_malformed')
                if row[5] is not None and (not isinstance(row[5], list) or not row[5]
                        or not all(isinstance(v, str) and v for v in row[5])
                        or not isinstance(row[6], list) or len(row[5]) != len(row[6])
                        or not all(isinstance(v, str) for v in row[6])):
                    raise Refusal('inventory_extension_config_malformed')
            identity = tuple(row[:CATALOG_IDENTITIES[key]])
            if key == 'enum_labels':
                # Two labels on one enum share schema/type; label is its identity.
                identity = row[0], row[1], row[3]
            if key in ('large_object_metadata', 'large_objects'):
                # PostgreSQL json_build_array renders OIDs as decimal strings.
                # Keep their actual type for the later exact comparison.
                oid = identity[0]
                valid = (type(oid) is int and oid > 0 or isinstance(oid, str)
                         and re.fullmatch(r'[1-9][0-9]*', oid) is not None)
                if key == 'large_objects':
                    valid = valid and type(identity[1]) is int and identity[1] >= 0
            else:
                valid = all(key == 'default_acls' and i == 1 and value is None or
                            isinstance(value, str) and (value or key in ('routines','enum_labels') and i == 2)
                            for i, value in enumerate(identity))
            if not valid:
                raise Refusal('inventory_empty_or_malformed')
            if identity in identities:
                raise Refusal('inventory_duplicate_identity')
            identities.add(identity)
    expected_enums = {(r[0],r[1]) for r in catalog['types'] if r[2]=='e'}
    actual_enums = {(r[0],r[1]) for r in catalog['enum_labels'] or []}
    expected_ranges = {(r[0],r[1]) for r in catalog['types'] if r[2]=='r'}
    actual_ranges = {(r[0],r[1]) for r in catalog['range_definitions'] or []}
    if expected_enums != actual_enums or expected_ranges != actual_ranges:
        raise Refusal('inventory_type_coverage_mismatch')
    domains = {(r[0],r[1]) for r in catalog['types'] if r[2]=='d'}
    publications = {r[0] for r in catalog['publications'] or []}
    relations = {(r[0],r[1]) for r in catalog['relations']}
    schemas = {r[0] for r in catalog['schemas']}
    roles = {r[0] for r in catalog['roles']}
    columns = {(r[0],r[1],r[2]) for r in catalog['columns']}
    if (any((r[0],r[1]) not in domains for r in catalog['domain_constraints'] or [])
            or any(r[0] not in publications or (r[1],r[2]) not in relations for r in catalog['publication_relations'] or [])
            or any(r[0] not in publications or r[1] not in schemas for r in catalog['publication_schemas'] or [])):
        raise Refusal('inventory_catalog_reference_mismatch')
    if (any(r[0] not in schemas or r[3] not in roles for r in catalog['types'])
            or any(r[0] not in schemas or r[2] not in roles for r in catalog['collations'] or [])
            or any(r[1] not in roles for r in catalog['publications'] or [])
            or any(r[0] not in roles or r[1] is not None and inventoried_schema(r[1])
                   and r[1] not in schemas for r in catalog['default_acls'] or [])
            or any((r[1],r[2],column) not in columns for r in catalog['publication_relations'] or []
                   for column in r[3] or [])):
        raise Refusal('inventory_catalog_reference_mismatch')
    for extension in catalog['extensions']:
        configs = [qualified_relation(value) for value in extension[5] or []]
        if len(configs) != len(set(configs)):
            raise Refusal('inventory_extension_config_malformed')
        if any(inventoried_schema(schema) and (schema,name) not in relations
               for schema,name in configs):
            raise Refusal('inventory_catalog_reference_mismatch')
    if catalog['database_acl'] is not None and not isinstance(catalog['database_acl'], list):
        raise Refusal('inventory_empty_or_malformed')
    expected = set()
    for relation in catalog['relations']:
        if not all(isinstance(value,str) and value for value in relation[:3]):
            raise Refusal('inventory_empty_or_malformed')
        if relation[2] in ('r','m','S'):
            expected.add(('sequence' if relation[2]=='S' else 'table', relation[0], relation[1]))
    seen = set()
    for row in records[1:]:
        if not isinstance(row,dict) or row.get('kind') not in ('table','sequence'):
            raise Refusal('inventory_empty_or_malformed')
        fields = {'kind','schema','name','count','sha256'} if row['kind']=='table' else {'kind','schema','name','last_value','is_called'}
        if set(row)!=fields or not all(isinstance(row[k],str) and row[k] for k in ('schema','name')):
            raise Refusal('inventory_empty_or_malformed')
        identity = row['kind'],row['schema'],row['name']
        if identity in seen:
            raise Refusal('inventory_duplicate_identity')
        seen.add(identity)
        if row['kind']=='table':
            if type(row['count']) is not int or row['count']<0 or not isinstance(row['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',row['sha256']):
                raise Refusal('inventory_empty_or_malformed')
        elif type(row['last_value']) is not int or type(row['is_called']) is not bool:
            raise Refusal('inventory_empty_or_malformed')
    if seen!=expected or not any(identity[0]=='table' for identity in seen):
        raise Refusal('inventory_coverage_mismatch')
    # Reject non-finite values anywhere, including otherwise unused metadata.
    json.dumps(records, sort_keys=True, allow_nan=False)


def compare_inventory(before, after):
    validate_inventory(before)
    validate_inventory(after)
    if json.dumps(before, sort_keys=True, allow_nan=False) != json.dumps(after, sort_keys=True, allow_nan=False):
        raise Refusal('restore_inventory_mismatch')
    return {'status': 'synthetic_inventory_equal', 'production_recovery_verified': False,
            'tables': sum(r.get('kind') == 'table' for r in before)}


if __name__ == '__main__':
    raise SystemExit(main())
