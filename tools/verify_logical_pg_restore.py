#!/usr/bin/env python3
"""Verify an acquired logical dump on an already restored, isolated local target.

No restore, DDL, production connection, app import, or catalog write is performed.
The original physical catalog comparison and its failed receipt remain intact.
Only active-column physical numbers and ACL array order have logical equivalents;
one explicitly reviewed default ACL requires a fresh target acldefault readback.
"""
from __future__ import annotations

import argparse
import copy
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess

import reviewed_pg_acquisition as acquisition

backup = acquisition.backup
Refusal = backup.Refusal
TARGET_PATTERN = r'round20_s1_actual_restore_[0-9a-f]{12}'
DEFAULT_RELATION = ('realtime', 'schema_migrations')
DEFAULT_OWNER = 'supabase_admin'
DEFAULT_ACL = ['supabase_admin=arwdDxtm/supabase_admin']
COMPARISON_MODE = 'reviewed_logical_database_restore'
EQUIVALENCES = ['active_column_physical_number_to_relative_ordinal',
                'ACL_array_order_preserving_verbatim_items',
                'realtime.schema_migrations_owner_default_with_live_readback']
# Preserve each item verbatim; sorting cannot erase grantor or grant options.
ACL_ITEM = re.compile(r'(?P<grantee>"(?:[^"]|"")*"|[^=/"\s]*)='
                      r'(?P<privileges>(?:[arwdDxtmXUCTcsA]\*?)*)/'
                      r'(?P<grantor>"(?:[^"]|"")*"|[^=/"\s]+)')
ACL_FIELDS = {'schemas': 2, 'relations': 4, 'columns': 9, 'routines': 4,
              'types': 4, 'default_acls': 3, 'large_object_metadata': 2,
              'tablespaces': 2}
DEFAULT_READBACK_SQL = """
SELECT json_build_object('kind','reviewed_relation_default_acl',
 'schema',n.nspname,'name',c.relname,'owner',pg_get_userbyid(c.relowner),
 'relkind',c.relkind,'actual_acl',c.relacl,'default_acl',acldefault('r',c.relowner))
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='realtime' AND c.relname='schema_migrations';
"""


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_acl(value, roles=None):
    if value is None:
        return None
    if not isinstance(value, list):
        raise Refusal('logical_acl_shape')
    identities = set()
    for item in value:
        match = ACL_ITEM.fullmatch(item) if isinstance(item, str) and '\x00' not in item else None
        if match is None:
            raise Refusal('logical_acl_item_malformed')
        def role_name(value):
            return value[1:-1].replace('""', '"') if value.startswith('"') else value
        identity = role_name(match['grantee']), role_name(match['grantor'])
        if not identity[1] or match['grantee'] == '""':
            raise Refusal('logical_acl_empty_named_role')
        if roles is not None and (identity[1] not in roles or identity[0] and identity[0] not in roles):
            raise Refusal('logical_acl_role_missing')
        privileges = match['privileges'].replace('*', '')
        if identity in identities or len(privileges) != len(set(privileges)):
            raise Refusal('logical_acl_duplicate')
        identities.add(identity)
    return sorted(value)


def validate_catalog_fields(records):
    """Validate typed producer fields and catalog references before equality."""
    catalog = records[0]
    def text(value, empty=False):
        return isinstance(value, str) and (bool(value) or empty) and '\x00' not in value
    def optional_text(value):
        return value is None or text(value, empty=True)
    def strings(value):
        return value is None or (isinstance(value, list) and bool(value)
                                 and all(text(v) for v in value))
    def settings(value):
        if not strings(value):
            return False
        if value is None:
            return True
        names = [v.split('=', 1)[0] for v in value]
        return (all('=' in v and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*', n)
                    for v, n in zip(value, names)) and len(names) == len(set(names)))
    def require(condition):
        if not condition:
            raise Refusal('logical_catalog_field_or_reference_malformed')
    # PostgreSQL text cannot contain NUL, even in fields otherwise compared raw.
    def no_nul(value):
        if isinstance(value, str):
            require('\x00' not in value)
        elif isinstance(value, list):
            for v in value: no_nul(v)
        elif isinstance(value, dict):
            for k, v in value.items(): no_nul(k); no_nul(v)
    no_nul(records)
    roles = {r[0] for r in catalog['roles']}
    schemas = {r[0] for r in catalog['schemas']}
    relations = {tuple(r[:2]): r for r in catalog['relations']}
    def namespace(value):
        return value in schemas or value == 'information_schema' or value.startswith('pg_')
    for r in catalog['roles']:
        require(all(type(v) is bool for v in r[1:8]) and type(r[8]) is int
                and -1 <= r[8] <= 2147483647 and (r[9] is None or text(r[9])) and settings(r[10]))
    for r in catalog['schemas']:
        require(r[1] in roles)
    for r in catalog['memberships'] or []:
        require(all(v in roles for v in r[:3]) and r[0] != r[1]
                and all(type(v) is bool for v in r[3:]))
    for r in catalog['constraints'] or []:
        require(tuple(r[:2]) in relations and type(r[3]) is bool and text(r[4]))
    for r in catalog['indexes'] or []:
        require(tuple(r[:2]) in relations and (r[0],r[2]) in relations
                and relations[(r[0],r[2])][2] in ('i','I') and text(r[3]))
    for r in catalog['policies'] or []:
        require(tuple(r[:2]) in relations and r[3] in ('PERMISSIVE','RESTRICTIVE')
                and isinstance(r[4], list) and bool(r[4]) and len(r[4]) == len(set(r[4]))
                and all(text(v) and (v == 'public' or v in roles) for v in r[4])
                and r[5] in ('ALL','SELECT','INSERT','UPDATE','DELETE')
                and optional_text(r[6]) and optional_text(r[7]))
    for r in catalog['triggers'] or []:
        require(tuple(r[:2]) in relations and r[3] in ('O','D','R','A') and text(r[4]))
    for r in catalog['routines'] or []:
        require(r[0] in schemas and text(r[2], empty=True) and r[3] in roles
                and settings(r[5]) and text(r[6]))
    for r in catalog['views'] or []:
        require(tuple(r[:2]) in relations and relations[tuple(r[:2])][2] in ('v','m') and text(r[2]))
    for r in catalog['extensions']:
        require(text(r[1]) and text(r[2]) and namespace(r[2]) and r[3] in roles and type(r[4]) is bool)
    for r in catalog['tablespaces']:
        require(r[1] in roles and strings(r[3]))
    sequences = {key for key, r in relations.items() if r[2] == 'S'}
    definitions = catalog['sequence_definitions'] or []
    require({tuple(r[:2]) for r in definitions} == sequences)
    for r in definitions:
        require(r[2] in ('smallint','integer','bigint') and all(type(v) is int for v in r[3:8])
                and all(-(2**63) <= v < 2**63 for v in r[3:8]) and r[4] != 0
                and r[6] <= r[3] <= r[5] and r[6] < r[5] and r[7] > 0 and type(r[8]) is bool)
    metadata = catalog['large_object_metadata'] or []
    large_oids = {r[0] for r in metadata}
    for r in metadata:
        require(r[1] in roles)
    for r in catalog['large_objects'] or []:
        require(r[0] in large_oids and text(r[2]) and re.fullmatch('[0-9a-f]{64}', r[2])
                and type(r[3]) is int and 0 <= r[3] <= 2048)
    for r in catalog['types']:
        require(all(optional_text(v) for v in r[5:6] + r[7:]))
    for r in catalog['domain_constraints'] or []:
        require(type(r[3]) is bool and text(r[4]))
    for r in catalog['range_definitions'] or []:
        require(text(r[2]) and optional_text(r[3]) and all(text(v) for v in r[4:]))
    for r in catalog['collations'] or []:
        require(all(text(k) for k in r[3]) and all(v is None or type(v) in (str,bool,int) for v in r[3].values()))
    for r in catalog['publication_relations'] or []:
        require(optional_text(r[4]))


def canonical_inventory(records):
    """Make a copy; retain row order and every field except physical attnum gaps."""
    backup.validate_inventory(records)
    validate_catalog_fields(records)
    result = copy.deepcopy(records)
    catalog = result[0]
    roles = {row[0] for row in catalog['roles']}
    schemas = {row[0] for row in catalog['schemas']}
    relations = {(row[0], row[1]) for row in catalog['relations']}
    for row in catalog['relations']:
        if (row[0] not in schemas or row[2] not in ('r','i','S','t','v','m','c','f','p','I')
                or row[3] not in roles or type(row[5]) is not bool or type(row[6]) is not bool
                or row[7] is not None and (not isinstance(row[7], list)
                    or any(not isinstance(v, str) or not v or '\x00' in v for v in row[7]))):
            raise Refusal('logical_relation_malformed')
    previous = None
    ordinal = 0
    for row in catalog['columns']:
        key = row[0], row[1], row[3]
        if (type(row[3]) is not int or not 1 <= row[3] <= 32767
                or (row[0], row[1]) not in relations
                or previous is not None and key <= previous
                or not isinstance(row[4], str) or not row[4] or '\x00' in row[4]
                or type(row[5]) is not bool or row[6] not in ('','a','d') or row[7] not in ('','s')
                or row[8] is not None and (not isinstance(row[8], str) or '\x00' in row[8])):
            raise Refusal('logical_column_physical_order_malformed')
        ordinal = ordinal + 1 if previous is not None and key[:2] == previous[:2] else 1
        previous = key
        row[3] = ordinal
    catalog['database_acl'] = canonical_acl(catalog['database_acl'], roles)
    for field, position in ACL_FIELDS.items():
        for row in catalog[field] or []:
            row[position] = canonical_acl(row[position], roles)
    return result


def reviewed_default_equivalence(before, after, readback):
    """The sole null/default exception is bound to owner, kind, and live readback."""
    source = next((r for r in before[0]['relations'] if tuple(r[:2]) == DEFAULT_RELATION), None)
    target = next((r for r in after[0]['relations'] if tuple(r[:2]) == DEFAULT_RELATION), None)
    if source is None or target is None or source[4] == target[4]:
        return False
    expected = {'kind': 'reviewed_relation_default_acl', 'schema': DEFAULT_RELATION[0],
                'name': DEFAULT_RELATION[1], 'owner': DEFAULT_OWNER, 'relkind': 'r',
                'actual_acl': None, 'default_acl': DEFAULT_ACL}
    if (source[2:4] != ['r', DEFAULT_OWNER] or target[2:4] != ['r', DEFAULT_OWNER]
            or source[4] != DEFAULT_ACL or target[4] is not None or readback != expected):
        # All other ACL differences are handled by the exact comparison below.
        return False
    target[4] = DEFAULT_ACL.copy()
    return True


def compare_logical_inventory(before, after, default_readback=None):
    source = canonical_inventory(before)
    target = canonical_inventory(after)
    default_used = reviewed_default_equivalence(source, target, default_readback)
    if json.dumps(source, sort_keys=True, allow_nan=False) != json.dumps(target, sort_keys=True, allow_nan=False):
        raise Refusal('logical_restore_inventory_mismatch')
    return {'status': 'logical_inventory_equal',
            'tables': sum(r['kind'] == 'table' for r in before[1:]),
            'sequences': sum(r['kind'] == 'sequence' for r in before[1:]),
            'reviewed_default_acl_equivalence_used': default_used}


def collect_local(target):
    if not isinstance(target, str) or re.fullmatch(TARGET_PATTERN, target) is None:
        raise Refusal('logical_unowned_target')
    inspected = json.loads(backup.run(['docker', 'inspect', target]))
    if not isinstance(inspected, list) or len(inspected) != 1:
        raise Refusal('logical_target_inspection')
    state = inspected[0]
    if (state['Name'] != '/' + target or state['HostConfig']['NetworkMode'] != 'none'
            or state['HostConfig']['PortBindings'] not in (None, {})
            or type(state['HostConfig']['PortBindings']) not in (type(None), dict)
            or state['State']['Running'] is not True):
        raise Refusal('logical_target_not_isolated_pinned_image')
    # Docker may report a platform config ID or an index ID. Bind the exact
    # immutable publisher reference to its inspected local ID, then the target.
    images = json.loads(backup.run(['docker', 'image', 'inspect', backup.SUPABASE_IMAGE]))
    if (not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], dict)
            or not isinstance(images[0].get('RepoDigests'), list)
            or backup.SUPABASE_IMAGE not in images[0]['RepoDigests']
            or not isinstance(images[0].get('Id'), str)
            or re.fullmatch(r'sha256:[0-9a-f]{64}', images[0]['Id']) is None
            or state['Image'] != images[0]['Id']):
        raise Refusal('logical_target_not_isolated_pinned_image')
    query = """BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL timezone='UTC'; SET LOCAL datestyle='ISO, YMD'; SET LOCAL extra_float_digits=3;
SELECT json_build_object('kind','local_execution_context','executor',current_user,
 'server_version',current_setting('server_version'),'local_socket',inet_server_addr() IS NULL,
 'search_path',current_setting('search_path'),'database',current_database());
""" + backup.INVENTORY_SQL + '\n' + acquisition.RECOVERY_PREREQUISITES_SQL + '\n' + DEFAULT_READBACK_SQL + '\nROLLBACK;'
    output = backup.run(['docker', 'exec', '-i', target, 'psql', '-XqAt', '-v',
                         'ON_ERROR_STOP=1', '-U', 'postgres', '-d', 'postgres'],
                        input=query.encode(), timeout=120)
    rows = [json.loads(line) for line in output.decode().splitlines()]
    if (not rows or not isinstance(rows[0], dict)
            or set(rows[0]) != {'kind','executor','server_version','local_socket','search_path','database'}
            or rows[0].get('kind') != 'local_execution_context'
            or rows[0].get('executor') != 'postgres' or rows[0].get('server_version') != '17.6'
            or rows[0].get('local_socket') is not True or rows[0].get('database') != 'postgres'
            or not isinstance(rows[0]['search_path'], str) or not rows[0]['search_path']
            or '\x00' in rows[0]['search_path']):
        raise Refusal('logical_execution_context_mismatch')
    context = rows.pop(0)
    default = rows.pop() if rows and rows[-1].get('kind') == 'reviewed_relation_default_acl' else None
    if not rows or rows[-1].get('kind') != 'recovery_prerequisites':
        raise Refusal('logical_prerequisites_missing')
    return rows[:-1], rows[-1], default, context


def verify_bundle(bundle, target, original_failure, output, request, approved_request_sha256):
    """Hash-bind all acquired artifacts and preserve the earlier failed attempt."""
    bundle, original_failure, output, request = map(Path, (bundle, original_failure, output, request))
    request = backup.private_file(request)
    if (not isinstance(approved_request_sha256, str)
            or re.fullmatch('[0-9a-f]{64}', approved_request_sha256) is None
            or sha(request) != approved_request_sha256):
        raise Refusal('logical_approved_request_binding')
    disposition = json.loads(request.read_text())
    receipt = backup.private_file(bundle / 'receipt.json')
    captured = json.loads(receipt.read_text())
    expected = {'database.dump', 'roles.sql', 'inventory.json', 'recovery_prerequisites.json'}
    if (captured.get('status') != 'acquired_inputs_restore_and_completeness_pending'
            or set(captured.get('artifacts', {})) != expected
            or captured.get('inventory_generator_sha256') != sha(Path(backup.__file__))
            or captured.get('generator_sha256') != sha(Path(acquisition.__file__))):
        raise Refusal('logical_bundle_binding')
    for name in expected:
        path = backup.private_file(bundle / name)
        if sha(path) != captured['artifacts'][name]['sha256'] or path.stat().st_size != captured['artifacts'][name]['bytes']:
            raise Refusal('logical_bundle_artifact_mismatch')
    failed = json.loads(backup.private_file(original_failure).read_text())
    if (failed.get('status') != 'FAILED_OFFLINE_RESTORE' or failed.get('backup_verified') is not False
            or failed.get('phase') != 'strict_source_restored_comparison'
            or failed.get('container') != target
            or failed.get('bundle_receipt_sha256') != sha(receipt)
            or failed.get('archive_sha256') != sha(bundle / 'database.dump')):
        raise Refusal('logical_original_failure_binding')
    expected_disposition = {'comparison_mode': COMPARISON_MODE,
                            'verifier_sha256': sha(Path(__file__)), 'local_target': target,
                            'bundle_receipt_sha256': sha(receipt),
                            'archive_sha256': sha(bundle / 'database.dump'),
                            'original_failed_receipt_sha256': sha(original_failure),
                            'allowed_equivalences': EQUIVALENCES}
    if disposition != expected_disposition:
        raise Refusal('logical_reviewed_disposition_mismatch')
    before = json.loads((bundle / 'inventory.json').read_text())
    before_props = json.loads((bundle / 'recovery_prerequisites.json').read_text())
    after, after_props, default, context = collect_local(target)
    # The collector uses the original executor and captured role GUCs. No
    # schema qualification/deparser text is normalized by this verifier.
    acquisition.compare_recovery_prerequisites(before_props, after_props)
    verdict = compare_logical_inventory(before, after, default)
    strict_equal = True
    try:
        backup.compare_inventory(before, after)
    except Refusal:
        strict_equal = False
    restored_inventory = output.with_name(output.stem + '.restored_inventory.json')
    restored_prerequisites = output.with_name(output.stem + '.restored_prerequisites.json')
    backup.write_new(restored_inventory, after)
    backup.write_new(restored_prerequisites, after_props)
    if (json.loads(restored_inventory.read_text()) != after
            or json.loads(restored_prerequisites.read_text()) != after_props):
        raise Refusal('logical_restored_artifact_readback')
    result = dict(verdict, status='PASS_ACTUAL_LOGICAL_DATABASE_RESTORE', backup_verified=True,
                  production_recovery_verified=False, production_connections=0, mutations=False,
                  generated_by=str(Path(__file__).resolve()), generator_sha256=sha(Path(__file__)),
                  generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  target_commit=backup.run(['git', '-C', str(Path(__file__).resolve().parents[1]), 'rev-parse', 'HEAD']).decode().strip(),
                  source_hashes={'acquisition': sha(Path(acquisition.__file__)), 'inventory': sha(Path(backup.__file__))},
                  comparison_mode=COMPARISON_MODE, reviewed_request=str(request),
                  reviewed_request_sha256=sha(request), allowed_equivalences=EQUIVALENCES,
                  original_failed_receipt=str(original_failure), original_failed_receipt_sha256=sha(original_failure),
                  bundle_receipt_sha256=sha(receipt), archive_sha256=sha(bundle / 'database.dump'),
                  strict_physical_inventory_equal=strict_equal, durable_prerequisites_equal=True,
                  local_target=target, execution_context=context, default_acl_readback=default,
                  restored_inventory=str(restored_inventory), restored_inventory_sha256=sha(restored_inventory),
                  restored_prerequisites=str(restored_prerequisites), restored_prerequisites_sha256=sha(restored_prerequisites),
                  scope='Acquired logical database state; external provider credentials and storage bytes are separate recovery inputs.')
    backup.write_new(output, result)
    readback = json.loads(output.read_text())
    if readback != result or readback['generator_sha256'] != sha(Path(__file__)):
        raise Refusal('logical_receipt_readback')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--original-failure', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--approved-request-sha256', required=True)
    args = parser.parse_args()
    try:
        result = verify_bundle(args.bundle, args.target, args.original_failure, args.out,
                               args.request, args.approved_request_sha256)
    except (Refusal, OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired):
        print(json.dumps({'status': 'REFUSED_LOGICAL_DATABASE_RESTORE', 'backup_verified': False}))
        return 1
    print(json.dumps({'status': result['status'], 'backup_verified': True,
                      'receipt': str(args.out), 'receipt_sha256': sha(args.out)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
