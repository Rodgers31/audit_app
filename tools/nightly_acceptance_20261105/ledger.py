"""Prepare an immutable dependency ledger; check local evidence without releasing it.

Operational gates intentionally require separate original hosted/source/adoption
receipts. This preparer does not manufacture those receipts or accept local doubles
as hosted runs. Unknown schemas and manual status edits are refused.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from common import Refusal, digest, fields, identity, publish, read_json, require, sha256, string
from record import git, source_snapshot, outside
from verify import validate, valid_source, fresh_time

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / 'docs/operations/nightly-acceptance-20261105/contract.json'
LANES = ('workflow', 'fiscal', 'oag', 'transport', 'runtime')


def prepare(repo, output, corpus=()):
    contract = read_json(CONTRACT)
    require(contract['schema'] == 'nightly-acceptance-contract-v1', 'unknown contract')
    output = outside(output, [repo, Path(__file__).resolve().parent, *corpus])
    require(not output.exists(), 'fresh external ledger path required')
    snapshot = source_snapshot(repo, corpus)
    ledger = {'schema': 'nightly-acceptance-ledger-v1', 'generated_by': str(Path(__file__).resolve()),
              'generator_sha256': sha256(__file__), 'generated_at': datetime.now(timezone.utc).isoformat(),
              'target_commit': snapshot['commit'], 'target_tree': snapshot['tree'],
              'source_sha256': identity(snapshot), 'source': snapshot,
              'contract_sha256': sha256(CONTRACT),
              'deliveries': {lane: None for lane in LANES},
              'gates': {row['id']: {'status': 'pending', 'evidence': None} for row in contract['gates']},
              'production_accepted': False, 'verdict': 'PREPARED_ALL_ACCEPTANCE_GATES_PENDING'}
    publish(output, ledger)
    return ledger


def check_prepared(path):
    ledger = read_json(path)
    fields(ledger, ('schema', 'generated_by', 'generator_sha256', 'generated_at', 'target_commit',
                    'target_tree', 'source_sha256', 'source', 'contract_sha256', 'deliveries',
                    'gates', 'production_accepted', 'verdict'))
    require(ledger['schema'] == 'nightly-acceptance-ledger-v1', 'unknown ledger')
    require(ledger['generated_by'] == str(Path(__file__).resolve())
            and ledger['generator_sha256'] == sha256(__file__), 'stale/unexpected ledger generator')
    fresh_time(ledger['generated_at'], 604800)
    valid_source(ledger['source'])
    digest(ledger['target_commit'], 40)
    digest(ledger['target_tree'], 40)
    require(ledger['source']['commit'] == ledger['target_commit']
            and ledger['source']['tree'] == ledger['target_tree']
            and identity(ledger['source']) == digest(ledger['source_sha256']), 'ledger source mismatch')
    require(ledger['contract_sha256'] == sha256(CONTRACT), 'acceptance contract changed')
    fields(ledger['deliveries'], LANES)
    require(all(v is None for v in ledger['deliveries'].values()), 'prepared ledger cannot assert lane delivery')
    fields(ledger['gates'], [row['id'] for row in read_json(CONTRACT)['gates']])
    for gate in ledger['gates'].values():
        fields(gate, ('status', 'evidence'))
        require(gate['status'] == 'pending' and gate['evidence'] is None,
                'prepared ledger cannot assert execution; retain a new original stage receipt')
    require(ledger['production_accepted'] is False
            and ledger['verdict'] == 'PREPARED_ALL_ACCEPTANCE_GATES_PENDING', 'false acceptance claim')
    return ledger


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'check-prepared', 'check-local'))
    parser.add_argument('path', type=Path)
    parser.add_argument('--repo', type=Path, default=ROOT)
    parser.add_argument('--corpus', type=Path, action='append', default=[])
    args = parser.parse_args()
    try:
        if args.action == 'prepare':
            prepare(args.repo, args.path, args.corpus)
            print('PREPARED_ALL_ACCEPTANCE_GATES_PENDING')
        elif args.action == 'check-prepared':
            check_prepared(args.path)
            print('PREPARED_LEDGER_VALID; execution/adoption/release still pending')
        else:
            validate(args.path, args.repo)
            print('LOCAL_EXECUTION_VERIFIED; operational acceptance still pending')
    except (Refusal, OSError, ValueError, KeyError) as exc:
        print(f'REFUSED: {exc}', file=sys.stderr)
        sys.exit(1)
