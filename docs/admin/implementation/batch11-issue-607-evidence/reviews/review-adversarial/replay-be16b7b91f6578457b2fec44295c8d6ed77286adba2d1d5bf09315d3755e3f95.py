"""Capture a fresh production-config replay in an explicitly owned container.

Prepare the pinned Linux runtime as documented in README.md; mount the checkout
at /app and an external artifact directory at /evidence. This entrypoint never
installs into shared runtimes, forwards credentials, or enables hosted workflows.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
sys.dont_write_bytecode = True
from verify_packet import cases, load


def check(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(checkout, output, container, docker_host, cohort, mode):
    checkout, output = Path(checkout).resolve(), Path(output).absolute()
    check(not any(p.is_symlink() for p in [output, *output.parents]), 'Symlinked output')
    check(not output.resolve().is_relative_to(checkout) and output.parent.is_dir() and not output.exists(), 'Use a fresh external output directory')
    check(cohort in ['public', 'users', 'operations', 'overview-audit', 'etl-ui', 'coordinator'], 'Unsupported cohort')
    check(mode in ['focused', 'original-100', 'cohort'], 'Unsupported mode')
    check(cohort == 'public' or mode == 'cohort', 'Focused/original modes require public cohort')
    docker = shutil.which('docker')
    check(docker is not None, 'Docker is required')
    output.mkdir()
    (output / 'home').mkdir()
    env = {'PATH': os.defpath, 'HOME': str(output / 'home'), 'DOCKER_HOST': docker_host}
    meta = json.loads(subprocess.check_output([docker, 'inspect', container], env=env, timeout=30))[0]
    check(meta['Config']['Labels'].get('audit_app.owner') == 'batch11-navigation', 'Container is not explicitly owned by this lane')
    check(meta['State']['Running'] is True and meta['HostConfig']['PortBindings'] in [None, {}], 'Use an isolated running container without host ports')
    mounts = meta['Mounts']
    check(any(Path(m['Source']).resolve() == checkout and m['Destination'] == '/app' for m in mounts), 'Container checkout mount mismatch')
    targets = [m for m in mounts if output.resolve().is_relative_to(Path(m['Source']).resolve()) and m['Destination'] == '/evidence']
    check(len(targets) == 1, 'Output must be below an owned /evidence bind mount')
    target = '/evidence/' + output.relative_to(Path(targets[0]['Source'])).as_posix()
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=checkout).decode().strip('\0').split('\0')
    check(paths and len(paths) == len(set(paths)), 'Empty/duplicate tracked source inventory')
    source = {p: sha(checkout / p) for p in paths}
    identity = subprocess.check_output(['git', 'rev-parse', 'HEAD', 'HEAD^{tree}'], cwd=checkout, text=True).splitlines()
    runtime = '/opt/b11/node-v22.23.3-linux-x64/bin:/opt/b11/python/bin:/usr/local/bin:/usr/bin:/bin'
    command = [docker, 'exec', container, 'env', '-i', 'PATH=' + runtime, 'HOME=/evidence/home', 'PLAYWRIGHT_BROWSERS_PATH=/ms-playwright', 'BROWSER_TEST_PYTHON=/opt/b11/python/bin/python', 'BROWSER_TEST_COHORT=' + cohort, 'BROWSER_TARGET_SHA=' + identity[0], 'CI=true', 'PLAYWRIGHT_JSON_OUTPUT_FILE=' + target + '/report.json', 'node', 'node_modules/@playwright/test/cli.js', 'test', '--config', 'playwright.ci-cohorts.config.ts', '--project=chromium', '--output', target + '/browser', '--reporter=list,json']
    if mode == 'focused':
        command += ['e2e/county-pagination-boundaries.spec.ts', 'e2e/county-pagination-contract.spec.ts']
    elif mode == 'original-100':
        command += ['e2e/smart-back.spec.ts', '--grep', 'scroll position is roughly preserved', '--repeat-each=100']
    started = time.time()
    timed_out = False
    with (output / 'console.log').open('x') as log:
        try:
            child = subprocess.run(command, env=env, cwd=checkout / 'frontend', stdout=log, stderr=subprocess.STDOUT, timeout=1200)
            child_exit = child.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            child_exit = None
    changed = [p for p, h in source.items() if not (checkout / p).is_file() or sha(checkout / p) != h]
    result = {'head': identity[0], 'tree': identity[1], 'source_hashes': source, 'source_changed': changed, 'child_exit': child_exit, 'timed_out': timed_out, 'command': command, 'started': started, 'ended': time.time(), 'generator_sha256': sha(Path(__file__)), 'log_sha256': sha(output / 'console.log'), 'scope': 'fresh local replay; no hosted or production acceptance', 'timeout_cleanup': 'If timed out, remote children may remain in this exact owned container; stop it and inspect before reusing.'}
    with (output / 'receipt.json').open('x') as f:
        json.dump(result, f, indent=2)
    check(json.loads((output / 'receipt.json').read_text()) == result, 'Receipt readback mismatch')
    check(not changed and not timed_out and type(child_exit) is int and child_exit == 0, 'Replay failed or source drifted; inspect preserved output')
    measured, counters = cases(load(output / 'report.json'))
    expected = 6 if mode == 'focused' else 100 if mode == 'original-100' else {'public': 275, 'users': 4, 'operations': 6, 'overview-audit': 5, 'etl-ui': 28, 'coordinator': 11}[cohort]
    skipped = 11 if mode == 'cohort' and cohort == 'public' else 0
    check(len(measured) == expected and counters == {'expected': expected - skipped, 'unexpected': 0, 'skipped': skipped, 'flaky': 0}, 'Incomplete/failed fresh execution accounting')
    print(json.dumps({k: v for k, v in result.items() if k not in ['source_hashes', 'command']}))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkout', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--container', required=True)
    p.add_argument('--docker-host', required=True)
    p.add_argument('--cohort', default='public')
    p.add_argument('--mode', choices=['focused', 'original-100', 'cohort'], default='focused')
    a = p.parse_args()
    execute(a.checkout, a.output, a.container, a.docker_host, a.cohort, a.mode)


if __name__ == '__main__':
    main()
