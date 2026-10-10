#!/usr/bin/env python3
"""Portable offline archive review. This does not rerun the historical browser."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from replay_env import external_output, require
from run_v2 import ROOT, identity, sha


def main():
    require(len(sys.argv) == 3, 'EXTERNAL_OUTPUT ABSOLUTE_NODE required')
    out = external_output(ROOT, sys.argv[1])
    require(not any(out.iterdir()), 'fresh empty output directory required')
    node = Path(sys.argv[2])
    require(node.is_absolute() and node.is_file() and os.access(node, os.X_OK), 'absolute Node executable required')
    node = node.resolve()
    own = Path(__file__).resolve().parent
    pkg = ROOT / 'docs/admin/implementation/batch10-scroll-evidence'
    direct_out = out / 'direct-controls-output'
    direct_out.mkdir()
    before = identity()
    started = time.time()
    commands = [
        ('package-cli', [str(node), str(pkg / 'verify.mjs')]),
        ('package-tests', [str(node), '--test', str(pkg / 'verify.test.mjs')]),
        ('direct-controls', [str(node), str(own / 'direct_controls_v2.mjs'), str(direct_out)]),
    ]
    results = []
    for name, command in commands:
        recorder_command = [sys.executable, str(own / 'run_v2.py'), name, str(ROOT), *command]
        result = subprocess.run(recorder_command, env={'PATH': os.defpath, 'PYTHONDONTWRITEBYTECODE': '1',
                                'BATCH10_DEPENDENCIES_OUTPUT': str(out)}, capture_output=True, timeout=300)
        # Retain wrapper streams as well as the actual child streams from run_v2.
        for suffix, value in (('.wrapper.stdout', result.stdout), ('.wrapper.stderr', result.stderr)):
            with (out / (name + suffix)).open('xb') as handle:
                handle.write(value)
        require((out / (name + '.json')).is_file(), 'recorder did not execute: ' + result.stderr.decode(errors='replace'))
        receipt = json.loads((out / (name + '.json')).read_bytes())
        results.append({'name': name, 'recorder_command': recorder_command, 'wrapper_exit': result.returncode,
                        'child_exit': receipt['exit'], 'receipt_sha256': sha(out / (name + '.json'))})
        print(json.dumps(results[-1]), flush=True)
    after = identity()
    receipt = {
        'schema': 2, 'classification': 'CURRENT_OFFLINE_ARCHIVE_REVIEW', 'current_checkout_acceptance': False,
        'meaning': 'historical archive integrity and parser controls only; 494/601/607 remain unresolved',
        'generated_by': str(Path(__file__).resolve().relative_to(ROOT)), 'generator_sha256': sha(__file__),
        'started_at_unix': started, 'ended_at_unix': time.time(), 'source_before': before, 'source_after': after,
        'source_stable': before == after, 'node_executable': str(node), 'node_executable_sha256': sha(node),
        'commands': results,
        'verification_exit': 0 if before == after and all(r['wrapper_exit'] == 0 and r['child_exit'] == 0 for r in results) else 1,
    }
    with (out / 'execution-v2.json').open('x') as handle:
        json.dump(receipt, handle, indent=2)
    require(json.loads((out / 'execution-v2.json').read_bytes()) == receipt, 'review receipt readback mismatch')
    return receipt['verification_exit']


if __name__ == '__main__':
    sys.exit(main())
