"""Strict shared evidence envelope/replay checks, never domain-authority approval.

All originals must already exist locally. No URL is opened and no source is
acquired. Lane-specific fiscal/OAG authority and actual HMAC/ORM validation must
run against the final combined source before any operational gate may pass.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from common import BoundEvidence, Refusal, canonical, digest, fields, identity, integer, read_json, require, sha256, string
import hashlib
from verify import fresh_time, valid_source

CONTRACT = Path(__file__).resolve().parents[2] / 'docs/operations/nightly-acceptance-20261105/contract.json'


def artifact(reference, root, originals=None):
    fields(reference, ('path', 'sha256', 'size'))
    name = Path(string(reference['path']))
    require(not name.is_absolute() and '..' not in name.parts and name.as_posix() == reference['path']
            and name.as_posix() != '.', 'relative canonical retained original path required')
    root = Path(root).absolute()
    path = root / name
    for parent in [path, *path.parents]:
        require(not parent.is_symlink(), 'retained original symlink')
    if originals is None:
        with BoundEvidence() as bound:
            data = bound.read(path)
    else:
        data = originals.read(path)
    require(len(data) == integer(reference['size'], 1)
            and hashlib.sha256(data).hexdigest() == digest(reference['sha256']), 'retained original absent/empty/changed')
    return path


def unique_strings(values):
    require(type(values) is list and bool(values) and all(type(v) is str and v for v in values)
            and len(set(values)) == len(values), 'nonempty unique string inventory required')
    return values


def validate(path):
    with BoundEvidence() as originals:
        return _validate(path, originals)


def validate_weekly(path):
    with BoundEvidence() as originals:
        return _validate(path, originals, kind='weekly-bootstrap-native')


def _validate(path, originals, kind='full15'):
    value = originals.json(path)
    path = Path(path).absolute()
    for entry in [path, *path.parents]:
        require(not entry.is_symlink(), 'original envelope symlink')
    fields(value, ('schema', 'generated_at', 'binding', 'source', 'runtime', 'plan', 'cli', 'pg',
                   'domains', 'refresh', 'originals'))
    schema = {'full15':'nightly-operational-envelope-v1',
              'weekly-bootstrap-native':'nightly-weekly-operational-envelope-v1'}[kind]
    require(value['schema'] == schema, 'unknown typed operational envelope')
    fresh_time(value['generated_at'], 604800)
    binding = value['binding']
    fields(binding, ('commit', 'tree', 'admitted_sha', 'schema_revision', 'run_id', 'attempt'))
    digest(binding['commit'], 40)
    digest(binding['tree'], 40)
    require(binding['admitted_sha'] == binding['commit'], 'source admission differs')
    require(binding['schema_revision'] == read_json(CONTRACT)['schema_revision'], 'unknown target database schema')
    integer(binding['run_id'], 1)
    integer(binding['attempt'], 1)
    root = path.parent
    def original(reference): return artifact(reference, root, originals)
    def original_json(reference): return originals.json(original(reference))
    source = original_json(value['source'])
    valid_source(source)
    require(source['commit'] == binding['commit'] and source['tree'] == binding['tree']
            and source['status'] == '', 'clean exact source identity required')
    runtime = original_json(value['runtime'])
    from runtime import LOCK, validate_runtime
    validate_runtime(runtime)
    require(runtime['qualification'] == 'PYTHON_AND_REVIEWED_NATIVE'
            and runtime['lock_sha256'] == sha256(LOCK), 'reviewed production/native runtime required')
    plan = value['plan']
    fields(plan, ('sha256', 'original'))
    original_plan = original_json(plan['original'])
    require(identity(original_plan) == digest(plan['sha256']), 'source plan digest differs')
    fields(original_plan, ('domains', 'bootstrap', 'dry_run', 'audits_review',
                           'reacquire_pending_pdf', 'audits_source_acceptance'))
    domains = unique_strings(original_plan['domains'])
    expected = read_json(CONTRACT)['domains']
    if kind == 'weekly-bootstrap-native': expected = ['opendata', *sorted(expected)]
    require(set(domains) == set(expected), 'exact typed full15/weekly domain inventory required')
    require(original_plan['dry_run'] is False
            and original_plan['bootstrap'] is (kind == 'weekly-bootstrap-native')
            and original_plan['reacquire_pending_pdf'] is False
            and original_plan['audits_review'] == '' and original_plan['audits_source_acceptance'] == '',
            'ordinary full15/weekly bootstrap scope differs')
    cli = value['cli']
    fields(cli, ('exit_code', 'executed', 'run_id', 'attempt', 'original'))
    require(integer(cli['exit_code']) == 0 and cli['executed'] is True, 'CLI did not execute successfully')
    require(cli['run_id'] == binding['run_id'] and type(cli['run_id']) is int
            and cli['attempt'] == binding['attempt'] and type(cli['attempt']) is int, 'CLI run/attempt differs')
    original(cli['original'])
    pg = value['pg']
    fields(pg, ('schema_revision', 'run_id', 'attempt', 'inventory'))
    require(pg['schema_revision'] == binding['schema_revision'] and pg['run_id'] == binding['run_id']
            and type(pg['run_id']) is int and pg['attempt'] == binding['attempt']
            and type(pg['attempt']) is int, 'PG identity differs')
    pg_rows = original_json(pg['inventory'])
    require(type(pg_rows) is list and len(pg_rows) == len(domains), 'PG full job inventory required')
    require(type(value['domains']) is list and len(value['domains']) == len(domains), 'domain results missing')
    ids, names, component_ids = set(), set(), set()
    for row in value['domains']:
        fields(row, ('domain', 'job_id', 'status', 'components'))
        domain, job_id = string(row['domain']), integer(row['job_id'], 1)
        require(domain in domains and domain not in names and job_id not in ids, 'duplicate/unknown domain/job')
        names.add(domain); ids.add(job_id)
        require(row['status'] == ('curated' if domain == 'learning_hub' else 'accepted'),
                'held/partial/unavailable/unconfirmed domain cannot qualify full recovery')
        require(type(row['components']) is list and bool(row['components']), 'source component inventory missing')
        for component in row['components']:
            fields(component, ('id', 'period', 'basis', 'units', 'source_bytes', 'authority', 'acquisition', 'readback'))
            key = (domain, string(component['id']))
            require(key not in component_ids, 'duplicate source component')
            component_ids.add(key)
            for field in ('period', 'basis', 'units'):
                string(component[field])
            source_bytes = original(component['source_bytes'])
            readback = original(component['readback'])
            require(sha256(source_bytes) == sha256(readback), 'retained readback bytes differ from original source')
            original(component['authority'])
            original(component['acquisition'])
    observed = set()
    for row in pg_rows:
        fields(row, ('domain', 'job_id', 'run_id', 'attempt', 'processed', 'created', 'updated'))
        pair = (string(row['domain']), integer(row['job_id'], 1))
        require(pair not in observed, 'duplicate PG row')
        observed.add(pair)
        require(type(row['run_id']) is int and row['run_id'] == binding['run_id']
                and type(row['attempt']) is int and row['attempt'] == binding['attempt'], 'PG job run differs')
        processed = integer(row['processed'], 1)
        require(integer(row['created']) + integer(row['updated']) <= processed, 'invalid PG writer counts')
    require(observed == {(r['domain'], r['job_id']) for r in value['domains']}, 'CLI/PG domain/job inventory differs')
    refresh = value['refresh']
    fields(refresh, ('worker_pids', 'events', 'paths'))
    pids = refresh['worker_pids']
    require(type(pids) is list and bool(pids) and all(type(p) is int and p > 0 for p in pids)
            and len(set(pids)) == len(pids), 'unique actual backend worker census required')
    unique_strings(refresh['paths'])
    require(type(refresh['events']) is list and len(refresh['events']) == len(pids) + 2, 'refresh ack inventory incomplete')
    kinds, workers = [], set()
    previous = -1
    for event in refresh['events']:
        fields(event, ('kind', 'sequence', 'pid', 'request', 'signature', 'response'))
        sequence = integer(event['sequence'])
        require(sequence > previous, 'duplicate/reordered refresh event')
        previous = sequence
        kinds.append(event['kind'])
        digest(event['signature'])
        original(event['request']); original(event['response'])
        if event['kind'] == 'backend_worker':
            require(type(event['pid']) is int and event['pid'] in pids and event['pid'] not in workers, 'bad/duplicate worker ack')
            workers.add(event['pid'])
        else:
            require(event['pid'] is None, 'unexpected worker identity')
    require(kinds == ['backend_invalidate', *['backend_worker'] * len(pids), 'frontend']
            and workers == set(pids), 'backend census must precede pages')
    attachments = value['originals']
    fields(attachments, ('run', 'jobs', 'full_log', 'acquisition_inventory', 'source_authority_review',
                      'hmac_verification', 'cleanup'))
    for reference in attachments.values(): original(reference)
    return value


def observe_local(path, *, backend_config, signing_key_file):
    """Supported local semantic importer; structural envelopes remain pending-only."""
    from acceptance_semantic import observe
    return observe(path, backend_config=backend_config, signing_key_file=signing_key_file)


def replay(first_path, second_path):
    first, second = validate(first_path), validate(second_path)
    require((first['binding']['run_id'], first['binding']['attempt']) !=
            (second['binding']['run_id'], second['binding']['attempt']), 'distinct run/attempt required')
    for key in ('commit', 'tree', 'admitted_sha', 'schema_revision'):
        require(first['binding'][key] == second['binding'][key], 'replay binding differs')
    require(first['plan']['sha256'] == second['plan']['sha256'], 'replay plan differs')
    for key in ('source', 'runtime'):
        require(first[key]['sha256'] == second[key]['sha256'], 'replay source/runtime bytes differ')
    def components(value):
        return sorted((row['domain'], c['id'], c['period'], c['basis'], c['units'],
                       c['source_bytes']['sha256'], c['authority']['sha256'], c['acquisition']['sha256'])
                      for row in value['domains'] for c in row['components'])
    require(components(first) == components(second), 'replay source/component/origin authority differs')
    return {'verdict': 'EVIDENCE_ENVELOPE_BOUND_AUTHORITY_AND_OPERATIONAL_REVIEW_PENDING',
            'production_accepted': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('first', type=Path)
    parser.add_argument('--replay', type=Path)
    parser.add_argument('--kind', choices=('full15','weekly-bootstrap-native'), default='full15')
    parser.add_argument('--semantic-local', action='store_true')
    parser.add_argument('--backend-config', type=Path)
    parser.add_argument('--signing-key-file', type=Path)
    args = parser.parse_args()
    try:
        if args.semantic_local:
            require(args.replay is None and args.backend_config is not None and args.signing_key_file is not None,
                    'semantic local importer requires explicit backend config and signing key originals')
            result = observe_local(args.first, backend_config=args.backend_config, signing_key_file=args.signing_key_file)
            print(result['verdict'])
        else:
            if args.replay:
                require(args.kind == 'full15', 'weekly replay requires its distinct semantic contract')
                replay(args.first, args.replay)
            elif args.kind == 'weekly-bootstrap-native': validate_weekly(args.first)
            else: validate(args.first)
            print('EVIDENCE_ENVELOPE_BOUND_AUTHORITY_AND_OPERATIONAL_REVIEW_PENDING')
    except (Refusal, OSError, ValueError, KeyError) as exc:
        print(f'REFUSED: {exc}', file=sys.stderr)
        sys.exit(1)
