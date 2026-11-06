#!/usr/bin/env python3
"""Offline preparation inventory. No database, provider, build or activation port.

Exit 0: packet integrity only. Exit 2: malformed/missing input. Exit 3: valid
readiness/capacity inventory with acceptance held. Hashes do not prove issuers.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys

sys.dont_write_bytecode = True
GATE_IDS = ('release_inputs', 'production_artifacts', 'schema_role_tls', 'rollback',
            'full15', 'replay', 'daily', 'weekly', 'storage_writers', 'db_exports',
            'custody_restore', 'host_stop', 'capacity', 'media_browser',
            'saved_grants', 'privacy', 'owner_stage')
OFF_CONTROLS = ('publishing', 'media_uploads', 'publishing_workers',
                'financial_generation', 'drafts', 'shadow', 'auto_approve',
                'auto_schedule', 'auto_publish', 'source_generation_hooks')
STATES = {'pending_engineering', 'pending_authority', 'historical_scoped', 'prepared'}
HASH = re.compile(r'[0-9a-f]{64}\Z')
DOCS = 'docs/releases/deployment-readiness-20261105'
SCRIPTS = 'scripts/verification/deployment_readiness_20261105'
SOURCE_INPUTS = (
    '.github/workflows/seed.yml', 'backend/Dockerfile.prod', 'frontend/Dockerfile.prod',
    'frontend/.nvmrc', 'frontend/package.json', 'frontend/package-lock.json',
    'frontend/scripts/verify-runtime-dependencies.cjs',
    'frontend/scripts/verify-native-dependencies.mjs', 'frontend/scripts/container-config.cjs',
    'backend/requirements.txt', 'backend/security-constraints.txt',
    'backend/ingestion-runtime.lock.json', 'backend/database.py', 'backend/request_database.py',
    'backend/services/admin_audit_storage.py', 'backend/social/worker/config.py',
    'backend/social/worker/role_contract.py', 'backend/social_worker_supervisor.py',
    'backend/social/connections/verification_process.py',
    'backend/social/connections/verification_execution.py',
    'backend/social/connections/verification_protocol.py',
    'backend/social/connections/verification_budget.py',
    'backend/social/connections/provider.py', 'backend/social/connections/service.py',
    'backend/social/connections/api.py', 'backend/social/media/storage.py',
    'backend/social/media/config.py', 'backend/social/media/recovery_packet.py',
    'backend/social/media/recovery.py', 'backend/social/media/maintenance.py',
    'backend/social/privacy/policy.py', 'backend/social/connections/callback_ingress.py',
    'backend/seeding/source_plan.py', 'tools/nightly_acceptance_20261105/runtime.py',
    'tools/nightly_acceptance_20261105/record.py', 'tools/nightly_acceptance_20261105/verify.py',
    'tools/nightly_acceptance_20261105/operational.py',
)


class Refusal(ValueError):
    """The requested evidence cannot be established."""


def require(condition, message):
    if not condition:
        raise Refusal(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _absolute_parts(path):
    raw = os.fspath(path)
    require(isinstance(raw, str) and raw.startswith('/') and '\x00' not in raw,
            'absolute path required')
    parts = raw.split('/')[1:]
    require(parts and all(p not in ('', '.', '..') for p in parts), 'path alias refused')
    return parts


@contextmanager
def parent_fd(path):
    """Retain every directory binding; never resolve a symlink ancestor."""
    parts = _absolute_parts(path)
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        yield fd, parts[-1]
    except OSError as exc:
        raise Refusal('path unavailable or not a real directory') from exc
    finally:
        os.close(fd)


def read_regular(path, limit=64 * 1024 * 1024):
    require(type(limit) is int and limit > 0, 'invalid read bound')
    try:
        with parent_fd(path) as (directory, name):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            try:
                before = os.fstat(fd)
                require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
                        'regular single-link file required')
                require(0 < before.st_size <= limit, 'empty or oversized file')
                with os.fdopen(os.dup(fd), 'rb') as stream:
                    raw = stream.read(limit + 1)
                after = os.fstat(fd)
                require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                        == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                        and len(raw) == before.st_size, 'file changed during read')
                linked = os.stat(name, dir_fd=directory, follow_symlinks=False)
                require((linked.st_dev, linked.st_ino) == (before.st_dev, before.st_ino),
                        'file binding changed')
                return raw
            finally:
                os.close(fd)
    except OSError as exc:
        raise Refusal('file unavailable or unsafe') from exc


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def _finite_float(value):
    number = float(value)
    require(math.isfinite(number), 'nonfinite JSON number')
    return number


def _bounded_integer(value):
    require(len(value.lstrip('-')) <= 20, 'JSON integer exceeds inventory bound')
    return int(value)


def _json_bounds(value):
    # Lazy iterators bound the traversal stack without copying wide containers.
    stack, nodes = [(iter((value,)), 0)], 0
    while stack:
        iterator, parent_depth = stack[-1]
        try:
            item = next(iterator)
        except StopIteration:
            stack.pop()
            continue
        nodes += 1
        require(nodes <= 20_000, 'JSON inventory node ceiling')
        if type(item) in (dict, list):
            depth = parent_depth + 1
            require(depth <= 32, 'JSON inventory depth ceiling')
            stack.append((iter(item.values() if type(item) is dict else item), depth))


def parse_object(raw):
    require(type(raw) in (bytes, str) and 0 < len(raw) <= 4 * 1024 * 1024,
            'bounded JSON bytes or text required')
    if type(raw) is str:
        try:
            raw = raw.encode('utf-8')
        except UnicodeError as exc:
            raise Refusal('JSON text must encode as UTF-8') from exc
        require(len(raw) <= 4 * 1024 * 1024, 'UTF-8 JSON byte ceiling')
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_float=_finite_float,
                           parse_int=_bounded_integer,
                           parse_constant=lambda _: (_ for _ in ()).throw(Refusal('nonfinite JSON')))
    except Refusal:
        raise
    except (UnicodeError, ValueError, RecursionError, OverflowError) as exc:
        raise Refusal('malformed JSON') from exc
    require(type(value) is dict and bool(value), 'nonempty JSON object required')
    _json_bounds(value)
    return value


def load_object(path):
    return parse_object(read_regular(path, 4 * 1024 * 1024))


def relative(name):
    require(type(name) is str and name and not name.startswith('/')
            and all(p not in ('', '.', '..') for p in name.split('/'))
            and '\\' not in name and '\x00' not in name, 'relative canonical path required')
    return name


def inventory(root, names):
    require(type(names) is list and names and len(names) <= 1000
            and len(names) == len(set(names)), 'nonempty unique inventory required')
    root = Path(root)
    _absolute_parts(root)
    result = []
    for name in sorted(names):
        raw = read_regular(root / relative(name))
        result.append({'path': name, 'bytes': len(raw), 'sha256': digest(raw)})
    return result


def check_inventory(root, records):
    require(type(records) is list and 0 < len(records) <= 1000, 'source inventory required')
    names = []
    for row in records:
        require(type(row) is dict and set(row) == {'path', 'bytes', 'sha256'}, 'invalid source record')
        names.append(relative(row['path']))
        require(type(row['bytes']) is int and row['bytes'] > 0, 'positive exact byte count required')
        require(type(row['sha256']) is str and HASH.fullmatch(row['sha256']), 'invalid hash')
    actual = inventory(root, names)
    require(sorted(records, key=lambda x: x['path']) == actual, 'source inventory changed')
    return actual


def check_catalog(catalog):
    require(type(catalog) is dict and set(catalog) == {'schema', 'private_index_sha256', 'records'}
            and catalog['schema'] == 'readiness-evidence-catalog-v1'
            and type(catalog['private_index_sha256']) is str
            and HASH.fullmatch(catalog['private_index_sha256']), 'invalid evidence catalog')
    return _evidence_records(catalog['records'])


def _evidence_records(rows):
    require(type(rows) is list and 0 < len(rows) <= 1000, 'nonempty catalog required')
    result = {}
    for row in rows:
        require(type(row) is dict and set(row) == {'id', 'sha256', 'bytes', 'scope'}, 'invalid evidence record')
        require(type(row['id']) is str and bool(row['id']) and row['id'] not in result
                and type(row['scope']) is str and bool(row['scope'])
                and type(row['sha256']) is str and HASH.fullmatch(row['sha256'])
                and type(row['bytes']) is int and row['bytes'] > 0, 'invalid or duplicate evidence identity')
        result[row['id']] = row
    return result


def check_matrix(matrix, evidence_records=None):
    require(type(matrix) is dict and set(matrix) == {'schema', 'scope', 'release_authorized', 'controls', 'gates'}
            and matrix.get('schema') == 'deployment-readiness-matrix-v1'
            and matrix.get('scope') == 'PREPARATION_ONLY'
            and matrix.get('release_authorized') is False, 'preparation-only matrix required')
    require(evidence_records is None or type(evidence_records) is dict, 'catalog mapping required')
    if evidence_records is not None:
        require(evidence_records == _evidence_records(list(evidence_records.values())),
                'catalog keys must equal strictly validated record IDs')
    controls = matrix.get('controls')
    require(type(controls) is dict and set(controls) == set(OFF_CONTROLS)
            and all(v is False for v in controls.values()), 'all holds must remain explicit false')
    gates = matrix.get('gates')
    require(type(gates) is list and len(gates) == len(GATE_IDS), 'complete gate inventory required')
    ids = []
    for gate in gates:
        require(type(gate) is dict and set(gate) == {'id', 'state', 'evidence', 'next', 'authority'},
                'invalid gate shape')
        require(type(gate['id']) is str and type(gate['state']) is str
                and gate['state'] in STATES, 'acceptance state forbidden in preparation packet')
        require(type(gate['evidence']) is list and all(type(x) is str and x for x in gate['evidence'])
                and len(gate['evidence']) == len(set(gate['evidence'])), 'invalid evidence references')
        require(gate['state'] != 'historical_scoped' or bool(gate['evidence']), 'historical leaf needs evidence')
        require(not gate['evidence'] or (evidence_records is not None
                and all(x in evidence_records for x in gate['evidence'])), 'unresolved evidence reference')
        require(all(type(gate[k]) is str and gate[k].strip() for k in ('next', 'authority')), 'missing next step or authority')
        ids.append(gate['id'])
    require(len(set(ids)) == len(GATE_IDS) and set(ids) == set(GATE_IDS), 'missing or duplicate gate')
    return {'packet_structure': 'VERIFIED', 'release': 'HELD', 'launch': 'HELD',
            'gate_count': len(gates), 'states': {s: sum(g['state'] == s for g in gates) for s in sorted(STATES)}}


def required_paths(root):
    """Complete flat owned packet plus the explicit inspected source boundary."""
    paths = set(SOURCE_INPUTS)
    for folder in (DOCS, SCRIPTS):
        with parent_fd(Path(root) / folder / 'inventory-marker') as (directory, _):
            with os.scandir(directory) as entries:
                for entry in entries:
                    require(len(paths) < 1000, 'source inventory ceiling')
                    require(entry.is_file(follow_symlinks=False), 'unexpected directory or nonregular packet entry')
                    if folder == DOCS and entry.name == 'source-manifest.json':
                        continue
                    paths.add(folder + '/' + entry.name)
    require({SCRIPTS + '/packet.py', SCRIPTS + '/test_packet.py',
             SCRIPTS + '/test_review_boundaries.py', SCRIPTS + '/catalog_preflight.sql',
             SCRIPTS + '/capacity.pending.json', DOCS + '/gate-matrix.json',
             DOCS + '/evidence-catalog.json', DOCS + '/README.md', DOCS + '/GATES.md',
             DOCS + '/RELEASE.md', DOCS + '/ROLLBACK.md', DOCS + '/OBSERVATION.md',
             DOCS + '/LAUNCH.md', DOCS + '/EVIDENCE.md'} <= paths, 'required packet input absent')
    return paths


def capacity(rows):
    require(type(rows) is list and 0 < len(rows) <= 64, 'capacity partitions required')
    result, keys = [], set()
    for row in rows:
        require(type(row) is dict and set(row) == {'unit', 'route_ref', 'limit', 'measured_peak', 'other_population', 'accepted_reserve'}, 'invalid capacity partition')
        require(row['unit'] in ('pooler_clients', 'per_login_database_backends', 'physical_pg'), 'distinct limit unit required')
        require(type(row['route_ref']) is str and HASH.fullmatch(row['route_ref']), 'hashed route reference required')
        key = (row['unit'], row['route_ref'])
        require(key not in keys, 'duplicate capacity partition')
        keys.add(key)
        require(type(row['limit']) is int and row['limit'] > 0, 'positive capacity limit required')
        for field in ('measured_peak', 'other_population', 'accepted_reserve'):
            value = row[field]
            require(value is None or (type(value) is int and value >= (1 if field == 'accepted_reserve' else 0)), 'unknown or exact nonnegative measurement required; reserve must be positive')
        complete = all(row[k] is not None for k in ('measured_peak', 'other_population', 'accepted_reserve'))
        remaining = row['limit'] - row['measured_peak'] - row['other_population'] - row['accepted_reserve'] if complete else None
        result.append({**row, 'remaining': remaining, 'arithmetic': 'WITHIN' if remaining is not None and remaining >= 0 else 'UNKNOWN' if remaining is None else 'OVER'})
    return {'state': 'PENDING', 'production_capacity_accepted': False, 'partitions': result,
            'scope': 'UNIT_PARTITIONED_ARITHMETIC_NOT_REPRESENTATIVE_FIT_OR_OWNER_ACCEPTANCE'}


def metadata(roots, *, max_entries=5000, max_depth=4):
    require(type(roots) is list and 0 < len(roots) <= 4, 'one to four explicit previously authorized roots required')
    require(type(max_entries) is int and 1 <= max_entries <= 5000
            and type(max_depth) is int and 0 <= max_depth <= 4, 'bounded census required')
    names = [os.fspath(p) for p in roots]
    require(len(set(names)) == len(names), 'duplicate root')
    rows = []
    def identity(value):
        return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
                value.st_mtime_ns, value.st_ctime_ns)
    def visit(directory, leaf, path, depth):
        require(len(rows) < max_entries, 'metadata entry ceiling reached; no complete census')
        try:
            value = os.stat(leaf, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            rows.append({'locator_sha256': digest(os.fsencode(path)), 'kind': 'absent'})
            return
        kind = 'symlink' if stat.S_ISLNK(value.st_mode) else 'directory' if stat.S_ISDIR(value.st_mode) else 'regular' if stat.S_ISREG(value.st_mode) else 'other'
        rows.append({'locator_sha256': digest(os.fsencode(path)), 'kind': kind,
                     'bytes': value.st_size, 'mode': oct(stat.S_IMODE(value.st_mode)),
                     'mtime_utc': datetime.fromtimestamp(value.st_mtime, timezone.utc).isoformat(),
                     'depth_boundary': kind == 'directory' and depth == max_depth})
        if kind == 'directory' and depth < max_depth:
            fd = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            try:
                require(identity(os.fstat(fd)) == identity(value), 'directory binding changed')
                children = []
                with os.scandir(fd) as entries:
                    for entry in entries:
                        require(len(children) < max_entries - len(rows), 'directory exceeds metadata bound')
                        children.append(entry.name)
                for name in sorted(children):
                    # Descriptor-relative lstat only; never reopen the absolute child path.
                    visit(fd, name, Path(path) / name, depth + 1)
                require(identity(os.fstat(fd)) == identity(value), 'directory changed during census')
            finally:
                os.close(fd)
        require(identity(os.stat(leaf, dir_fd=directory, follow_symlinks=False)) == identity(value),
                'metadata binding changed during census')
    for path in roots:
        with parent_fd(path) as (directory, leaf):
            visit(directory, leaf, Path(path), 0)
    return {'scope': 'METADATA_ONLY_NOT_EXPORT_CLASSIFICATION', 'retention_compliant': False,
            'observed_at': datetime.now(timezone.utc).isoformat(), 'roots_sha256': [digest(os.fsencode(p)) for p in roots],
            'entries': rows, 'regular_files': sum(x['kind'] == 'regular' for x in rows),
            'limits': {'max_entries': max_entries, 'max_depth': max_depth},
            'boundary': 'Limited roots/depth; absent is not disposed-with-evidence. Mtime/size/suffix do not classify exports or exceptions.'}


def publish(path, value, source_root):
    raw = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    output, source = Path(path), Path(source_root)
    _absolute_parts(output)
    _absolute_parts(source)
    require(output != source and source not in output.parents, 'output must be external to measured source')
    try:
        with parent_fd(output) as (directory, name):
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        require(read_regular(output) == raw, 'receipt readback changed')
    except OSError as exc:
        raise Refusal('output must be fresh with safe existing parent') from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    verify = sub.add_parser('integrity', help='verify source and packet bytes only; never release acceptance')
    verify.add_argument('--manifest', required=True, type=Path)
    ready = sub.add_parser('readiness', help='same verification, exit 3 because operational gates are held')
    ready.add_argument('--manifest', required=True, type=Path)
    cap = sub.add_parser('capacity', help='unknown measurements remain pending; exit 3')
    cap.add_argument('--input', required=True, type=Path)
    census = sub.add_parser('metadata', help='no export/object contents; explicit previously authorized roots only')
    census.add_argument('--candidate-root', action='append', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command in ('integrity', 'readiness'):
            require(args.manifest == args.root / DOCS / 'source-manifest.json', 'canonical packet manifest required')
            manifest_raw = read_regular(args.manifest, 4 * 1024 * 1024)
            manifest = parse_object(manifest_raw)
            require(set(manifest) == {'schema', 'baseline_commit', 'baseline_tree', 'matrix', 'files'}
                    and manifest['schema'] == 'deployment-readiness-source-v1'
                    and all(type(manifest[k]) is str and re.fullmatch('[0-9a-f]{40}', manifest[k]) for k in ('baseline_commit', 'baseline_tree')), 'invalid source manifest')
            measured = check_inventory(args.root, manifest['files'])
            require({r['path'] for r in measured} == required_paths(args.root), 'incomplete or unexpected source inventory')
            require(digest(read_regular(Path(__file__).absolute()))
                    == next(r['sha256'] for r in measured if r['path'] == SCRIPTS + '/packet.py'),
                    'running verifier differs from measured tool')
            matrix_path = relative(manifest['matrix'])
            require(matrix_path == DOCS + '/gate-matrix.json', 'canonical measured matrix required')
            catalog = check_catalog(load_object(args.root / DOCS / 'evidence-catalog.json'))
            result = check_matrix(load_object(args.root / matrix_path), catalog)
            result.update({'source_files': len(measured), 'manifest_sha256': digest(manifest_raw),
                           'scope': 'PACKET_INTEGRITY_ONLY_NOT_ISSUER_OR_DEPLOYMENT_ACCEPTANCE'})
            # Bind the original paths again, including the matrix, after consumption.
            check_inventory(args.root, manifest['files'])
            require({r['path'] for r in measured} == required_paths(args.root)
                    and read_regular(args.manifest, 4 * 1024 * 1024) == manifest_raw, 'packet input changed during consumption')
            code = 0 if args.command == 'integrity' else 3
        elif args.command == 'capacity':
            value = load_object(args.input)
            require(set(value) == {'partitions'}, 'invalid capacity envelope')
            result, code = capacity(value['partitions']), 3
        else:
            result, code = metadata(args.candidate_root), 3
        result.update({'generated_by': str(Path(__file__).absolute()),
                       'generator_sha256': digest(read_regular(Path(__file__).absolute())),
                       'at': datetime.now(timezone.utc).isoformat(), 'acceptance': False})
        if args.output:
            publish(args.output, result, args.root)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return code
    except (Refusal, TypeError, KeyError, OSError) as exc:
        print(json.dumps({'verdict': 'FAILED', 'reason': str(exc), 'acceptance': False}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
