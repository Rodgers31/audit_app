"""Read back a local execution against its originals; never an operational approval."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import io
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from common import (BoundEvidence, Refusal, canonical, digest, fields, identity, integer, loads, read_json,
                    require, sha256, string)
from record import TOOL, child_invocation, inventory, source_snapshot, validate_outcomes

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
    with BoundEvidence() as originals:
        return _validate(path, repo, max_age_seconds, originals)


def _validate(path, repo, max_age_seconds, originals):
    integer(max_age_seconds, 1)
    require(max_age_seconds <= 604800, 'freshness ceiling is seven days')
    raw_path = path
    path = Path(path).absolute()
    require(path.name == 'execution.json' and not path.is_symlink(), 'original execution path required')
    receipt = originals.json(raw_path)
    version2 = receipt.get('schema') == 'nightly-local-execution-v2'
    fields(receipt, (*KEYS, 'configuration') if version2 else KEYS)
    require(receipt['schema'] in ('nightly-local-execution-v1', 'nightly-local-execution-v2'), 'unknown execution schema')
    config = receipt.get('configuration')
    if version2:
        fields(config, ('backend', 'optimized', 'repo', 'targets', 'native_profile'))
        require(type(config['repo']) is str and Path(config['repo']).is_absolute()
                and type(config['targets']) is list and bool(config['targets'])
                and all(type(t) is str and t and not t.startswith('-') for t in config['targets']),
                'explicit original source/targets required')
        if repo is not None:
            require(Path(repo).absolute() == Path(config['repo']), 'source checkout path differs')
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
    names = ('stdout.log', 'stderr.log', 'junit.xml', 'phases.json', 'invocation.json')
    if version2 and config['backend'] is not None: names += ('backend.json',)
    fields(receipt['artifacts'], names)
    artifacts = {}
    for name, checksum in receipt['artifacts'].items():
        artifacts[name] = originals.read(path.parent / name)
        require(hashlib.sha256(artifacts[name]).hexdigest() == digest(checksum),
                f'original artifact changed: {name}')
    actual = validate_outcomes(loads(artifacts['phases.json']), io.BytesIO(artifacts['junit.xml']),
                               receipt['expected'], receipt['child_exit'])
    require(receipt['executed'] == actual, 'executed inventory mismatch')
    argv = receipt['argv']
    require(type(argv) is list and bool(argv) and all(type(x) is str and x for x in argv)
            and Path(argv[0]).is_absolute(), 'absolute original interpreter required')
    if version2:
        expected_argv, expected_env = child_invocation(argv[0], Path(config['repo']), path.parent,
                                                     config['targets'], config['backend'], config['optimized'])
        require(argv == expected_argv, 'unexpected configured test entry point')
        if config['backend'] is not None:
            from acceptance_backend_config import validate_report
            validate_report(loads(artifacts['backend.json']), config['backend'], receipt['expected'])
    else:
        require(len(argv) >= 13
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
    invocation = loads(artifacts['invocation.json'])
    fields(invocation, ('argv', 'environment', 'source_sha256', *(['configuration'] if version2 else [])))
    expected_invocation = {'argv': argv, 'environment': receipt['environment'],
                           'source_sha256': receipt['source_sha256']}
    if version2: expected_invocation['configuration'] = config
    require(canonical(invocation) == canonical(expected_invocation),
            'execution differs from retained original invocation')
    runtime = receipt['runtime']
    require(runtime is None or type(runtime) is dict, 'malformed execution runtime')
    if runtime is not None:
        from runtime import validate_runtime
        validate_runtime(runtime)
    if version2 and config['native_profile'] is not None:
        require(runtime is not None and runtime['qualification'] == 'PYTHON_AND_REVIEWED_NATIVE',
                'native execution requires qualified original runtime')
        require(hashlib.sha256(originals.read(config['native_profile'])).hexdigest() == runtime['native_profile_sha256'],
                'original reviewed native profile changed')
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
