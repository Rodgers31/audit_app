"""Run local pytest controls, refusing incomplete evidence and source/runtime drift.

This records local execution only. It never dispatches, acquires official source,
connects to production, or turns local evidence into production acceptance.
Use an outer OS sandbox for arbitrary test code. All output is fresh and external.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import signal
import math
import re
import stat
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
from common import (Refusal, canonical, fields, identity, integer, publish,
                    read_json, require, sha256, string)

TOOL = Path(__file__).resolve()


def git(repo, *args):
    result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, check=True,
                            timeout=30, env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/tmp'})
    return result.stdout.decode().strip()


def inventory(root):
    root = Path(root).absolute()
    require(root.exists() and not root.is_symlink(), 'inventory root absent/symlink')
    paths = [root] if root.is_file() else sorted(root.rglob('*'))
    rows = {}
    for path in paths:
        if path == root / '.git' or root / '.git' in path.parents:
            continue
        require(not path.is_symlink(), f'symlink in consumed corpus: {path}')
        require(path.is_file() or path.is_dir(), f'nonregular consumed corpus entry: {path}')
        if path.is_file():
            rows[str(path.relative_to(root)) if root.is_dir() else path.name] = {
                'size': path.stat().st_size, 'sha256': sha256(path)}
    require(bool(rows), 'empty consumed corpus')
    return rows


def source_snapshot(repo, corpus):
    return {'commit': git(repo, 'rev-parse', 'HEAD'), 'tree': git(repo, 'rev-parse', 'HEAD^{tree}'),
            'status': git(repo, 'status', '--porcelain=v1', '--untracked-files=all'),
            'files': inventory(repo),
            'corpus': {str(Path(p).absolute()): inventory(p) for p in corpus}}


def outside(path, roots):
    path = Path(path).absolute()
    # Reject traversal and any symlink component before resolve hides it.
    require('..' not in path.parts, 'output traversal')
    for component in [path, *path.parents]:
        require(not component.is_symlink(), 'output symlink')
    resolved = path.resolve()
    for root in roots:
        root = Path(root).resolve()
        require(resolved != root and root not in resolved.parents, 'output overlaps measured input')
    return resolved


def validate_outcomes(phases, junit, expected, child_exit):
    integer(child_exit)
    require(child_exit == 0, f'pytest child exit: {child_exit}')
    require(type(expected) is list and bool(expected), 'nonempty expected case inventory required')
    require(all(type(x) is str and x.strip() for x in expected) and len(set(expected)) == len(expected),
            'expected cases must be unique nonempty strings')
    fields(phases, ('exitstatus', 'reports'))
    require(integer(phases['exitstatus']) == child_exit, 'observer exit mismatch')
    require(type(phases['reports']) is list and bool(phases['reports']), 'no phase reports')
    actual = {}
    for row in phases['reports']:
        fields(row, ('nodeid', 'phase', 'outcome', 'wasxfail'))
        node = string(row['nodeid'])
        require(node in expected, f'unexpected case: {node}')
        require(row['phase'] in ('setup', 'call', 'teardown'), 'unknown test phase')
        require(row['outcome'] == 'passed' and row['wasxfail'] is None,
                f"nonpassing/skipped/XPASS phase: {node} {row['phase']}")
        phases_seen = actual.setdefault(node, set())
        require(row['phase'] not in phases_seen, 'duplicate phase report')
        phases_seen.add(row['phase'])
    require(set(actual) == set(expected) and all(p == {'setup', 'call', 'teardown'} for p in actual.values()),
            'missing executed cases/phases')
    tree = ET.parse(junit)
    require(tree.getroot().tag in ('testsuites', 'testsuite'), 'unknown JUnit root')
    require(not any(element.tag in ('error', 'failure', 'skipped') for element in tree.iter()),
            'JUnit error/failure/skip at any scope')
    suites = [tree.getroot()] if tree.getroot().tag == 'testsuite' else tree.findall('.//testsuite')
    require(bool(suites), 'nonempty JUnit suites required')
    for element in tree.iter():
        for key in ('tests', 'errors', 'failures', 'skipped'):
            if key in element.attrib:
                value = element.attrib[key]
                require(re.fullmatch(r'[0-9]+', value) is not None, 'malformed JUnit count')
                if key != 'tests':
                    require(int(value) == 0, f'JUnit reports {key}')
        if 'time' in element.attrib:
            try:
                elapsed = float(element.attrib['time'])
            except ValueError as exc:
                raise Refusal('malformed JUnit duration') from exc
            require(math.isfinite(elapsed) and elapsed >= 0, 'nonfinite/negative JUnit duration')
    for suite in suites:
        if 'tests' in suite.attrib:
            require(int(suite.attrib['tests']) == len(suite.findall('.//testcase')), 'JUnit suite count mismatch')
    cases = tree.findall('.//testcase')
    if 'tests' in tree.getroot().attrib:
        require(int(tree.getroot().attrib['tests']) == len(cases), 'JUnit root count mismatch')
    require(len(cases) == len(expected) and bool(cases), 'JUnit case inventory differs')
    seen = set()
    expected_junit = set()
    for node in expected:
        parts = node.split('::')
        require(len(parts) >= 2 and parts[0].endswith('.py'), 'pytest node identity required')
        expected_junit.add(('.'.join([parts[0][:-3].replace('/', '.'), *parts[1:-1]]), parts[-1]))
    for case in cases:
        key = (case.get('classname'), case.get('name'))
        require(all(type(x) is str and x for x in key) and key not in seen, 'duplicate/missing JUnit identity')
        seen.add(key)
        require(not list(case.findall('skipped')) and not list(case.findall('error'))
                and not list(case.findall('failure')), 'JUnit failure/skip')
    require(seen == expected_junit, 'JUnit identities differ from executed phases')
    return sorted(actual)


def group_absent(pgid):
    integer(pgid, 2)
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    return False


def reap(process):
    """Own one new session; kill its descendants even after its leader exited."""
    pgid = process.pid
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if group_absent(pgid):
            break
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        until = time.monotonic() + 2
        while not group_absent(pgid) and time.monotonic() < until:
            time.sleep(0.05)
    process.wait(timeout=2)
    require(group_absent(pgid), 'owned process group still present after cleanup')
    return {'pgid': pgid, 'group_absent': True, 'leader_reaped': True}


def run(repo, output, expected_path, targets, timeout=120, corpus=(), runtime_lock=None):
    repo = Path(repo).absolute()
    integer(timeout, 1)
    require(timeout <= 1800, 'local control timeout ceiling is 1800 seconds')
    require(type(targets) is list and bool(targets)
            and all(type(x) is str and bool(x) and not x.startswith('-') for x in targets),
            'explicit pytest selectors required, no injected runner options')
    require(type(corpus) in (tuple, list) and len(set(map(str, corpus))) == len(corpus), 'duplicate corpus roots')
    expected_path = Path(expected_path).resolve()
    expected = read_json(expected_path)
    require(type(expected) is list and bool(expected) and all(type(x) is str and x for x in expected)
            and len(set(expected)) == len(expected), 'unique nonempty expected inventory required')
    output = outside(output, [repo, TOOL.parent, expected_path, *corpus])
    require(not output.exists(), 'fresh output directory required')
    require((repo / '.git').exists(), 'owned Git checkout required')
    snapshot = source_snapshot(repo, corpus)
    measured_tools = inventory(TOOL.parent)
    # Lock before substantial process execution; callers may hold it in an outer fixture.
    with open('/tmp/auditgava-launch-heavy-20261103.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Refusal('shared heavy lock busy; no child started') from exc
        runtime = None
        if runtime_lock is not None:
            from runtime import verify
            runtime = verify(runtime_lock)
        output.mkdir(mode=0o700)
        env = {'PATH': os.path.dirname(sys.executable) + ':/usr/local/bin:/usr/bin:/bin',
               'HOME': str(output), 'TMPDIR': str(output), 'PYTHONDONTWRITEBYTECODE': '1',
               'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
               'PYTHONPATH': str(TOOL.parent), 'NIGHTLY_PHASE_REPORT': str(output / 'phases.json')}
        argv = [sys.executable, '-B', '-m', 'pytest', '-p', 'pytest_observer', '-p', 'no:cacheprovider', '-rA',
                '-o', 'xfail_strict=true', '--junitxml=' + str(output / 'junit.xml'), *targets]
        publish(output / 'invocation.json', {'argv': argv, 'environment': env, 'source_sha256': identity(snapshot)})
        failures, child_exit, cleanup = [], None, None
        with (output / 'stdout.log').open('xb') as stdout, (output / 'stderr.log').open('xb') as stderr:
            process = subprocess.Popen(argv, cwd=repo, env=env, stdout=stdout, stderr=stderr,
                                       start_new_session=True)
            try:
                child_exit = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                failures.append('child timed out')
            finally:
                try:
                    cleanup = reap(process)
                except (Refusal, subprocess.SubprocessError) as exc:
                    failures.append(str(exc))
        cases = []
        try:
            cases = validate_outcomes(read_json(output / 'phases.json'), output / 'junit.xml', expected, child_exit)
        except (Refusal, OSError, ET.ParseError) as exc:
            failures.append(str(exc))
        try:
            require(canonical(source_snapshot(repo, corpus)) == canonical(snapshot), 'consumed source/corpus changed')
            require(inventory(TOOL.parent) == measured_tools, 'recorder/helper changed')
            require(read_json(expected_path) == expected, 'expected inventory changed')
            if runtime_lock is not None:
                from runtime import verify
                require(verify(runtime_lock) == runtime, 'runtime changed')
        except (Refusal, OSError, subprocess.SubprocessError) as exc:
            failures.append(str(exc))
        artifacts = {p.name: sha256(p) for p in output.iterdir() if p.is_file()}
        receipt = {'schema': 'nightly-local-execution-v1', 'generated_by': str(TOOL),
                   'generator_sha256': sha256(TOOL), 'helpers': measured_tools,
                   'generated_at': datetime.now(timezone.utc).isoformat(),
                   'target_commit': snapshot['commit'], 'target_tree': snapshot['tree'],
                   'source': snapshot, 'source_sha256': identity(snapshot),
                   'runtime': runtime, 'argv': argv, 'environment': env, 'child_exit': child_exit,
                   'expected': expected, 'executed': cases, 'cleanup': cleanup,
                   'artifacts': artifacts, 'failures': failures,
                   'verdict': 'LOCAL_CONTROLS_PASSED' if not failures else 'FAILED'}
        publish(output / 'execution.json', receipt)
        return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected', type=Path, required=True)
    parser.add_argument('--runtime-lock', type=Path)
    parser.add_argument('--corpus', type=Path, action='append', default=[])
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('targets', nargs='+')
    args = parser.parse_args()
    result = run(args.repo, args.output, args.expected, args.targets, args.timeout, args.corpus, args.runtime_lock)
    print(result['verdict'])
    return 0 if result['verdict'] == 'LOCAL_CONTROLS_PASSED' else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (Refusal, OSError, subprocess.SubprocessError) as exc:
        print(f'REFUSED: {exc}', file=sys.stderr)
        sys.exit(1)
