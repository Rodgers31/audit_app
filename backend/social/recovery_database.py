"""Bounded complete PostgreSQL inventory with an independently read signed witness.

This module reads actual databases. It refuses RLS-filtered reads, partial row
limits, omitted/changed relations, schema drift and same-store restore claims.
Trusted verification key is supplied separately; packet keys are never trusted.
No report authorizes publishing, key retirement, deletion, or off-host custody.
"""
import hashlib
import json
import re
from pathlib import Path
from uuid import UUID
from sqlalchemy import text
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from .privacy.deletion_ledger import canonical, _pairs

MAX_TABLES = 300
MAX_ROWS = 100_000
MAX_ROW_BYTES = 2_000_000
MAX_TOTAL_BYTES = 64_000_000
MAX_MANIFEST = 256_000


class DatabaseRecoveryError(ValueError):
    def __init__(self):
        super().__init__('DATABASE_RECOVERY_REFUSED')


def require(condition):
    if condition is not True:
        raise DatabaseRecoveryError()


def _identity_shape(value):
    import ipaddress
    require(type(value) is list and len(value) == 4)
    name, oid, address, port = value
    require(type(name) is str and 1 <= len(name.encode('utf-8')) <= 63 and '\x00' not in name)
    require(type(oid) is str and oid.isascii() and oid.isdecimal() and str(int(oid)) == oid and 0 < int(oid) < 2**32)
    if address is None or port is None:
        require(address is None and port is None)
    else:
        require(type(address) is str and 1 <= len(address) <= 64)
        ipaddress.ip_interface(address)
        require(type(port) is int and 1 <= port <= 65535)


def _backup_commitments(value):
    if value is None:
        return
    require(type(value) is dict and set(value) == {'envelopes_sha256','digests_sha256'})
    require(all(type(v) is str and re.fullmatch('[a-f0-9]{64}',v) is not None for v in value.values()))


def _setup(conn, schema):
    require(conn.dialect.name == 'postgresql')
    require(type(schema) is str and re.fullmatch(r'[a-z][a-z0-9_]{0,62}', schema) is not None and not schema.startswith('pg_') and schema != 'information_schema')
    conn.execute(text('SET TRANSACTION READ ONLY'))
    conn.execute(text("SET LOCAL statement_timeout='15s'"))
    conn.execute(text("SET LOCAL lock_timeout='2s'"))
    # off does not bypass RLS. PostgreSQL errors when a policy would filter rows.
    conn.execute(text('SET LOCAL row_security=off'))
    conn.execute(text("SET LOCAL timezone='UTC'"))
    conn.execute(text("SET LOCAL datestyle='ISO, YMD'"))
    return tuple(conn.execute(text('SELECT current_database(), (SELECT oid FROM pg_database WHERE datname=current_database())::text, inet_server_addr()::text, inet_server_port()')).one())


def _constraint_definition(definition):
    # pg_dump reparses an unbounded varchar ARRAY-to-text coercion as
    # individual element coercions. Normalize ONLY this equivalent membership
    # expression; arbitrary casts, functions, lengths and comparisons stay exact.
    match = re.fullmatch(r"CHECK \(([a-z_][a-z0-9_]*)::text = ANY \(ARRAY\[((?:'[a-z_]{1,64}'::character varying(?:::text)?)(?:, '[a-z_]{1,64}'::character varying(?:::text)?)*)\](?:::text\[\])?\)\)", definition)
    if match is None:
        return definition
    members = re.findall(r"'([a-z_]{1,64})'", match.group(2))
    return 'CHECK_TEXT_MEMBERSHIP:' + canonical([match.group(1), sorted(members)]).decode('ascii')


def _catalog(conn, schema):
    rows = conn.execute(text("""SELECT c.relname,c.relkind,c.relispartition,
        coalesce(jsonb_agg(jsonb_build_array(a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,a.attgenerated,pg_get_expr(d.adbin,d.adrelid),coll.collname) ORDER BY a.attnum) FILTER (WHERE a.attnum IS NOT NULL),'[]'::jsonb)::text
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        LEFT JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
        LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
        LEFT JOIN pg_collation coll ON coll.oid=a.attcollation
        WHERE n.nspname=:schema AND c.relkind IN ('r','p','f','m')
        GROUP BY c.oid,c.relname,c.relkind,c.relispartition ORDER BY c.relname"""), {'schema': schema}).all()
    require(0 < len(rows) <= MAX_TABLES)
    # Partition roots read their descendants exactly once. Foreign/materialized
    # storage requires a separate recovery contract and cannot be silently omitted.
    require(all(r[1] in ('r', 'p') for r in rows))
    catalog = {r[0]: {'kind': r[1], 'partition': r[2], 'columns': json.loads(r[3])} for r in rows}
    for name, definition in catalog.items():
        parameters = {'schema': schema, 'name': name}
        definition['constraints'] = list(conn.execute(text("""SELECT con.conname, pg_get_constraintdef(con.oid,true)
            FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=:schema AND c.relname=:name ORDER BY con.conname"""), parameters).tuples())
        definition['indexes'] = list(conn.execute(text("SELECT indexname,indexdef FROM pg_indexes WHERE schemaname=:schema AND tablename=:name ORDER BY indexname"), parameters).tuples())
        definition['triggers'] = list(conn.execute(text("""SELECT t.tgname,pg_get_triggerdef(t.oid,true) FROM pg_trigger t
            JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=:schema AND c.relname=:name AND NOT t.tgisinternal ORDER BY t.tgname"""), parameters).tuples())
        definition['policies'] = list(conn.execute(text("SELECT policyname,permissive,roles::text,cmd,qual,with_check FROM pg_policies WHERE schemaname=:schema AND tablename=:name ORDER BY policyname"), parameters).tuples())
        definition['rls'] = list(conn.execute(text("SELECT c.relrowsecurity,c.relforcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:schema AND c.relname=:name"), parameters).one())
        definition['constraints'] = [[row[0], _constraint_definition(row[1])] for row in definition['constraints']]
        for field in ('constraints','indexes','triggers','policies'):
            definition[field] = [list(row) for row in definition[field]]
    return catalog


def _inventory(conn, schema):
    catalog = _catalog(conn, schema)
    quote = conn.dialect.identifier_preparer.quote_identifier
    total_rows, total_bytes, tables = 0, 0, {}
    for name, definition in catalog.items():
        relation = 'ONLY ' + quote(schema) + '.' + quote(name)
        count = conn.execute(text('SELECT count(*) FROM ' + relation)).scalar_one()
        require(type(count) is int and count <= MAX_ROWS and total_rows + count <= MAX_ROWS)
        # Server-side cursor and per-row bound: never truncate a successful export.
        # PostgreSQL jsonb output orders object keys independently of Python.
        statement = text('SELECT CASE WHEN octet_length(row_to_json(t)::jsonb::text) <= '+str(MAX_ROW_BYTES)+' THEN row_to_json(t)::jsonb::text ELSE NULL END FROM ' + relation + ' AS t ORDER BY row_to_json(t)::jsonb::text COLLATE "C"')
        digest, read = hashlib.sha256(), 0
        result = conn.execution_options(stream_results=True, max_row_buffer=100).execute(statement)
        try:
            for (row,) in result:
                require(type(row) is str)
                raw = row.encode('utf-8')
                require(len(raw) <= MAX_ROW_BYTES)
                total_bytes += len(raw)
                require(total_bytes <= MAX_TOTAL_BYTES)
                digest.update(len(raw).to_bytes(8, 'big'))
                digest.update(raw)
                read += 1
                require(read <= count)
        finally:
            result.close()
        require(read == count)
        total_rows += read
        tables[name] = {'definition': definition, 'rows': read, 'sha256': digest.hexdigest()}
    functions = [list(row) for row in conn.execute(text("""SELECT p.proname,pg_get_function_identity_arguments(p.oid),pg_get_functiondef(p.oid)
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=:schema AND p.prokind IN ('f','p')
        ORDER BY p.proname,pg_get_function_identity_arguments(p.oid)"""), {'schema':schema})]
    views = [list(row) for row in conn.execute(text("""SELECT c.relname,pg_get_viewdef(c.oid,true),c.reloptions
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:schema AND c.relkind='v' ORDER BY c.relname"""), {'schema':schema})]
    sequences = {}
    for name, start, increment, minimum, maximum, cache, cycle in conn.execute(text("""SELECT c.relname,s.seqstart,s.seqincrement,s.seqmin,s.seqmax,s.seqcache,s.seqcycle
        FROM pg_sequence s JOIN pg_class c ON c.oid=s.seqrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=:schema ORDER BY c.relname"""), {'schema':schema}):
        state = list(conn.execute(text('SELECT last_value,is_called FROM '+quote(schema)+'.'+quote(name))).one())
        sequences[name] = {'definition':[start,increment,minimum,maximum,cache,cycle], 'state':state}
    enums = [list(row) for row in conn.execute(text("""SELECT t.typname,array_agg(e.enumlabel ORDER BY e.enumsortorder)
        FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace JOIN pg_enum e ON e.enumtypid=t.oid
        WHERE n.nspname=:schema GROUP BY t.oid,t.typname ORDER BY t.typname"""), {'schema':schema})]
    return {'schema': schema, 'tables': tables, 'functions': functions, 'views':views, 'sequences':sequences, 'enums':enums,
            'total_rows': total_rows, 'total_bytes': total_bytes}


def capture_database(engine, *, schema, signing_key, backup_sha256):
    """Two repeatable-read connections share one exported snapshot.

    The second connection independently counts and reads every relation; both
    complete projections must agree. A separately held witness key signs the
    exact DB identity, schema and full row commitments, including empty tables.
    Caller binds the independently persisted database dump by SHA256.
    """
    try:
        require(type(signing_key) is bytes and len(signing_key) == 32)
        require(type(backup_sha256) is str and re.fullmatch('[a-f0-9]{64}', backup_sha256) is not None)
        with engine.connect().execution_options(isolation_level='REPEATABLE READ') as source, source.begin():
            identity = _setup(source, schema)
            token = source.execute(text('SELECT pg_export_snapshot()')).scalar_one()
            first = _inventory(source, schema)
            with engine.connect().execution_options(isolation_level='REPEATABLE READ') as witness, witness.begin():
                # Generated by PostgreSQL, never accepted from a caller.
                require(re.fullmatch('[0-9A-Fa-f-]+', token) is not None)
                witness.execute(text("SET TRANSACTION SNAPSHOT '" + token + "'"))
                require(_setup(witness, schema) == identity)
                require(source.execute(text('SELECT pg_backend_pid()')).scalar_one() != witness.execute(text('SELECT pg_backend_pid()')).scalar_one())
                second = _inventory(witness, schema)
            require(first == second)
        payload = {'schema_version': 1, 'source_identity': list(identity), 'backup_sha256': backup_sha256, 'inventory': first,
            'generated_by': 'backend/social/recovery_database.py', 'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'extraction': 'supplied_backup_digest', 'key_backups': None}
        signature = Ed25519PrivateKey.from_private_bytes(signing_key).sign(canonical(payload)).hex()
        result = canonical({'payload': payload, 'signature': signature})
        require(len(result) <= MAX_MANIFEST)
        return result
    except Exception:
        pass
    raise DatabaseRecoveryError()


def recovery_snapshot_id(manifest):
    require(type(manifest) is bytes and 0 < len(manifest) <= MAX_MANIFEST)
    return str(UUID(bytes=hashlib.sha256(manifest).digest()[:16]))


def _verify_crypto(conn, schema, manifest, keyring_backup, digest_backup, subject_proofs):
    import base64
    from datetime import datetime, timezone
    from .recovery_inventory import FIELDS, MAX_RECORDS, _snapshot, _inventory as crypto_inventory, _subject_proofs, _execute, _canonical
    mapping = {'credentials':'social_credentials','flows':'social_oauth_flows',
        'ownership':'social_privacy_ownership','receipts':'social_privacy_receipts',
        'variants':'social_privacy_request_variants','accounts':'social_accounts','audits':'social_audit_events'}
    quote = conn.dialect.identifier_preparer.quote_identifier
    def portable(value):
        if type(value) is UUID:
            return str(value)
        if type(value) is bytes:
            return base64.b64encode(value).decode('ascii')
        if type(value) is memoryview:
            return base64.b64encode(bytes(value)).decode('ascii')
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).isoformat().replace('+00:00','Z')
        require(value is None or type(value) in (str,int,list,dict))
        return value
    tables, total = {}, 0
    for logical, physical in mapping.items():
        fields = sorted(FIELDS[logical])
        query = text('SELECT '+','.join(quote(f) for f in fields)+' FROM '+quote(schema)+'.'+quote(physical)+' ORDER BY id LIMIT '+str(MAX_RECORDS+1))
        rows = conn.execute(query).mappings().all()
        total += len(rows)
        require(total <= MAX_RECORDS)
        tables[logical] = [{field:portable(row[field]) for field in fields} for row in rows]
    snapshot_id = recovery_snapshot_id(manifest)
    _, indexed = _snapshot(_canonical({'schema_version':1,'snapshot_id':snapshot_id,'tables':tables}))
    envelopes, expected = crypto_inventory(indexed)
    subjects = _subject_proofs(subject_proofs,snapshot_id,expected,indexed)
    versions = _execute(envelopes,subjects,keyring_backup,digest_backup,indexed)
    return {'envelopes_verified':len(envelopes),'subject_records_verified':len(subjects),
        'active_envelope_version':versions[0],'active_digest_version':versions[1]}


def verify_database_restore(engine, manifest, *, schema, public_key, backup_sha256, keyring_backup=None, digest_backup=None, subject_proofs=None):
    """Works while the source DB/key store is absent; only public witness needed."""
    try:
        require(type(manifest) is bytes and 0 < len(manifest) <= MAX_MANIFEST)
        require(type(public_key) is bytes and len(public_key) == 32)
        packet = json.loads(manifest, object_pairs_hook=_pairs)
        require(type(packet) is dict and set(packet) == {'payload', 'signature'})
        payload = packet['payload']
        Ed25519PublicKey.from_public_bytes(public_key).verify(bytes.fromhex(packet['signature']), canonical(payload))
        require(type(payload) is dict and set(payload) == {'schema_version', 'source_identity', 'backup_sha256', 'inventory', 'generated_by', 'generator_sha256', 'extraction', 'key_backups'})
        require(payload['generated_by'] == 'backend/social/recovery_database.py' and type(payload['generator_sha256']) is str and re.fullmatch('[a-f0-9]{64}', payload['generator_sha256']) is not None and payload['extraction'] in ('supplied_backup_digest', 'pg_dump_exported_snapshot'))
        require(type(payload['schema_version']) is int and payload['schema_version'] == 1)
        require(type(backup_sha256) is str and re.fullmatch('[a-f0-9]{64}', backup_sha256) is not None and backup_sha256 == payload['backup_sha256'])
        _identity_shape(payload['source_identity'])
        _backup_commitments(payload['key_backups'])
        crypto_requested = any(v is not None for v in (keyring_backup,digest_backup,subject_proofs))
        require(not crypto_requested or all(type(v) is bytes for v in (keyring_backup,digest_backup,subject_proofs)))
        if crypto_requested:
            require(payload['key_backups'] == {'envelopes_sha256':hashlib.sha256(keyring_backup).hexdigest(),'digests_sha256':hashlib.sha256(digest_backup).hexdigest()})
        crypto_result = None
        with engine.connect().execution_options(isolation_level='REPEATABLE READ') as restored, restored.begin():
            identity = _setup(restored, schema)
            # Endpoints have aliases (IPv4/IPv6, masks and interfaces). They
            # cannot establish a distinct restore store. Conservatively require
            # a distinct database name/OID pair; ambiguous clones stay refused.
            require(list(identity[:2]) != payload['source_identity'][:2])
            actual = _inventory(restored, schema)
            require(canonical(actual) == canonical(payload['inventory']))
            if crypto_requested:
                crypto_result = _verify_crypto(restored,schema,manifest,keyring_backup,digest_backup,subject_proofs)
        return {'status': 'VERIFIED_BY_EXECUTION', 'scope': 'complete_selected_schema_database_rows',
            'recovery_snapshot_id': recovery_snapshot_id(manifest), 'cryptographic_continuity_verified': crypto_result is not None, 'crypto_inventory': crypto_result,
            'tables_verified': len(actual['tables']), 'records_verified': actual['total_rows'],
            'database_coverage_verified': True, 'source_database_required': False,
            'backup_snapshot_binding_verified': payload['extraction'] == 'pg_dump_exported_snapshot',
            'backup_custody_verified': False, 'off_host_verified': False,
            'production_authorized': False, 'publishing_authorized': False,
            'retirement_authorized': False, 'deletion_authorized': False, 'privilege_restoration_verified': False,
            'requires_external_deletion_ledger_reapplication': True}
    except Exception:
        pass
    raise DatabaseRecoveryError()


def _dump_snapshot(engine, snapshot, schema, destination, pg_dump):
    """Bounded child, same exported snapshot; no credentials in arguments/logs."""
    import os
    from pathlib import Path
    import selectors
    import signal
    import subprocess
    import time
    from .privacy.private_io import write_private
    require(type(pg_dump) is type(Path()) and pg_dump.is_absolute() and pg_dump.is_file())
    require(type(destination) is type(Path()) and destination.is_absolute() and not destination.exists() and not destination.is_symlink())
    url = engine.url
    require(url.get_backend_name() == 'postgresql' and all(type(v) is str and bool(v) for v in (url.host, url.database, url.username)))
    # No ambient service file, loader, credentials, proxy or inherited PGOPTIONS.
    environ = {'PATH': '/usr/bin:/bin', 'PGHOST': url.host, 'PGPORT': str(url.port or 5432),
        'PGUSER': url.username, 'PGDATABASE': url.database, 'PGCONNECT_TIMEOUT': '5',
        'PGSSLMODE': url.query.get('sslmode', 'prefer'), 'LC_ALL': 'C',
        'PGPASSFILE': '/dev/null', 'PGSERVICEFILE': '/dev/null'}
    if url.password is not None:
        environ['PGPASSWORD'] = url.password
    # Existing provider TLS root may be explicitly selected by this URL.
    if 'sslrootcert' in url.query:
        environ['PGSSLROOTCERT'] = url.query['sslrootcert']
    command = [str(pg_dump), '--format=custom', '--no-owner', '--no-privileges', '--no-password', '--schema='+schema, '--snapshot='+snapshot]
    process = subprocess.Popen(command, env=environ, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    content = bytearray()
    deadline = time.monotonic() + 45
    try:
        while selector.get_map():
            require(time.monotonic() <= deadline)
            for key, _ in selector.select(timeout=0.2):
                block = os.read(key.fileobj.fileno(), 65536)
                if not block:
                    selector.unregister(key.fileobj)
                    continue
                content.extend(block)
                require(len(content) <= MAX_TOTAL_BYTES)
        require(process.wait(timeout=max(0.1, deadline-time.monotonic())) == 0)
        # The dedicated child group must be empty after reaping pg_dump. An
        # exited launcher cannot orphan a descendant and still certify closure.
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise DatabaseRecoveryError()
        require(content[:5] == b'PGDMP')
        raw = bytes(content)
        write_private(destination, raw)
        return hashlib.sha256(raw).hexdigest()
    finally:
        selector.close()
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        process.stdout.close()


def export_database_backup(engine, *, schema, destination, signing_key, pg_dump, keyring_backup=None, digest_backup=None):
    """Export actual complete selected-schema bytes at the independently read snapshot.

    The primary transaction remains alive until pg_dump has finished using its
    exported snapshot. Source mutations cannot produce an unbound backup. This
    writes only a fresh private local file, never uploads or changes the DB.
    """
    try:
        require(type(signing_key) is bytes and len(signing_key) == 32)
        backups = None
        if keyring_backup is not None or digest_backup is not None:
            from .connections.recovery import parse_keyring
            from .recovery_inventory import _digest_backup
            require(type(keyring_backup) is bytes and type(digest_backup) is bytes)
            parse_keyring(keyring_backup)
            _digest_backup(digest_backup)
            backups = {'envelopes_sha256':hashlib.sha256(keyring_backup).hexdigest(),'digests_sha256':hashlib.sha256(digest_backup).hexdigest()}
        with engine.connect().execution_options(isolation_level='REPEATABLE READ') as source, source.begin():
            identity = _setup(source, schema)
            token = source.execute(text('SELECT pg_export_snapshot()')).scalar_one()
            require(re.fullmatch('[0-9A-Fa-f-]+', token) is not None)
            first = _inventory(source, schema)
            with engine.connect().execution_options(isolation_level='REPEATABLE READ') as witness, witness.begin():
                witness.execute(text("SET TRANSACTION SNAPSHOT '" + token + "'"))
                require(_setup(witness, schema) == identity)
                require(source.execute(text('SELECT pg_backend_pid()')).scalar_one() != witness.execute(text('SELECT pg_backend_pid()')).scalar_one())
                require(_inventory(witness, schema) == first)
            digest = _dump_snapshot(engine, token, schema, destination, pg_dump)
        payload = {'schema_version': 1, 'source_identity': list(identity), 'backup_sha256': digest, 'inventory': first,
            'generated_by': 'backend/social/recovery_database.py', 'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'extraction': 'pg_dump_exported_snapshot', 'key_backups': backups}
        result = canonical({'payload': payload, 'signature': Ed25519PrivateKey.from_private_bytes(signing_key).sign(canonical(payload)).hex()})
        require(len(result) <= MAX_MANIFEST)
        return result
    except Exception:
        pass
    raise DatabaseRecoveryError()
