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
from common import Refusal, canonical, digest, fields, identity, integer, read_json, require, sha256, string
from verify import fresh_time, valid_source

CONTRACT = Path(__file__).resolve().parents[2] / 'docs/operations/nightly-acceptance-20261105/contract.json'


def artifact(reference, root):
    fields(reference, ('path', 'sha256', 'size'))
    name = Path(string(reference['path']))
    require(not name.is_absolute() and '..' not in name.parts, 'relative retained original path required')
    root = Path(root).resolve()
    path = root / name
    for parent in [path, *path.parents]:
        require(not parent.is_symlink(), 'retained original symlink')
    require(path.is_file() and path.stat().st_size == integer(reference['size'], 1)
            and sha256(path) == digest(reference['sha256']), 'retained original absent/empty/changed')
    return path


def unique_strings(values):
    require(type(values) is list and bool(values) and all(type(v) is str and v for v in values)
            and len(set(values)) == len(values), 'nonempty unique string inventory required')
    return values


def validate(path):
    path = Path(path)
    for entry in [path, *path.parents]:
        require(not entry.is_symlink(), 'original envelope symlink')
    value = read_json(path)
    fields(value, ('schema', 'generated_at', 'binding', 'source', 'runtime', 'plan', 'cli', 'pg',
                   'domains', 'refresh', 'originals'))
    require(value['schema'] == 'nightly-operational-envelope-v1', 'unknown operational envelope')
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
    source = read_json(artifact(value['source'], root))
    valid_source(source)
    require(source['commit'] == binding['commit'] and source['tree'] == binding['tree']
            and source['status'] == '', 'clean exact source identity required')
    runtime = read_json(artifact(value['runtime'], root))
    from runtime import LOCK, validate_runtime
    validate_runtime(runtime)
    require(runtime['qualification'] == 'PYTHON_AND_REVIEWED_NATIVE'
            and runtime['lock_sha256'] == sha256(LOCK), 'reviewed production/native runtime required')
    plan = value['plan']
    fields(plan, ('sha256', 'original'))
    original_plan = read_json(artifact(plan['original'], root))
    require(identity(original_plan) == digest(plan['sha256']), 'source plan digest differs')
    fields(original_plan, ('domains', 'bootstrap', 'dry_run', 'audits_review',
                           'reacquire_pending_pdf', 'audits_source_acceptance'))
    domains = unique_strings(original_plan['domains'])
    require(set(domains) == set(read_json(CONTRACT)['domains']), 'full fifteen-domain plan required')
    require(original_plan['dry_run'] is False and type(original_plan['bootstrap']) is bool
            and type(original_plan['reacquire_pending_pdf']) is bool
            and type(original_plan['audits_review']) is str
            and type(original_plan['audits_source_acceptance']) is str, 'malformed/unexecuted plan')
    cli = value['cli']
    fields(cli, ('exit_code', 'executed', 'run_id', 'attempt', 'original'))
    require(integer(cli['exit_code']) == 0 and cli['executed'] is True, 'CLI did not execute successfully')
    require(cli['run_id'] == binding['run_id'] and type(cli['run_id']) is int
            and cli['attempt'] == binding['attempt'] and type(cli['attempt']) is int, 'CLI run/attempt differs')
    artifact(cli['original'], root)
    pg = value['pg']
    fields(pg, ('schema_revision', 'run_id', 'attempt', 'inventory'))
    require(pg['schema_revision'] == binding['schema_revision'] and pg['run_id'] == binding['run_id']
            and type(pg['run_id']) is int and pg['attempt'] == binding['attempt']
            and type(pg['attempt']) is int, 'PG identity differs')
    pg_rows = read_json(artifact(pg['inventory'], root))
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
            source_bytes = artifact(component['source_bytes'], root)
            readback = artifact(component['readback'], root)
            require(sha256(source_bytes) == sha256(readback), 'retained readback bytes differ from original source')
            artifact(component['authority'], root)
            artifact(component['acquisition'], root)
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
        artifact(event['request'], root); artifact(event['response'], root)
        if event['kind'] == 'backend_worker':
            require(type(event['pid']) is int and event['pid'] in pids and event['pid'] not in workers, 'bad/duplicate worker ack')
            workers.add(event['pid'])
        else:
            require(event['pid'] is None, 'unexpected worker identity')
    require(kinds == ['backend_invalidate', *['backend_worker'] * len(pids), 'frontend']
            and workers == set(pids), 'backend census must precede pages')
    originals = value['originals']
    fields(originals, ('run', 'jobs', 'full_log', 'acquisition_inventory', 'source_authority_review',
                      'hmac_verification', 'cleanup'))
    for reference in originals.values(): artifact(reference, root)
    return value


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
    args = parser.parse_args()
    try:
        if args.replay: replay(args.first, args.replay)
        else: validate(args.first)
        print('EVIDENCE_ENVELOPE_BOUND_AUTHORITY_AND_OPERATIONAL_REVIEW_PENDING')
    except (Refusal, OSError, ValueError, KeyError) as exc:
        print(f'REFUSED: {exc}', file=sys.stderr)
        sys.exit(1)
