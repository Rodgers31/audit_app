"""Read back a local execution against its originals; never an operational approval."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from common import (Refusal, canonical, digest, fields, identity, integer, read_json,
                    require, sha256, string)
from record import TOOL, inventory, source_snapshot, validate_outcomes

KEYS = ('schema', 'generated_by', 'generator_sha256', 'helpers', 'generated_at',
        'target_commit', 'target_tree', 'source', 'source_sha256', 'runtime', 'argv',
        'environment', 'child_exit', 'expected', 'executed', 'cleanup', 'artifacts', 'failures', 'verdict')


def fresh_time(value, maximum):
    integer(maximum, 1)
    require(maximum <= 604800, 'freshness ceiling is seven days')
    timestamp = datetime.fromisoformat(string(value))
    require(timestamp.tzinfo is not None, 'explicit execution timezone required')
    age = (datetime.now(timezone.utc) - timestamp).total_seconds()
    require(0 <= age <= maximum, 'stale/future execution')


def valid_source(source):
    fields(source, ('commit', 'tree', 'status', 'files', 'corpus'))
    digest(source['commit'], 40)
    digest(source['tree'], 40)
    require(type(source['status']) is str and type(source['corpus']) is dict, 'invalid source status/corpus')
    def rows(files):
        require(type(files) is dict and bool(files), 'nonempty source file inventory required')
        for name, row in files.items():
            string(name)
            require(not Path(name).is_absolute() and '..' not in Path(name).parts
                    and name != '.' and Path(name).as_posix() == name, 'invalid/noncanonical source member')
            fields(row, ('size', 'sha256'))
            integer(row['size'])
            digest(row['sha256'])
    rows(source['files'])
    for root, files in source['corpus'].items():
        require(Path(string(root)).is_absolute(), 'absolute original corpus root required')
        rows(files)


def validate(path, repo=None, max_age_seconds=86400):
    integer(max_age_seconds, 1)
    require(max_age_seconds <= 604800, 'freshness ceiling is seven days')
    path = Path(path)
    require(path.name == 'execution.json' and not path.is_symlink(), 'original execution path required')
    receipt = read_json(path)
    fields(receipt, KEYS)
    require(receipt['schema'] == 'nightly-local-execution-v1', 'unknown execution schema')
    require(receipt['generated_by'] == str(TOOL) and receipt['generator_sha256'] == sha256(TOOL),
            'unexpected/stale recorder')
    require(receipt['helpers'] == inventory(TOOL.parent), 'helper bytes changed; historical execution only')
    require(receipt['verdict'] == 'LOCAL_CONTROLS_PASSED' and receipt['failures'] == [], 'failed execution')
    fresh_time(receipt['generated_at'], max_age_seconds)
    valid_source(receipt['source'])
    digest(receipt['target_commit'], 40)
    digest(receipt['target_tree'], 40)
    require(type(receipt['source']) is dict and bool(receipt['source'].get('files')),
            'complete source inventory required')
    require(receipt['source']['commit'] == receipt['target_commit']
            and receipt['source']['tree'] == receipt['target_tree']
            and identity(receipt['source']) == digest(receipt['source_sha256']), 'source identity mismatch')
    fields(receipt['cleanup'], ('pgid', 'group_absent', 'leader_reaped'))
    integer(receipt['cleanup']['pgid'], 2)
    require(receipt['cleanup']['group_absent'] is True and receipt['cleanup']['leader_reaped'] is True,
            'positive process closure proof required')
    fields(receipt['artifacts'], ('stdout.log', 'stderr.log', 'junit.xml', 'phases.json', 'invocation.json'))
    for name, checksum in receipt['artifacts'].items():
        artifact = path.parent / name
        require(artifact.is_file() and not artifact.is_symlink() and sha256(artifact) == digest(checksum),
                f'original artifact changed: {name}')
    actual = validate_outcomes(read_json(path.parent / 'phases.json'), path.parent / 'junit.xml',
                               receipt['expected'], receipt['child_exit'])
    require(receipt['executed'] == actual, 'executed inventory mismatch')
    argv = receipt['argv']
    require(type(argv) is list and len(argv) >= 13 and all(type(x) is str and x for x in argv)
            and Path(argv[0]).is_absolute()
            and argv[1:12] == ['-B', '-m', 'pytest', '-p', 'pytest_observer', '-p', 'no:cacheprovider', '-rA', '-o',
                              'xfail_strict=true', '--junitxml=' + str(path.parent / 'junit.xml')]
            and all(not x.startswith('-') for x in argv[12:]), 'unexpected test entry point')
    expected_env = {'PATH': str(Path(receipt['argv'][0]).parent) + ':/usr/local/bin:/usr/bin:/bin',
                    'HOME': str(path.parent), 'TMPDIR': str(path.parent), 'PYTHONDONTWRITEBYTECODE': '1',
                    'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTHONPATH': str(TOOL.parent),
                    'NIGHTLY_PHASE_REPORT': str(path.parent / 'phases.json')}
    require(type(receipt['environment']) is dict and receipt['environment'] == expected_env,
            'unexpected child environment')
    invocation = read_json(path.parent / 'invocation.json')
    fields(invocation, ('argv', 'environment', 'source_sha256'))
    require(canonical(invocation) == canonical({'argv': argv, 'environment': receipt['environment'],
                                               'source_sha256': receipt['source_sha256']}),
            'execution differs from retained original invocation')
    runtime = receipt['runtime']
    require(runtime is None or type(runtime) is dict, 'malformed execution runtime')
    if runtime is not None:
        from runtime import validate_runtime
        validate_runtime(runtime)
    if repo is not None:
        corpus = list(receipt['source']['corpus'])
        require(canonical(source_snapshot(repo, corpus)) == canonical(receipt['source']),
                'current source differs from original execution')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt', type=Path)
    parser.add_argument('--repo', type=Path)
    args = parser.parse_args()
    try:
        validate(args.receipt, args.repo)
        print('LOCAL_EXECUTION_VERIFIED; production acceptance remains pending')
    except (Refusal, OSError, ValueError, KeyError) as exc:
        print(f'REFUSED: {exc}', file=sys.stderr)
        sys.exit(1)
