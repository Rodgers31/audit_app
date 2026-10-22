#!/usr/bin/env python3
"""Offline supplement to a logical restore: capture-bound persistent privileges.

Only the already owned network-none PostgreSQL target is queried. Source proof,
producer and original unfiltered matrix are retained inputs, never executed.
The approved request is an operator checkpoint, not a signature or source grant.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
import uuid
from pathlib import Path
import re
import subprocess

import verify_logical_pg_restore as logical

backup = logical.backup
Refusal = logical.Refusal
CONTRACT_SHA = '6b67ebb6d4cae58c28ef15e57c62a43f0fc6eddebf64cc6b9d0559246080b98f'
SQL_SHA = 'd56a58384a26aeefc0f8fa9ffeaed91d79fe104565ef15c0a7bd3cf978024f4b'
ORIGINAL_SQL_SHA = 'f537f259693bcc324a4440fed9eb09a191bc78ba086030af0b427e2dd9acc8db'
PROOF_KEYS = {'schema','status','profile','commit','generator_sha256','catalog_sha256',
    'durable_prerequisites_sha256','original_privileges_sha256','persistent_privileges_sha256',
    'profile_contract_sha256','original_sql_sha256','persistent_sql_sha256','role_count',
    'excluded_temp_namespace_count','read_only','tls_verified','publishing_disabled','off_switch_count',
    'production_mutations','connection_disposed','temporary_material_removed','generated_at','elapsed_seconds'}


def require(value, reason):
    if value is not True:
        raise Refusal(reason)


def digest(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None, 'permission_digest')
    return value


def private_input(value):
    path = backup.private_file(value)
    require(path.stat().st_uid == os.getuid(), 'permission_input_owner')
    limit = 128 * 1024 * 1024 if path.name == 'database.dump' else 64 * 1024 * 1024
    require(0 < path.stat().st_size <= limit, 'permission_input_bound')
    return path


def load_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'permission_duplicate_json_field')
            result[key] = value
        return result
    def constant(_):
        raise Refusal('permission_nonfinite_json')
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=constant)


def sources_unchanged(sources, hashes):
    return (all(logical.sha(path) == hashes[name] for name,path in sources.items())
            and Path(__file__).resolve() == sources['verifier']
            and Path(logical.__file__).resolve() == sources['logical']
            and Path(logical.acquisition.__file__).resolve() == sources['acquisition']
            and Path(backup.__file__).resolve() == sources['inventory'])


def load_contract():
    path = Path(__file__).with_name('persistent_privilege_contract.py')
    require(logical.sha(path) == CONTRACT_SHA, 'permission_contract_changed')
    spec = importlib.util.spec_from_file_location('_persistent_privilege_contract', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def validate_source(proof, before, props, original, producer_sha, contract, *, now=None):
    """Bind retained source evidence to the archive's exact catalog/config/roles.

    Capture evidence may outlive the capture session. Its time is retained and
    cannot establish freshness of today's production state. Wrong-archive proof
    never becomes valid by reusing its original timestamp or producer name.
    """
    require(type(proof) is dict and set(proof) == PROOF_KEYS, 'permission_source_shape')
    require(type(proof['schema']) is int and proof['schema'] == 1
            and proof['status'] == 'VERIFIED_CAPTURE_BOUND_PERSISTENT_PRIVILEGES_SOURCE'
            and proof['profile'] == contract.PROFILE, 'permission_source_contract')
    require(type(proof['commit']) is str and re.fullmatch('[0-9a-f]{40}', proof['commit']) is not None,
            'permission_source_commit')
    for key in PROOF_KEYS:
        if key.endswith('_sha256'):
            digest(proof[key])
    require(proof['generator_sha256'] == producer_sha and proof['profile_contract_sha256'] == CONTRACT_SHA
            and proof['original_sql_sha256'] == ORIGINAL_SQL_SHA and proof['persistent_sql_sha256'] == SQL_SHA,
            'permission_source_producer_or_sql')
    require(all(proof[k] is True for k in ('read_only','tls_verified','publishing_disabled',
            'connection_disposed','temporary_material_removed')) and proof['production_mutations'] is False,
            'permission_source_execution')
    require(type(proof['off_switch_count']) is int and proof['off_switch_count'] == 12
            and type(proof['excluded_temp_namespace_count']) is int
            and 0 <= proof['excluded_temp_namespace_count'] <= 1000000,
            'permission_source_bounds')
    require(type(proof['elapsed_seconds']) in (int, float) and math.isfinite(proof['elapsed_seconds'])
            and 0 <= proof['elapsed_seconds'] < 60, 'permission_source_elapsed')
    try:
        stamp = dt.datetime.fromisoformat(proof['generated_at'])
        require(stamp.utcoffset() == dt.timedelta(0)
                and (stamp - (now or dt.datetime.now(dt.timezone.utc))).total_seconds() <= 30,
                'permission_source_time')
    except (TypeError, ValueError, OverflowError):
        raise Refusal('permission_source_time') from None
    logical.canonical_inventory(before)
    roles = [row[0] for row in before[0]['roles']]
    contract.validate_matrix(original, roles)
    require(type(proof['role_count']) is int and proof['role_count'] == len(roles) > 0,
            'permission_source_roles')
    require(proof['catalog_sha256'] == contract.digest(contract.catalog_projection(before[0], logical))
            and proof['durable_prerequisites_sha256'] == contract.digest(contract.durable_projection(props, logical.acquisition))
            and proof['original_privileges_sha256'] == contract.digest(original), 'permission_source_capture_binding')
    return roles


def query_profile(target):
    """Fresh owned-target context, inventory/config and matrix in one snapshot."""
    # The same audited target/image/isolation inspection as the logical verifier.
    logical.inspect_local_target(target)
    path = Path(__file__).with_name('persistent_pg_privileges.sql')
    require(logical.sha(path) == SQL_SHA, 'permission_sql_changed')
    fixed = path.read_text()
    select = fixed[fixed.index('SELECT json_build_object'):fixed.rindex('ROLLBACK;')]
    sql = """BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL timezone='UTC'; SET LOCAL datestyle='ISO, YMD'; SET LOCAL extra_float_digits=3;
SET LOCAL statement_timeout='30s'; SET LOCAL lock_timeout='1s';
SELECT json_build_object('kind','persistent_profile_context','executor',current_user,
 'server_version',current_setting('server_version'),'local_socket',inet_server_addr() IS NULL,
 'readonly',current_setting('transaction_read_only'),'database',current_database(),
 'search_path',pg_catalog.current_setting('search_path'),
 'resolved_schemas',pg_catalog.current_schemas(true));
""" + backup.INVENTORY_SQL + '\n' + logical.acquisition.RECOVERY_PREREQUISITES_SQL + '\n' + select + '\nROLLBACK;'
    raw = backup.run(['docker','exec','-i',target,'psql','-XqAt','-v','ON_ERROR_STOP=1',
                      '-U','postgres','-d','postgres'], input=sql.encode(), timeout=120)
    rows = backup.inventory_json_lines(raw)
    context = rows[0] if rows else None
    require(type(context) is dict and set(context) == {'kind','executor','server_version','local_socket',
            'readonly','database','search_path','resolved_schemas'} and context['kind'] == 'persistent_profile_context'
            and context['executor'] == 'postgres' and context['server_version'] == '17.6'
            and context['local_socket'] is True and context['readonly'] == 'on'
            and context['database'] == 'postgres' and context['resolved_schemas'] == ['pg_catalog','public']
            and len(rows) >= 4, 'permission_target_context')
    return rows[1:-2], rows[-2], rows[-1], context


def verify(bundle, target, logical_receipt, source_proof, source_generator, original_privileges,
           request, approved_sha256, output, check_plan=None):
    paths = {name: private_input(value) for name, value in (
        ('logical_receipt',logical_receipt),('source_proof',source_proof),
        ('source_generator',source_generator),('original_privileges',original_privileges),('request',request))}
    bundle, output = Path(bundle), Path(output)
    require(not output.exists() and not output.is_symlink() and output.parent.is_dir()
            and not output.parent.is_symlink() and output.parent.stat().st_uid == os.getuid()
            and output.parent.stat().st_mode & 0o077 == 0, 'permission_new_private_output_required')
    require(logical.sha(paths['request']) == digest(approved_sha256), 'permission_request_binding')
    for name in ('receipt.json','database.dump','roles.sql','inventory.json','recovery_prerequisites.json'):
        paths['bundle/' + name] = private_input(bundle / name)
    parent = load_json(paths['logical_receipt'])
    require(type(parent) is dict, 'permission_logical_receipt_shape')
    for name in ('reviewed_request','original_failed_receipt','restored_inventory','restored_prerequisites'):
        paths[name] = private_input(parent[name])
        require(logical.sha(paths[name]) == parent[name+'_sha256'], 'permission_logical_artifact_binding')
    if check_plan is not None:
        paths['check_plan'] = private_input(check_plan)
        require(logical.sha(paths['check_plan']) == parent.get('check_reparse_plan_sha256'), 'permission_check_plan_binding')
    else:
        require('isolated_check_reparse' not in parent, 'permission_check_plan_required')
    initial = {name: logical.sha(path) for name, path in paths.items()}
    contract, contract_path = load_contract()
    sources = {name: Path(value).resolve() for name, value in (
        ('verifier',__file__),('logical',logical.__file__),('acquisition',logical.acquisition.__file__),
        ('inventory',backup.__file__),('contract',contract_path),
        ('check_helper',Path(__file__).with_name('logical_restore_check_proof.py')),
        ('check_grammar',Path(__file__).with_name('logical_restore_check_grammar.py')),
        ('sql',Path(__file__).with_name('persistent_pg_privileges.sql')))}
    source_hashes = {name: logical.sha(path) for name, path in sources.items()}
    require(source_hashes['sql'] == SQL_SHA, 'permission_sql_changed')
    decision = load_json(paths['request'])
    expected = {'version':1,'local_target':target,'verifier_sha256':source_hashes['verifier'],
                'source_hashes':source_hashes,'input_hashes':{k:v for k,v in initial.items() if k != 'request'}}
    require(type(decision) is dict and type(decision.get('version')) is int and decision == expected,
            'permission_reviewed_disposition')
    captured = load_json(paths['bundle/receipt.json'])
    require(captured.get('status') == 'acquired_inputs_restore_and_completeness_pending'
            and captured.get('generator_sha256') == source_hashes['acquisition']
            and captured.get('inventory_generator_sha256') == source_hashes['inventory']
            and set(captured.get('artifacts',{})) == {'database.dump','roles.sql','inventory.json','recovery_prerequisites.json'},
            'permission_bundle_binding')
    for name, item in captured['artifacts'].items():
        require(type(item) is dict and type(item.get('bytes')) is int
                and item['bytes'] == paths['bundle/'+name].stat().st_size
                and item.get('sha256') == initial['bundle/'+name], 'permission_bundle_artifact')
    require(parent.get('status') == 'PASS_ACTUAL_LOGICAL_DATABASE_RESTORE' and parent.get('backup_verified') is True
            and parent.get('persistent_mutations') is False and type(parent.get('production_connections')) is int
            and parent['production_connections'] == 0 and parent.get('production_recovery_verified') is False
            and parent.get('generator_sha256') == source_hashes['logical'] and parent.get('local_target') == target
            and parent.get('bundle_receipt_sha256') == initial['bundle/receipt.json']
            and parent.get('archive_sha256') == initial['bundle/database.dump']
            and parent.get('durable_prerequisites_equal') is True
            and parent.get('source_hashes') == {k:source_hashes[k] for k in ('acquisition','inventory')},
            'permission_logical_receipt_binding')
    before = load_json(paths['bundle/inventory.json'])
    props = load_json(paths['bundle/recovery_prerequisites.json'])
    original = load_json(paths['original_privileges'])
    proof = load_json(paths['source_proof'])
    roles = validate_source(proof,before,props,original,initial['source_generator'],contract)
    # A named/hash-matching PASS file is not proof that its comparison ran.
    # Re-execute the approved logical verifier on the same live isolated target.
    reverified_path = output.with_name(output.stem + '.logical_reverified.json')
    reverified = logical.verify_bundle(bundle,target,paths['original_failed_receipt'],reverified_path,
        paths['reviewed_request'],initial['reviewed_request'],paths.get('check_plan'),
        initial.get('check_plan'))
    inventory, properties, matrix, context = query_profile(target)
    require(context['search_path'] == parent['execution_context']['search_path'], 'permission_target_search_path')
    require(inventory == load_json(paths['restored_inventory'])
            and inventory == json.loads(Path(reverified['restored_inventory']).read_text()),
            'permission_target_inventory_changed')
    logical.acquisition.compare_recovery_prerequisites(load_json(paths['restored_prerequisites']), properties)
    contract.validate_matrix(matrix, roles)
    require(contract.digest(matrix) == proof['persistent_privileges_sha256'], 'permission_persistent_profile_changed')
    # Recheck the complete live state after the profile read and bind all files
    # immediately before publishing. No success survives input/producer drift.
    require(all(logical.sha(path) == initial[name] for name,path in paths.items())
            and sources_unchanged(sources,source_hashes),
            'permission_input_or_producer_changed')
    matrix_path = output.with_name(output.stem + '.restored_privileges.json')
    backup.write_new(matrix_path,matrix)
    result = {'status':'PASS_LOGICAL_RESTORE_AND_PERSISTENT_PRIVILEGES','backup_verified':True,'persistent_privileges_verified':True,
        'production_recovery_verified':False,'production_connections':0,
        'mutations':reverified['mutations'],'persistent_mutations':False,
        'logical_reverification_sha256':logical.sha(reverified_path),
        'generated_by':str(Path(__file__).resolve()),'generator_sha256':source_hashes['verifier'],
        'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source_hashes':source_hashes,
        'request_sha256':approved_sha256,'input_hashes':initial,'local_target':target,
        'source_observation_generated_at':proof['generated_at'],'source_observation_commit':proof['commit'],
        'source_observation_is_current_production_read':False,'role_count':len(roles),
        'source_excluded_temp_namespace_count':proof['excluded_temp_namespace_count'],'profile':contract.PROFILE,
        'persistent_privileges_sha256':contract.digest(matrix),'restored_privileges_sha256':logical.sha(matrix_path),
        'scope':'Persistent permission supplement for this exact acquired archive and logical restore; external services/storage/keys remain separate.'}
    staged = output.with_name(output.name + '.pending-' + uuid.uuid4().hex)
    try:
        backup.write_new(staged,result)
        require(json.loads(staged.read_text()) == result and json.loads(matrix_path.read_text()) == matrix,
                'permission_publication_readback')
        final_inventory, final_props, final_matrix, final_context = query_profile(target)
        contract.validate_matrix(final_matrix, roles)
        require(final_inventory == inventory and final_matrix == matrix and final_context == context,
                'permission_profile_changed_before_publication')
        logical.acquisition.compare_recovery_prerequisites(properties,final_props)
        require(all(logical.sha(path) == initial[name] for name,path in paths.items())
                and sources_unchanged(sources,source_hashes),
                'permission_input_or_producer_changed_before_publication')
        os.link(staged,output)
    finally:
        staged.unlink(missing_ok=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('bundle','target','logical-receipt','source-proof','source-generator','original-privileges','request','out'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--approved-request-sha256',required=True)
    parser.add_argument('--check-reparse-plan')
    args=parser.parse_args()
    try:
        result=verify(args.bundle,args.target,args.logical_receipt,args.source_proof,args.source_generator,
                      args.original_privileges,args.request,args.approved_request_sha256,args.out,args.check_reparse_plan)
    except (Refusal,OSError,ValueError,TypeError,KeyError,IndexError,subprocess.TimeoutExpired):
        print(json.dumps({'status':'REFUSED_PERSISTENT_PRIVILEGES','persistent_privileges_verified':False}))
        return 1
    print(json.dumps({k:result[k] for k in ('status','persistent_privileges_verified','production_connections','mutations','role_count')}))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
